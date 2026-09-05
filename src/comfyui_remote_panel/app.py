from __future__ import annotations

import asyncio
from datetime import datetime
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

from .auth import AuthProvider, create_auth_provider
from .comfy import ComfyClient, ComfyError
from .config import Config
from .db import TERMINAL_STATUSES, Database
from .events import EventBus
from .files import FileStore, FileValidationError, StorageCapacityError
from .jobs import JobService, new_job_id
from .lifecycle import ComfyLifecycle, LifecycleError
from .metrics import MetricsService
from .preset import PresetError, load_presets, preset_from_definition
from .workflow_config import (
    MAX_PACKAGE_BYTES, MAX_WORKFLOW_BYTES, build_definition, export_package,
    import_package, inspect_api_workflow, parse_json_bytes,
)


MAX_REQUEST_BYTES = 1024 * 1024 * 1024
MAX_PROMPT_BYTES = 32 * 1024
MAX_PROMPT_CHARS = 10_000
MAX_TEXT_FIELD_BYTES = 2 * 1024
MAX_TEXT_FIELD_CHARS = 1_000
UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
RANGE_PATTERN = re.compile(r"^bytes=(\d*)-(\d*)$")
log = logging.getLogger(__name__)
_SSE_HEARTBEAT_SECONDS = 15
_JOB_EXISTENCE_LIMIT = 100


class TextFieldTooLarge(ValueError):
    pass


def json_error(message: str, status: int, code: str = "request_error") -> web.Response:
    return web.json_response({"error": {"code": code, "message": message}}, status=status)


