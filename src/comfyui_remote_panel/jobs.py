from __future__ import annotations

import asyncio
import logging
import re
import secrets
import time
import uuid
from pathlib import Path
from typing import Any

from .comfy import ComfyClient, ComfyError
from .db import ACTIVE_STATUSES, TERMINAL_STATUSES, Database
from .events import EventBus
from .files import FileStore, FileValidationError
from .preset import Preset, PresetError


log = logging.getLogger(__name__)

_LOCAL_PATH = re.compile(r"(?i)(?:\b[a-z]:[\\/]|\\\\|/(?:home|root|users|mnt|opt|var|tmp)/)[^\s\"']+")
_IP_ADDRESS = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?(?![\d.])")


def safe_summary(value: Any, fallback: str = "ComfyUI 执行失败，请检查本机日志") -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return fallback
    text = _LOCAL_PATH.sub("[本机路径]", text)
    text = _IP_ADDRESS.sub("[本机地址]", text)
    return text[:500]


def new_job_id() -> str:
    return str(uuid.uuid4())


class JobService:
    def __init__(self, db: Database, files: FileStore, comfy: ComfyClient, presets: dict[str, Preset], events: EventBus):
        self.db = db
        self.files = files
        self.comfy = comfy
        self.presets = presets
        self.events = events
        self._stop = asyncio.Event()
        self._last_output_recovery = 0.0

    async def create(self, fields: dict[str, Any], uploaded: list[dict[str, Any]], job_id: str | None = None) -> dict[str, Any]:
        job_id = job_id or new_job_id()
        preset_id = fields.get("preset_id") or "h3-fl2va-v4step600"
        preset = self.presets.get(preset_id)
        if preset is None:
            raise PresetError("未知工作流预设")
        if not preset.available:
            # Startup deliberately does not wait for ComfyUI. If a user submits
            # before the background capability check finishes, do that check on
            # demand so an online ComfyUI is still usable immediately.
            await self.comfy.validate_preset(preset)
        if not preset.available:
            diagnostics = "；".join(preset.diagnostics[:3]) or "尚未完成在线检查"
            raise ComfyError("工作流预设当前不可用：" + diagnostics)
        normalized = preset.validate_parameters(fields)
        seed = normalized.get("seed")
        if seed is None:
            seed = str(secrets.randbits(64))
            normalized["seed"] = seed
        effective_uploads = list(uploaded)
        copied: list[dict[str, Any]] = []
        try:
            retry_source_id = fields.get("retry_source_id")
            if retry_source_id:
                source = await self.db.get_job(str(retry_source_id))
                if source is None or source["status"] not in TERMINAL_STATUSES:
                    raise PresetError("原任务不存在或尚未结束，无法沿用参考图")
                supplied_roles = {item["role"] for item in effective_uploads}
                supplied_kinds = {self.files.role_kind(role) for role in supplied_roles}
                for file in source["files"]:
                    role = file["role"]
                    kind = self.files.role_kind(role)
                    compatible = role in {"first", "last"} if preset.manifest.get("family") != "ref2va" else kind is not None
                    replaced = role in supplied_roles if preset.manifest.get("family") != "ref2va" else kind in supplied_kinds
                    if compatible and not replaced:
                        copied_file = self.files.copy_input(Path(file["path"]), job_id, file["role"])
                        copied.append(copied_file)
                        effective_uploads.append(copied_file)
            roles = {file["role"] for file in effective_uploads}
            if preset.manifest.get("family") == "ref2va":
                limits = preset.manifest["reference_media"]
                counts = {
                    kind: sum(self.files.role_kind(role) == kind for role in roles)
                    for kind in ("image", "video", "audio")
                }
                if any(self.files.role_kind(role) is None for role in roles):
                    raise PresetError("Ref2VA 收到了不支持的参考素材")
                if counts["image"] > limits["images"]["max"] or counts["video"] > limits["videos"]["max"] or counts["audio"] > limits["audios"]["max"]:
                    raise PresetError("参考素材数量超过工作流允许范围")
                mode = " · ".join(f"{counts[kind]}{label}" for kind, label in (("image", "图"), ("video", "视频"), ("audio", "音频")) if counts[kind]) or "纯文字"
            else:
                if roles - {"first", "last"}:
                    raise PresetError("FL2VA 仅支持首帧和尾帧")
                mode = {frozenset(): "纯文字", frozenset({"first"}): "仅首帧", frozenset({"last"}): "仅尾帧", frozenset({"first", "last"}): "首尾帧"}[frozenset(roles)]
            has_image = any(self.files.role_kind(role) == "image" for role in roles)
            if normalized.get("aspect_ratio") == "reference" and not has_image:
                raise PresetError("参考图比例需要至少上传一张参考图")
            record = {
                "id": job_id,
                "preset_id": preset_id,
                "status": "submitting",
                "mode": mode,
                **normalized,
            }
            await self.db.create_job(record, effective_uploads)
            media_names = {file["role"]: self.files.comfy_input_name(Path(file["path"])) for file in effective_uploads}
            prompt = preset.build_prompt(normalized, job_id, media_names)
            await self.comfy.submit(job_id, prompt)
            _, job = await self.db.update_job_if_status(
                job_id, {"submitting"}, status="queued", stage="等待执行", queue_position=None
            )
        except (PresetError, FileValidationError):
            self.files.cleanup_untracked(copied)
            raise
        except Exception as exc:
            summary = safe_summary(exc, "任务提交失败")
            _, job = await self.db.update_job_if_status(
                job_id, {"submitting"},
                status="failed",
                error_code="submission_failed",
                error_summary=summary,
                finished_at=time.time(),
            )
        self.events.publish("job", self.public_job(job))
        return job

    async def retry(self, job_id: str) -> dict[str, Any]:
        original = await self.db.get_job(job_id)
        if original is None:
            raise KeyError(job_id)
        if original["status"] not in TERMINAL_STATUSES:
            raise PresetError("只有已结束任务可以重试")
        return {
            "retry_source_id": original["id"],
            "preset_id": original["preset_id"],
            "prompt": original["prompt"],
            "duration_seconds": original["duration_seconds"],
            "aspect_ratio": original["aspect_ratio"],
            "megapixels": original["megapixels"],
            "seed": original["seed"],
            "scheduler": original["scheduler"],
            "sampler": original["sampler"],
            "steps": original["steps"],
            "input_roles": [file["role"] for file in original["files"] if self.files.role_kind(file["role"]) is not None],
        }

    async def cancel(self, job_id: str) -> dict[str, Any]:
        job = await self.db.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        if job["status"] in TERMINAL_STATUSES:
            return job
        acted = await self.comfy.cancel(job_id)
        if acted:
            updated, job = await self.db.update_job_if_status(
                job_id, ACTIVE_STATUSES, status="cancelled", stage="已取消",
                finished_at=time.time(), queue_position=None,
            )
            if updated:
                self.events.publish("job", self.public_job(job))
        return job

    async def delete(self, job_id: str) -> None:
        job = await self.db.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        if job["status"] not in TERMINAL_STATUSES:
            raise PresetError("运行中或排队中的任务不能删除")
        await self.db.update_job(job_id, status="deleting", stage="正在删除")
        try:
            for file in job["files"]:
                path = Path(file["path"])
                if path.exists():
                    self.files.delete_exact(path, file["role"])
            await self.db.delete_job(job_id)
        except Exception:
            await self.db.update_job(job_id, status=job["status"], stage="删除失败", error_code="delete_failed", error_summary="部分文件删除失败，请检查权限后重试")
            raise
        self.events.publish("job_deleted", {"id": job_id})

    async def reconcile_once(self) -> None:
        active = await self.db.active_jobs()
        if active:
            queue = await self.comfy.queue()
            running = {str(item[1]) for item in queue.get("queue_running", []) if isinstance(item, list) and len(item) > 1}
            pending_list = [str(item[1]) for item in queue.get("queue_pending", []) if isinstance(item, list) and len(item) > 1]
            pending = set(pending_list)
            for job in active:
                job_id = job["id"]
                if job_id in running:
                    values: dict[str, Any] = {"status": "running", "queue_position": 0}
                    if not job.get("started_at"):
                        values["started_at"] = time.time()
                    updated = await self.db.update_active_job(job_id, **values)
                elif job_id in pending:
                    updated = await self.db.update_active_job(job_id, status="queued", stage="等待执行", queue_position=pending_list.index(job_id) + 1)
                else:
                    history = await self.comfy.history(job_id)
                    entry = history.get(job_id) if isinstance(history, dict) else None
                    if entry:
                        updated = await self._apply_history(job, entry)
                    else:
                        updated = await self.db.update_active_job(job_id, status="interrupted", stage="意外中断", error_code="missing_upstream", error_summary="ComfyUI 中找不到这个未完成任务", finished_at=time.time(), queue_position=None)
                self.events.publish("job", self.public_job(updated))
        if time.time() - self._last_output_recovery >= 30:
            self._last_output_recovery = time.time()
            await self._recover_missing_outputs()

    async def _apply_history(self, job: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
        current = await self.db.get_job(job["id"])
        if current is None or current["status"] in TERMINAL_STATUSES:
            return current
        status_data = entry.get("status", {})
        status_text = str(status_data.get("status_str", "")).lower()
        completed = status_data.get("completed")
        message_types = {
            str(message[0]) for message in status_data.get("messages", [])
            if isinstance(message, list) and message
        }
        if "execution_interrupted" in message_types:
            status = "cancelled"
            error_code = error_summary = None
        elif completed or status_text in {"success", "succeeded", "completed"}:
            status = "succeeded"
            error_code = error_summary = None
        elif status_text in {"cancelled", "canceled", "interrupted"}:
            status = "cancelled"
            error_code = error_summary = None
        else:
            status = "failed"
            error_code = "execution_failed"
            error_summary = self._history_error(status_data)
        if status == "succeeded":
            await self._capture_output(job["id"], entry)
        return await self.db.update_active_job(
            job["id"], status=status, stage={"succeeded": "已完成", "failed": "失败", "cancelled": "已取消"}[status],
            finished_at=time.time(), queue_position=None, error_code=error_code, error_summary=error_summary,
        )

    @staticmethod
    def _history_error(status_data: dict[str, Any]) -> str:
        messages = status_data.get("messages", [])
        for message in reversed(messages if isinstance(messages, list) else []):
            if isinstance(message, list) and len(message) > 1 and isinstance(message[1], dict):
                value = message[1].get("exception_message") or message[1].get("exception_type")
                if isinstance(value, str):
                    return safe_summary(value)
        return "ComfyUI 执行失败，请检查本机日志"

    async def _capture_output(self, job_id: str, entry: dict[str, Any]) -> bool:
        preset = self.presets[(await self.db.get_job(job_id))["preset_id"]]
        output = entry.get("outputs", {}).get(preset.output_node, {})
        descriptors: list[dict[str, Any]] = []
        for key in ("videos", "video", "files", "images"):
            value = output.get(key)
            if isinstance(value, list):
                descriptors.extend(item for item in value if isinstance(item, dict))
            elif isinstance(value, dict):
                descriptors.append(value)
        for descriptor in descriptors:
            try:
                path = self.files.register_output(job_id, descriptor)
            except (FileValidationError, OSError):
                continue
            await self.db.add_file(job_id, "output", path, path.stat().st_size)
            return True
        return False

    async def _recover_missing_outputs(self) -> None:
        for job in await self.db.succeeded_without_output():
            history = await self.comfy.history(job["id"])
            entry = history.get(job["id"]) if isinstance(history, dict) else None
            if isinstance(entry, dict) and await self._capture_output(job["id"], entry):
                updated = await self.db.get_job(job["id"])
                self.events.publish("job", self.public_job(updated))

    async def handle_ws_event(self, event: dict[str, Any]) -> None:
        event_type = event.get("type")
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        job_id = data.get("prompt_id")
        if not isinstance(job_id, str):
            return
        job = await self.db.get_job(job_id)
        if job is None:
            return
        if job["status"] in TERMINAL_STATUSES:
            return
        preset = self.presets[job["preset_id"]]
        updated = None
        if event_type in {"execution_start", "executing"}:
            node = str(data.get("node")) if data.get("node") is not None else None
            values: dict[str, Any] = {"status": "running", "queue_position": 0}
            if node:
                values["stage"] = preset.stages.get(node, "运行中")
            if not job.get("started_at"):
                values["started_at"] = time.time()
            updated = await self.db.update_active_job(job_id, **values)
        elif event_type == "progress":
            updated = await self.db.update_active_job(job_id, status="running", stage="采样", progress_value=int(data.get("value", 0)), progress_max=int(data.get("max", 0)))
        elif event_type == "execution_success":
            try:
                history = await self.comfy.history(job_id)
                entry = history.get(job_id, {})
                updated = await self._apply_history(job, entry)
            except ComfyError:
                return
        elif event_type == "execution_error":
            summary = safe_summary(data.get("exception_message") or data.get("exception_type"))
            updated = await self.db.update_active_job(job_id, status="failed", stage="失败", error_code="execution_failed", error_summary=summary, finished_at=time.time(), queue_position=None)
        elif event_type == "execution_interrupted":
            updated = await self.db.update_active_job(job_id, status="cancelled", stage="已取消", finished_at=time.time(), queue_position=None)
        if updated:
            self.events.publish("job", self.public_job(updated))

    async def reconcile_loop(self, interval: float = 3.0) -> None:
        while not self._stop.is_set():
            try:
                await self.reconcile_once()
            except ComfyError:
                pass
            except Exception:
                log.exception("job reconciliation failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    async def websocket_loop(self) -> None:
        while not self._stop.is_set():
            try:
                async for event in self.comfy.websocket_events():
                    await self.handle_ws_event(event)
            except ComfyError:
                pass
            except Exception:
                log.exception("ComfyUI WebSocket loop failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=2)
            except asyncio.TimeoutError:
                pass

    def stop(self) -> None:
        self._stop.set()

    def public_job(self, job: dict[str, Any] | None) -> dict[str, Any] | None:
        if job is None:
            return None
        result = {key: value for key, value in job.items() if key != "files"}
        result["seed"] = str(result["seed"])
        preset = self.presets.get(job["preset_id"])
        result["preset_name"] = preset.manifest["name"] if preset else job["preset_id"]
        input_files = [file for file in job.get("files", []) if self.files.role_kind(file["role"]) is not None]
        result["input_count"] = len(input_files)
        result["media_counts"] = {
            kind: sum(self.files.role_kind(file["role"]) == kind for file in input_files)
            for kind in ("image", "video", "audio")
        }
        return result
