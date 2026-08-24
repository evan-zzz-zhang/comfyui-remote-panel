from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any

from aiohttp import web

from .comfy import ComfyClient, ComfyError
from .config import Config
from .db import TERMINAL_STATUSES, Database
from .events import EventBus
from .files import FileStore, FileValidationError
from .jobs import JobService, new_job_id
from .lifecycle import ComfyLifecycle, LifecycleError
from .metrics import MetricsService
from .preset import PresetError, load_presets


MAX_REQUEST_BYTES = 1024 * 1024 * 1024
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
RANGE_PATTERN = re.compile(r"^bytes=(\d*)-(\d*)$")
log = logging.getLogger(__name__)


def json_error(message: str, status: int, code: str = "request_error") -> web.Response:
    return web.json_response({"error": {"code": code, "message": message}}, status=status)


def create_app(config: Config) -> web.Application:
    @web.middleware
    async def security_headers(request: web.Request, handler):
        try:
            response = await handler(request)
        except web.HTTPException as exc:
            response = exc
        except Exception:
            log.exception("unhandled panel request error")
            response = json_error("服务器内部错误", 500, "internal_error")
        response.headers.update({
            "Content-Security-Policy": "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob: data:; media-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
            "X-Content-Type-Options": "nosniff",
            "Referrer-Policy": "no-referrer",
            "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
            "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        })
        if request.path != "/healthz" and not request.path.startswith("/static/"):
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @web.middleware
    async def authenticate(request: web.Request, handler):
        if request.path == "/healthz":
            return await handler(request)
        if request.headers.get("Tailscale-User-Login") not in config.allowed_logins:
            return json_error("无权访问", 403, "forbidden")
        if request.method in UNSAFE_METHODS:
            origin = request.headers.get("Origin")
            if origin is not None and origin.rstrip("/") != config.public_origin:
                return json_error("拒绝跨来源写请求", 403, "origin_mismatch")
        return await handler(request)

    app = web.Application(client_max_size=MAX_REQUEST_BYTES, middlewares=[security_headers, authenticate])
    app["config"] = config
    app["db"] = Database(config.database_path)
    app["files"] = FileStore(config.dedicated_input_dir, config.dedicated_output_dir, config.data_dir)
    app["presets"] = load_presets(config.workflow_dir)
    app["events"] = EventBus()
    app["comfy"] = ComfyClient(config.comfyui_base_url, config.minimum_comfyui_version, str(uuid.uuid4()))
    app["lifecycle"] = ComfyLifecycle(config, app["comfy"])
    app["jobs"] = JobService(app["db"], app["files"], app["comfy"], app["presets"], app["events"])
    app["metrics"] = MetricsService(app["db"], app["comfy"], app["presets"], app["events"], config.data_dir, config.monitoring_interval, config.nvidia_smi_timeout, app["lifecycle"])
    app["background_tasks"] = []

    static_dir = Path(__file__).with_name("static")

    async def healthz(_: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def index(_: web.Request) -> web.Response:
        return web.FileResponse(static_dir / "index.html")

    async def list_jobs(request: web.Request) -> web.Response:
        try:
            page = max(1, int(request.query.get("page", "1")))
            page_size = min(100, max(1, int(request.query.get("page_size", "20"))))
        except ValueError:
            return json_error("分页参数无效", 400)
        result = await app["db"].list_jobs(page, page_size)
        result["items"] = [app["jobs"].public_job(job) for job in result["items"]]
        return web.json_response(result)

    async def get_job(request: web.Request) -> web.Response:
        job = await app["db"].get_job(request.match_info["job_id"])
        if job is None:
            return json_error("任务不存在", 404, "not_found")
        return web.json_response(app["jobs"].public_job(job))

    async def create_job(request: web.Request) -> web.Response:
        if not request.content_type.startswith("multipart/"):
            return json_error("请求必须使用 multipart/form-data", 415)
        job_id = new_job_id()
        uploaded: list[dict[str, Any]] = []
        fields: dict[str, Any] = {}
        allowed_text = {"preset_id", "prompt", "duration_seconds", "aspect_ratio", "megapixels", "seed", "scheduler", "sampler", "steps", "retry_source_id"}
        fixed_files = {"first_frame": "first", "last_frame": "last"}
        repeated_files = {"ref_images": ("image", 9), "ref_videos": ("video", 3), "ref_audios": ("audio", 3)}
        repeated_counts = {name: 0 for name in repeated_files}
        try:
            reader = await request.multipart()
            async for part in reader:
                if part.name in fixed_files:
                    role = fixed_files[part.name]
                    if any(item["role"] == role for item in uploaded):
                        raise PresetError("同一帧只能上传一张图片")
                    if not part.filename:
                        continue
                    uploaded.append(await app["files"].save_upload(job_id, role, part))
                elif part.name in repeated_files:
                    if not part.filename:
                        continue
                    prefix, maximum = repeated_files[part.name]
                    index = repeated_counts[part.name]
                    if index >= maximum:
                        raise PresetError(f"{part.name} 上传数量超过 {maximum}")
                    repeated_counts[part.name] += 1
                    uploaded.append(await app["files"].save_upload(job_id, f"{prefix}_{index}", part))
                elif part.name in allowed_text:
                    if part.name in fields:
                        raise PresetError(f"字段重复：{part.name}")
                    fields[part.name] = await part.text()
                else:
                    raise PresetError(f"不支持的字段：{part.name}")
            fields["duration_seconds"] = int(fields.get("duration_seconds", "5"))
            fields["megapixels"] = float(fields.get("megapixels", "0.4"))
            if "steps" in fields:
                fields["steps"] = int(fields["steps"])
            seed_text = fields.get("seed", "").strip()
            fields["seed"] = int(seed_text) if seed_text else None
            job = await app["jobs"].create(fields, uploaded, job_id)
            return web.json_response(app["jobs"].public_job(job), status=201)
        except (ValueError, PresetError, FileValidationError) as exc:
            app["files"].cleanup_untracked(uploaded)
            return json_error(str(exc), 400, "validation_error")
        except ComfyError as exc:
            app["files"].cleanup_untracked(uploaded)
            return json_error(str(exc), 503, "comfyui_unavailable")

    async def cancel_job(request: web.Request) -> web.Response:
        try:
            job = await app["jobs"].cancel(request.match_info["job_id"])
        except KeyError:
            return json_error("任务不存在", 404, "not_found")
        except ComfyError as exc:
            return json_error(str(exc), 503, "comfyui_unavailable")
        return web.json_response(app["jobs"].public_job(job))

    async def retry_job(request: web.Request) -> web.Response:
        try:
            job = await app["jobs"].retry(request.match_info["job_id"])
        except KeyError:
            return json_error("任务不存在", 404, "not_found")
        except (PresetError, FileValidationError) as exc:
            return json_error(str(exc), 409, "invalid_state")
        except ComfyError as exc:
            return json_error(str(exc), 503, "comfyui_unavailable")
        return web.json_response(job)

    async def list_presets(_: web.Request) -> web.Response:
        return web.json_response({"items": [preset.public_metadata() for preset in app["presets"].values()]})

    async def delete_job(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except (json.JSONDecodeError, web.HTTPBadRequest):
            body = None
        if not isinstance(body, dict) or body.get("confirm") is not True:
            return json_error("删除需要 confirm=true", 400, "confirmation_required")
        try:
            await app["jobs"].delete(request.match_info["job_id"])
        except KeyError:
            return json_error("任务不存在", 404, "not_found")
        except PresetError as exc:
            return json_error(str(exc), 409, "invalid_state")
        except (OSError, FileValidationError):
            return json_error("删除失败，任务记录已保留", 500, "delete_failed")
        return web.Response(status=204)

    async def metrics(_: web.Request) -> web.Response:
        if not app["metrics"].snapshot:
            await app["metrics"].collect()
        return web.json_response(app["metrics"].snapshot)

    async def control_comfyui(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except (json.JSONDecodeError, web.HTTPBadRequest):
            body = None
        if not isinstance(body, dict) or body.get("confirm") is not True:
            return json_error("设备控制需要 confirm=true", 400, "confirmation_required")
        try:
            result = await app["lifecycle"].trigger(request.match_info["action"])
        except LifecycleError as exc:
            return json_error(str(exc), 409, "control_unavailable")
        return web.json_response(result, status=202)

    async def events(_: web.Request) -> web.StreamResponse:
        if not app["metrics"].snapshot:
            await app["metrics"].collect()
        response = web.StreamResponse(status=200, headers={
            "Content-Type": "text/event-stream; charset=utf-8",
            "Cache-Control": "no-cache, no-store",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        })
        await response.prepare(_)
        jobs = await app["db"].list_jobs(1, 100)
        snapshot = {"jobs": [app["jobs"].public_job(job) for job in jobs["items"]], "metrics": app["metrics"].snapshot}
        await _write_sse(response, "snapshot", snapshot)
        iterator = app["events"].subscribe().__aiter__()
        try:
            while True:
                try:
                    event = await asyncio.wait_for(iterator.__anext__(), timeout=15)
                    await _write_sse(response, event["type"], event["data"])
                except asyncio.TimeoutError:
                    await response.write(b": heartbeat\n\n")
        except (ConnectionResetError, asyncio.CancelledError, StopAsyncIteration):
            pass
        finally:
            await iterator.aclose()
        return response

    async def video(request: web.Request) -> web.StreamResponse:
        job = await app["db"].get_job(request.match_info["job_id"])
        if job is None:
            return json_error("任务不存在", 404, "not_found")
        output = next((file for file in job["files"] if file["role"] == "output"), None)
        if output is None:
            return json_error("视频尚不可用", 404, "video_unavailable")
        try:
            path = app["files"].validate_output_file(Path(output["path"]))
        except (OSError, FileValidationError):
            return json_error("视频文件不存在或路径无效", 404, "video_unavailable")
        return await _stream_file(request, path)

    app.router.add_get("/healthz", healthz)
    app.router.add_get("/", index)
    app.router.add_static("/static", static_dir, show_index=False)
    app.router.add_get("/api/jobs", list_jobs)
    app.router.add_post("/api/jobs", create_job)
    app.router.add_get("/api/presets", list_presets)
    app.router.add_get("/api/jobs/{job_id}", get_job)
    app.router.add_post("/api/jobs/{job_id}/cancel", cancel_job)
    app.router.add_post("/api/jobs/{job_id}/retry", retry_job)
    app.router.add_delete("/api/jobs/{job_id}", delete_job)
    app.router.add_get("/api/jobs/{job_id}/video", video)
    app.router.add_get("/api/metrics", metrics)
    app.router.add_post("/api/comfyui/control/{action}", control_comfyui)
    app.router.add_get("/api/events", events)

    async def startup(_: web.Application) -> None:
        config.data_dir.mkdir(parents=True, exist_ok=True)
        app["files"].initialize()
        await app["db"].initialize()
        await app["comfy"].start()
        app["background_tasks"] = [
            asyncio.create_task(app["jobs"].reconcile_loop(config.monitoring_interval)),
            asyncio.create_task(app["jobs"].websocket_loop()),
            asyncio.create_task(app["metrics"].loop()),
        ]

    async def cleanup(_: web.Application) -> None:
        app["jobs"].stop()
        app["metrics"].stop()
        for task in app["background_tasks"]:
            task.cancel()
        if app["background_tasks"]:
            await asyncio.gather(*app["background_tasks"], return_exceptions=True)
        await app["lifecycle"].close()
        await app["comfy"].close()

    app.on_startup.append(startup)
    app.on_cleanup.append(cleanup)
    return app


async def _write_sse(response: web.StreamResponse, event: str, data: Any) -> None:
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    await response.write(f"event: {event}\ndata: {payload}\n\n".encode("utf-8"))


async def _stream_file(request: web.Request, path: Path) -> web.StreamResponse:
    size = path.stat().st_size
    start, end, status = 0, size - 1, 200
    range_header = request.headers.get("Range")
    if range_header:
        match = RANGE_PATTERN.fullmatch(range_header.strip())
        if not match or (not match.group(1) and not match.group(2)):
            return web.Response(status=416, headers={"Content-Range": f"bytes */{size}"})
        if match.group(1):
            start = int(match.group(1))
            end = int(match.group(2)) if match.group(2) else size - 1
        else:
            suffix = int(match.group(2))
            if suffix <= 0:
                return web.Response(status=416, headers={"Content-Range": f"bytes */{size}"})
            start = max(0, size - suffix)
        if start >= size or end < start:
            return web.Response(status=416, headers={"Content-Range": f"bytes */{size}"})
        end = min(end, size - 1)
        status = 206
    length = max(0, end - start + 1)
    disposition = "attachment" if request.query.get("download") == "1" else "inline"
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(length),
        "Content-Type": mimetypes.guess_type(path.name)[0] or "video/mp4",
        "Content-Disposition": f'{disposition}; filename="{path.name}"',
    }
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    response = web.StreamResponse(status=status, headers=headers)
    await response.prepare(request)
    if request.method != "HEAD":
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                await response.write(chunk)
    await response.write_eof()
    return response