def create_app(config: Config, auth_provider: AuthProvider | None = None) -> web.Application:
    auth_provider = auth_provider or create_auth_provider(config)
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
        principal = auth_provider.authenticate(request)
        if principal is None:
            return json_error("无权访问", 403, "forbidden")
        request["principal"] = principal
        if request.method in UNSAFE_METHODS:
            origin = request.headers.get("Origin")
            if origin is not None and not auth_provider.allows_origin(origin):
                return json_error("拒绝跨来源写请求", 403, "origin_mismatch")
        return await handler(request)

    app = web.Application(client_max_size=MAX_REQUEST_BYTES, middlewares=[security_headers, authenticate])
    app["config"] = config
    app["auth_provider"] = auth_provider
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

    async def existing_jobs(request: web.Request) -> web.Response:
        raw_ids = request.query.get("ids", "")
        job_ids = [item for item in raw_ids.split(",") if item]
        if not job_ids or len(set(job_ids)) > _JOB_EXISTENCE_LIMIT:
            return json_error("任务存在性查询数量无效", 400, "invalid_query")
        existing = await app["db"].existing_job_ids(job_ids)
        return web.json_response({"ids": [job_id for job_id in job_ids if job_id in existing]})

    async def create_job(request: web.Request) -> web.Response:
        if not request.content_type.startswith("multipart/"):
            return json_error("请求必须使用 multipart/form-data", 415)
        job_id = new_job_id()
        uploaded: list[dict[str, Any]] = []
        fields: dict[str, Any] = {}
        reservation = None
        allowed_text = {"preset_id", "prompt", "duration_seconds", "aspect_ratio", "megapixels", "seed", "scheduler", "sampler", "steps", "retry_source_id", "retry_keep_roles", "values_json"}
        fixed_files = {"first_frame": "first", "last_frame": "last"}
        repeated_files = {"ref_images": ("image", 9), "ref_videos": ("video", 3), "ref_audios": ("audio", 3)}
        slot_files = {**{f"image_{index}": f"image_{index}" for index in range(9)}, **{f"video_{index}": f"video_{index}" for index in range(3)}, **{f"audio_{index}": f"audio_{index}" for index in range(3)}}
        repeated_counts = {name: 0 for name in repeated_files}
        try:
            reservation = await app["files"].reserve_capacity(
                request.content_length or 0, await app["db"].tracked_size(),
                config.minimum_free_bytes, config.output_reserve_bytes, config.max_tracked_bytes,
            )
            reader = await request.multipart()
            async for part in reader:
                if part.name in fixed_files:
                    role = fixed_files[part.name]
                    if any(item["role"] == role for item in uploaded):
                        raise PresetError("同一帧只能上传一张图片")
                    if not part.filename:
                        continue
                    uploaded.append(await app["files"].save_upload(job_id, role, part, reservation))
                elif part.name in slot_files:
                    role = slot_files[part.name]
                    if any(item["role"] == role for item in uploaded):
                        raise PresetError(f"素材槽位重复：{role}")
                    if part.filename:
                        uploaded.append(await app["files"].save_upload(job_id, role, part, reservation))
                elif part.name in repeated_files:
                    if not part.filename:
                        continue
                    prefix, maximum = repeated_files[part.name]
                    index = repeated_counts[part.name]
                    if index >= maximum:
                        raise PresetError(f"{part.name} 上传数量超过 {maximum}")
                    repeated_counts[part.name] += 1
                    uploaded.append(await app["files"].save_upload(job_id, f"{prefix}_{index}", part, reservation))
                elif part.name in allowed_text:
                    if part.name in fields:
                        raise PresetError(f"字段重复：{part.name}")
                    fields[part.name] = await _read_text_part(part, part.name)
                else:
                    raise PresetError(f"不支持的字段：{part.name}")
            if "values_json" in fields:
                values = json.loads(fields.pop("values_json"))
                if not isinstance(values, dict) or not all(isinstance(key, str) for key in values):
                    raise PresetError("values_json 必须是对象")
                fields.update(values)
            fields["duration_seconds"] = int(fields.get("duration_seconds", "5"))
            fields["megapixels"] = float(fields.get("megapixels", "0.4"))
            if "steps" in fields:
                fields["steps"] = int(fields["steps"])
            seed_value = fields.get("seed")
            if seed_value is None:
                seed_text = ""
            elif isinstance(seed_value, str):
                seed_text = seed_value.strip()
            elif isinstance(seed_value, int) and not isinstance(seed_value, bool):
                seed_text = str(seed_value)
            else:
                raise PresetError("种子必须是整数")
            fields["seed"] = seed_text or None
            fields["_capacity_reservation"] = reservation
            job = await app["jobs"].create(fields, uploaded, job_id)
            return web.json_response(app["jobs"].public_job(job), status=201)
        except StorageCapacityError as exc:
            app["files"].cleanup_untracked(uploaded)
            return json_error(str(exc), 507, "insufficient_storage")
        except TextFieldTooLarge as exc:
            app["files"].cleanup_untracked(uploaded)
            return json_error(str(exc), 413, "field_too_large")
        except (ValueError, PresetError, FileValidationError) as exc:
            app["files"].cleanup_untracked(uploaded)
            return json_error(str(exc), 400, "validation_error")
        except ComfyError as exc:
            app["files"].cleanup_untracked(uploaded)
            return json_error(str(exc), 503, "comfyui_unavailable")
        finally:
            if reservation is not None:
                await reservation.release()

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
        enabled = {item["id"] for item in await app["db"].list_workflows() if item["status"] == "enabled"}
        return web.json_response({"items": [
            preset.public_metadata()
            for preset in app["presets"].values()
            if preset.id in enabled and str(preset.manifest.get("family", "")).lower() != "fl2va"
        ]})

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

    async def purge_job(request: web.Request) -> web.Response:
        try:
            body = await request.json()
        except (json.JSONDecodeError, web.HTTPBadRequest):
            body = None
        if not isinstance(body, dict) or body.get("confirm") is not True:
            return json_error("清理本地产物需要 confirm=true", 400, "confirmation_required")
        try:
            await app["jobs"].purge(request.match_info["job_id"])
        except KeyError:
            return json_error("任务不存在", 404, "not_found")
        except PresetError as exc:
            return json_error(str(exc), 409, "invalid_state")
        except (OSError, FileValidationError):
            return json_error("清理失败，任务记录已保留", 500, "purge_failed")
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
        subscription = app["events"].open_subscription()
        snapshot_sequence = app["events"].sequence
        pending: asyncio.Task | None = None
        try:
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
            iterator = subscription.__aiter__()
            pending = asyncio.create_task(iterator.__anext__())
            while True:
                done, _ = await asyncio.wait({pending}, timeout=_SSE_HEARTBEAT_SECONDS)
                if not done:
                    await response.write(b": heartbeat\n\n")
                    continue
                try:
                    event = pending.result()
                except StopAsyncIteration:
                    break
                pending = asyncio.create_task(iterator.__anext__())
                if int(event.get("sequence", 0)) <= snapshot_sequence:
                    continue
                await _write_sse(response, event["type"], event["data"])
        except (ConnectionResetError, asyncio.CancelledError, StopAsyncIteration):
            pass
        finally:
            if pending is not None and not pending.done():
                pending.cancel()
                await asyncio.gather(pending, return_exceptions=True)
            await subscription.aclose()
        return response

    async def video(request: web.Request) -> web.StreamResponse:
        job = await app["db"].get_job(request.match_info["job_id"])
        if job is None:
            return json_error("任务不存在", 404, "video_unavailable")
        output = next((file for file in job["files"] if file["role"] == "output"), None)
        if output is None:
            return json_error("视频尚不可用", 404, "video_unavailable")
        try:
            path = app["files"].validate_output_file(Path(output["path"]))
        except (OSError, FileValidationError):
            return json_error("视频文件不存在或路径无效", 404, "video_unavailable")
        download_name = _download_filename(job) if request.query.get("download") == "1" else None
        return await _stream_file(request, path, download_name)

    async def list_artifacts(request: web.Request) -> web.Response:
        if await app["db"].get_job(request.match_info["job_id"]) is None:
            return json_error("任务不存在", 404, "not_found")
        artifacts = await app["db"].list_artifacts(request.match_info["job_id"])
        return web.json_response({"items": [
            {key: value for key, value in artifact.items() if key != "path"}
            for artifact in artifacts
        ]})

    async def artifact(request: web.Request) -> web.StreamResponse:
        try:
            artifact_id = int(request.match_info["artifact_id"])
        except ValueError:
            return json_error("结果编号无效", 400, "validation_error")
        item = await app["db"].get_artifact(request.match_info["job_id"], artifact_id)
        if item is None or item["direction"] != "output":
            return json_error("结果不存在", 404, "not_found")
        try:
            path = app["files"].validate_artifact_file(Path(item["path"]))
        except (OSError, FileValidationError):
            return json_error("结果文件不存在或路径无效", 404, "not_found")
        name = item.get("original_name") or path.name
        return await _stream_file(request, path, name)

    async def list_workflows(_: web.Request) -> web.Response:
        items = await app["db"].list_workflows()
        return web.json_response({"items": [
            {key: value for key, value in item.items() if key != "definition"}
            | {"manifest": item["definition"]["manifest"]}
            for item in items
        ]})

    async def get_workflow(request: web.Request) -> web.Response:
        item = await app["db"].get_workflow(request.match_info["workflow_id"])
        return web.json_response(item) if item else json_error("工作流不存在", 404, "not_found")

    async def inspect_workflow(request: web.Request) -> web.Response:
        if request.content_length and request.content_length > MAX_WORKFLOW_BYTES:
            return json_error("工作流 JSON 不能超过 4MB", 413, "too_large")
        try:
            workflow = parse_json_bytes(await request.read())
            result = inspect_api_workflow(workflow)
            schemas = {}
            for node_type in sorted({node["class_type"] for node in result["nodes"]}):
                try:
                    schemas[node_type] = await app["comfy"].object_info(node_type)
                except ComfyError:
                    schemas[node_type] = None
            result["object_info"] = schemas
            return web.json_response(result)
        except PresetError as exc:
            return json_error(str(exc), 400, "validation_error")

    async def save_workflow(request: web.Request) -> web.Response:
        try:
            payload = await request.json()
            config_payload = payload.get("config")
            workflow_id = config_payload.get("id") if isinstance(config_payload, dict) else None
            existing = await app["db"].get_workflow(workflow_id) if isinstance(workflow_id, str) else None
            expected_revision = payload.get("expected_revision")
            if existing is not None:
                if expected_revision is None:
                    return json_error(
                        "该工作流 ID 已存在；新导入不会覆盖现有工作流，请改名或从现有工作流进入高级映射编辑",
                        409, "workflow_exists",
                    )
                try:
                    expected_revision = int(expected_revision)
                except (TypeError, ValueError):
                    return json_error("编辑 revision 无效", 409, "workflow_revision_conflict")
                if int(existing["revision"]) != expected_revision:
                    return json_error("工作流已被更新，请重新打开后再编辑", 409, "workflow_revision_conflict")
            elif expected_revision is not None:
                return json_error("要编辑的工作流不存在", 409, "workflow_revision_conflict")
            definition = build_definition(payload.get("workflow"), config_payload)
            item = await app["db"].save_workflow(definition, status="draft")
            return web.json_response(item, status=201)
        except (json.JSONDecodeError, TypeError, AttributeError, PresetError) as exc:
            return json_error(str(exc), 400, "validation_error")

    async def set_workflow_status(request: web.Request) -> web.Response:
        workflow_id = request.match_info["workflow_id"]
        try:
            payload = await request.json()
            status = payload.get("status")
            item = await app["db"].set_workflow_status(workflow_id, status)
            if item is None:
                return json_error("工作流不存在", 404, "not_found")
            if status == "enabled":
                preset = preset_from_definition(item["definition"], config.workflow_dir / workflow_id)
                try:
                    await app["comfy"].validate_preset(preset)
                except ComfyError:
                    pass
                app["presets"][workflow_id] = preset
            return web.json_response(item)
        except (ValueError, AttributeError, PresetError) as exc:
            return json_error(str(exc), 400, "validation_error")

    async def test_workflow(request: web.Request) -> web.Response:
        workflow_id = request.match_info["workflow_id"]
        item = await app["db"].get_workflow(workflow_id)
        if item is None:
            return json_error("工作流不存在", 404, "not_found")
        try:
            values = await request.json()
            preset = preset_from_definition(item["definition"], config.workflow_dir / workflow_id)
            app["presets"][workflow_id] = preset
            await app["comfy"].validate_preset(preset)
            job = await app["jobs"].create({"preset_id": workflow_id, **values}, [], is_test=True)
            return web.json_response(app["jobs"].public_job(job), status=201)
        except (PresetError, ComfyError, ValueError, TypeError) as exc:
            return json_error(str(exc), 400 if isinstance(exc, (PresetError, ValueError)) else 503, "workflow_test_failed")

    async def export_workflow(request: web.Request) -> web.Response:
        item = await app["db"].get_workflow(request.match_info["workflow_id"])
        if item is None:
            return json_error("工作流不存在", 404, "not_found")
        payload = export_package(item["definition"])
        return web.Response(
            body=payload, content_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{item["id"]}-r{item["revision"]}.zip"'},
        )

    async def import_workflow_package(request: web.Request) -> web.Response:
        if request.content_length and request.content_length > MAX_PACKAGE_BYTES:
            return json_error("工作流包不能超过 8MB", 413, "too_large")
        try:
            definition = import_package(await request.read())
            workflow_id = str(definition["manifest"]["id"])
            if await app["db"].get_workflow(workflow_id) is not None:
                return json_error(
                    "该工作流 ID 已存在；导入 Package 不会覆盖现有工作流",
                    409, "workflow_exists",
                )
            item = await app["db"].save_workflow(definition, status="draft")
            return web.json_response(item, status=201)
        except PresetError as exc:
            return json_error(str(exc), 400, "validation_error")

    async def copy_workflow(request: web.Request) -> web.Response:
        source = await app["db"].get_workflow(request.match_info["workflow_id"])
        if source is None:
            return json_error("工作流不存在", 404, "not_found")
        try:
            payload = await request.json()
            definition = json.loads(json.dumps(source["definition"]))
            definition["manifest"]["id"] = payload["id"]
            definition["manifest"]["name"] = payload["name"]
            definition["manifest"]["revision"] = 1
            preset_from_definition(definition)
            item = await app["db"].save_workflow(definition, status="draft")
            return web.json_response(item, status=201)
        except (KeyError, TypeError, PresetError) as exc:
            return json_error(str(exc), 400, "validation_error")

    async def delete_workflow(request: web.Request) -> web.Response:
        workflow_id = request.match_info["workflow_id"]
        item = await app["db"].get_workflow(workflow_id)
        if item is None:
            return json_error("工作流不存在", 404, "not_found")
        if item["builtin"]:
            return json_error("内置工作流不能删除", 409, "builtin_workflow")
        async with app["db"]._lock:
            with app["db"]._connect() as db:
                db.execute("DELETE FROM workflows WHERE id = ?", (workflow_id,))
        app["presets"].pop(workflow_id, None)
        return web.Response(status=204)

    app.router.add_get("/healthz", healthz)
    app.router.add_get("/", index)
    app.router.add_static("/static", static_dir, show_index=False)
    app.router.add_get("/api/jobs", list_jobs)
    app.router.add_post("/api/jobs", create_job)
    app.router.add_get("/api/presets", list_presets)
    app.router.add_get("/api/jobs/existence", existing_jobs)
    app.router.add_get("/api/jobs/{job_id}", get_job)
    app.router.add_post("/api/jobs/{job_id}/cancel", cancel_job)
    app.router.add_post("/api/jobs/{job_id}/retry", retry_job)
    app.router.add_delete("/api/jobs/{job_id}", delete_job)
    app.router.add_post("/api/jobs/{job_id}/purge", purge_job)
    app.router.add_get("/api/jobs/{job_id}/video", video)
    app.router.add_get("/api/jobs/{job_id}/artifacts", list_artifacts)
    app.router.add_get("/api/jobs/{job_id}/artifacts/{artifact_id}", artifact)
    app.router.add_get("/api/workflows", list_workflows)
    app.router.add_post("/api/workflows", save_workflow)
    app.router.add_post("/api/workflows/inspect", inspect_workflow)
    app.router.add_post("/api/workflows/import", import_workflow_package)
    app.router.add_get("/api/workflows/{workflow_id}", get_workflow)
    app.router.add_post("/api/workflows/{workflow_id}/status", set_workflow_status)
    app.router.add_post("/api/workflows/{workflow_id}/test", test_workflow)
    app.router.add_post("/api/workflows/{workflow_id}/copy", copy_workflow)
    app.router.add_get("/api/workflows/{workflow_id}/export", export_workflow)
    app.router.add_delete("/api/workflows/{workflow_id}", delete_workflow)
    app.router.add_get("/api/metrics", metrics)
    app.router.add_post("/api/comfyui/control/{action}", control_comfyui)
    app.router.add_get("/api/events", events)

    async def startup(_: web.Application) -> None:
        config.data_dir.mkdir(parents=True, exist_ok=True)
        app["files"].initialize()
        await app["db"].initialize()
        for preset in list(app["presets"].values()):
            await app["db"].save_workflow(preset.snapshot(), status="enabled", builtin=True)
        await app["db"].backfill_legacy_workflows({
            preset.id: preset.snapshot() for preset in app["presets"].values()
        })
        for item in await app["db"].list_workflows():
            if not item["builtin"]:
                app["presets"][item["id"]] = preset_from_definition(
                    item["definition"], config.workflow_dir / item["id"]
                )
        migration = await app["files"].migrate_legacy(await app["db"].tracked_files())
        for change in migration:
            path = Path(change["new_path"])
            await app["db"].update_file_path(change["job_id"], change["role"], path, path.stat().st_size)
        if migration:
            log.info("flattened %d tracked legacy files", len(migration))
        orphan_report = await app["files"].scan_orphans(await app["db"].tracked_paths())
        if orphan_report:
            log.warning("orphan dry-run found %d app-owned paths; nothing was deleted", len(orphan_report))
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


async def _read_text_part(part: Any, field_name: str) -> str:
    byte_limit = MAX_PROMPT_BYTES if field_name == "prompt" else MAX_TEXT_FIELD_BYTES
    char_limit = MAX_PROMPT_CHARS if field_name == "prompt" else MAX_TEXT_FIELD_CHARS
    payload = bytearray()
    while True:
        chunk = await part.read_chunk(4096)
        if not chunk:
            break
        payload.extend(chunk)
        if len(payload) > byte_limit:
            raise TextFieldTooLarge(f"字段 {field_name} 超过 {byte_limit} 字节限制")
    try:
        value = payload.decode(part.get_charset(default="utf-8"))
    except (UnicodeDecodeError, LookupError) as exc:
        raise ValueError(f"字段 {field_name} 不是有效 UTF-8 文本") from exc
    if len(value) > char_limit:
        raise TextFieldTooLarge(f"字段 {field_name} 超过 {char_limit} 字符限制")
    return value


def _download_filename(job: dict[str, Any]) -> str:
    preset_id = re.sub(r"[^A-Za-z0-9._-]+", "-", str(job.get("preset_id") or "h3")).strip("-.") or "h3"
    stamp = datetime.fromtimestamp(float(job["created_at"])).strftime("%Y%m%d-%H%M%S")
    short_id = re.sub(r"[^0-9a-f]", "", str(job["id"]).lower())[:6] or "000000"
    return f"{preset_id}-{stamp}-{short_id}.mp4"


async def _stream_file(request: web.Request, path: Path, download_name: str | None = None) -> web.StreamResponse:
    size = (await asyncio.to_thread(path.stat)).st_size
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
        "Content-Disposition": f'{disposition}; filename="{download_name or path.name}"',
    }
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{size}"
    response = web.StreamResponse(status=status, headers=headers)
    await response.prepare(request)
    if request.method != "HEAD":
        handle = await asyncio.to_thread(path.open, "rb")
        try:
            await asyncio.to_thread(handle.seek, start)
            remaining = length
            while remaining:
                chunk = await asyncio.to_thread(handle.read, min(1024 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                await response.write(chunk)
        finally:
            await asyncio.to_thread(handle.close)
    await response.write_eof()
    return response
