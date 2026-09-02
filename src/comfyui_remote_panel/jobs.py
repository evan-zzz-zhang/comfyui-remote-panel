from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
import re
import secrets
import time
import uuid
from pathlib import Path
from typing import Any

from .comfy import ComfyClient, ComfyError
from .db import ACTIVE_STATUSES, HIDDEN_STATUS, TERMINAL_STATUSES, Database
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
    _PROGRESS_STARTS = {"build": 0, "sampling": 10, "decode": 70, "compose": 85, "save": 95}
    _PROGRESS_WEIGHTS = {"build": 10, "sampling": 60, "decode": 15, "compose": 10, "save": 5}
    _SUBMISSION_CONFIRMATION_TIMEOUT = 60.0
    _MISSING_CONFIRMATIONS = 3
    _MISSING_GRACE_SECONDS = 30.0

    def __init__(self, db: Database, files: FileStore, comfy: ComfyClient, presets: dict[str, Preset], events: EventBus):
        self.db = db
        self.files = files
        self.comfy = comfy
        self.presets = presets
        self.events = events
        self._stop = asyncio.Event()
        self._last_output_recovery = 0.0

    async def create(
        self, fields: dict[str, Any], uploaded: list[dict[str, Any]],
        job_id: str | None = None, *, is_test: bool = False,
    ) -> dict[str, Any]:
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
        effective_uploads = list(uploaded)
        copied: list[dict[str, Any]] = []
        persisted = False
        try:
            retry_source_id = fields.get("retry_source_id")
            if retry_source_id:
                source = await self.db.get_job(str(retry_source_id))
                if source is None or source["status"] not in TERMINAL_STATUSES:
                    raise PresetError("原任务不存在或尚未结束，无法沿用参考图")
                keep_roles: set[str] | None = None
                if fields.get("retry_keep_roles") is not None:
                    try:
                        raw_keep_roles = json.loads(str(fields["retry_keep_roles"]))
                    except (TypeError, json.JSONDecodeError) as exc:
                        raise PresetError("retry_keep_roles 必须是 JSON 数组") from exc
                    if not isinstance(raw_keep_roles, list) or any(not isinstance(role, str) for role in raw_keep_roles):
                        raise PresetError("retry_keep_roles 必须是 JSON 字符串数组")
                    keep_roles = set(raw_keep_roles)
                    source_roles = {file["role"] for file in source["files"] if self.files.role_kind(file["role"]) is not None}
                    if not keep_roles <= source_roles:
                        raise PresetError("retry_keep_roles 包含原任务不存在的素材槽位")
                supplied_roles = {item["role"] for item in effective_uploads}
                supplied_kinds = {self.files.role_kind(role) for role in supplied_roles}
                for file in source["files"]:
                    role = file["role"]
                    kind = self.files.role_kind(role)
                    compatible = preset.retry_role_compatible(role)
                    if keep_roles is not None:
                        should_copy = role in keep_roles
                    else:
                        replaced = role in supplied_roles if preset.media_binding["type"] in {"frame_pair", "slots"} else kind in supplied_kinds
                        should_copy = not replaced
                    if compatible and should_copy and role not in supplied_roles:
                        copied_file = await self.files.copy_input_async(Path(file["path"]), job_id, file["role"])
                        copied.append(copied_file)
                        effective_uploads.append(copied_file)
            roles = {file["role"] for file in effective_uploads}
            mode, allow_empty_prompt = preset.validate_media_roles(roles)
            normalized = preset.validate_parameters(fields, allow_empty_prompt=allow_empty_prompt)
            # Workflow-family selectors are routing metadata rather than
            # workflow parameters.  Preserve the resolved values in the
            # existing JSON payload without changing the jobs table schema.
            for metadata_key in (
                "_v047_prompt_backend",
                "_v047_inference_profile",
                "_v047_effective_inference_profile",
                "_v048_generation_mode",
                "_v048_prompt_backend",
                "_v048_inference_profile",
                "_v048_effective_inference_profile",
                "_v048_variant_model_overrides",
            ):
                if metadata_key in fields:
                    normalized[metadata_key] = fields[metadata_key]
            seed = normalized.get("seed")
            if seed is None:
                seed = str(secrets.randbits(64))
                normalized["seed"] = seed
            has_image = any(self.files.role_kind(role) == "image" for role in roles)
            if normalized.get("aspect_ratio") == "reference" and not has_image:
                raise PresetError("参考图比例需要至少上传一张参考图")
            record = {
                "id": job_id,
                "preset_id": preset_id,
                "workflow_id": preset_id,
                "workflow_revision": preset.revision,
                "workflow_snapshot": preset.snapshot(),
                "input_values": normalized,
                "is_test": is_test,
                "status": "submitting",
                "mode": mode,
                **normalized,
            }
            await self.db.create_job(record, effective_uploads)
            persisted = True
            media_names = {file["role"]: self.files.comfy_input_name(Path(file["path"])) for file in effective_uploads}
            variant_model_overrides = fields.get("_v047_variant_model_overrides")
            prompt = preset.build_prompt(
                normalized,
                job_id,
                media_names,
                variant_model_overrides if isinstance(variant_model_overrides, dict) else None,
            )
            await self.comfy.submit(job_id, prompt)
            _, job = await self.db.update_job_if_status(
                job_id, {"submitting"}, status="queued", stage="等待执行", queue_position=None
            )
        except (PresetError, FileValidationError):
            self.files.cleanup_untracked(copied)
            raise
        except Exception as exc:
            if not persisted:
                self.files.cleanup_untracked(copied)
                raise
            summary = safe_summary(exc, "任务提交失败")
            try:
                confirmed, job = await self._confirm_submission(job_id)
            except ComfyError:
                confirmed = False
                job = await self.db.get_job(job_id)
            if not confirmed:
                _, job = await self.db.update_job_if_status(
                    job_id, {"submitting"},
                    status="submitting",
                    stage="确认提交状态",
                    error_code="submission_uncertain",
                    error_summary=None,
                )
            log.warning("ComfyUI submission response could not be trusted for job %s: %s", job_id, summary)
        self.events.publish("job", self.public_job(job))
        return job

    async def _confirm_submission(self, job_id: str) -> tuple[bool, dict[str, Any] | None]:
        """Resolve a submit error without declaring an accepted prompt failed."""
        job = await self.db.get_job(job_id)
        if job is None or job["status"] in TERMINAL_STATUSES:
            return True, job
        queue = await self.comfy.queue()
        running = {str(item[1]) for item in queue.get("queue_running", []) if isinstance(item, list) and len(item) > 1}
        pending_list = [str(item[1]) for item in queue.get("queue_pending", []) if isinstance(item, list) and len(item) > 1]
        if job_id in running:
            values: dict[str, Any] = {
                "status": "running", "queue_position": 0,
                "missing_observations": 0, "missing_first_at": None,
            }
            if not job.get("started_at"):
                values["started_at"] = time.time()
            return True, await self.db.update_active_job(job_id, **values)
        if job_id in pending_list:
            return True, await self.db.update_active_job(
                job_id, status="queued", stage="等待执行", queue_position=pending_list.index(job_id) + 1,
                missing_observations=0, missing_first_at=None,
            )
        history = await self.comfy.history(job_id)
        entry = history.get(job_id) if isinstance(history, dict) else None
        if entry:
            current = await self.db.get_job(job_id)
            if current is None:
                return True, None
            return True, await self._apply_history(current, entry)
        return False, job

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
            "retry_keep_roles": [file["role"] for file in original["files"] if self.files.role_kind(file["role"]) is not None],
            "values": original.get("input_values", {}),
        }

    async def cancel(self, job_id: str) -> dict[str, Any]:
        job = await self.db.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        if job["status"] in TERMINAL_STATUSES:
            return job
        requested_at = time.time()
        job = await self.db.update_active_job(job_id, cancel_requested_at=requested_at)
        acted = await self.comfy.cancel(job_id)
        if acted:
            updated, job = await self.db.update_job_if_status(
                job_id, ACTIVE_STATUSES, status="cancelled", stage="已取消",
                finished_at=time.time(), queue_position=None, cancel_requested_at=requested_at,
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

        await self.db.update_job(job_id, status=HIDDEN_STATUS, stage="已从历史隐藏")
        self.events.publish("job_deleted", {"id": job_id})

    async def purge(self, job_id: str) -> None:
        job = await self.db.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        if job["status"] not in TERMINAL_STATUSES | {HIDDEN_STATUS}:
            raise PresetError("运行中或排队中的任务不能清理文件")
        try:
            for file in job["files"]:
                path = Path(file["path"])
                if path.exists():
                    self.files.delete_exact(path, file["role"])
            await self.db.delete_job(job_id)
        except Exception:
            await self.db.update_job(job_id, status=job["status"], stage="清理失败", error_code="purge_failed", error_summary="部分文件清理失败，请检查权限后重试")
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
                    values: dict[str, Any] = {
                        "status": "running", "queue_position": 0,
                        "missing_observations": 0, "missing_first_at": None,
                    }
                    if not job.get("started_at"):
                        values["started_at"] = time.time()
                    updated = await self.db.update_active_job(job_id, **values)
                elif job_id in pending:
                    updated = await self.db.update_active_job(
                        job_id, status="queued", stage="等待执行",
                        queue_position=pending_list.index(job_id) + 1,
                        missing_observations=0, missing_first_at=None,
                    )
                else:
                    history = await self.comfy.history(job_id)
                    entry = history.get(job_id) if isinstance(history, dict) else None
                    if entry:
                        updated = await self._apply_history(job, entry)
                    elif job["status"] == "submitting" and time.time() - job["created_at"] < self._SUBMISSION_CONFIRMATION_TIMEOUT:
                        updated = await self.db.update_active_job(job_id, status="submitting", stage="确认提交状态", error_code="submission_uncertain", error_summary=None)
                    elif job["status"] == "submitting":
                        updated = await self.db.update_active_job(job_id, status="failed", stage="提交失败", error_code="submission_unconfirmed", error_summary="提交响应异常，超过确认时间后仍未在 ComfyUI 中找到任务", finished_at=time.time(), queue_position=None)
                    else:
                        updated = await self._observe_missing(job)
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
            status, error_code, error_summary = self._interruption_result(current)
        elif completed or status_text in {"success", "succeeded", "completed"}:
            status = "succeeded"
            error_code = error_summary = None
        elif status_text in {"cancelled", "canceled", "interrupted"}:
            status, error_code, error_summary = self._interruption_result(current)
        else:
            status = "failed"
            error_code = "execution_failed"
            error_summary = self._history_error(status_data)
        if status == "succeeded":
            await self._capture_output(job["id"], entry)
        return await self.db.update_active_job(
            job["id"], status=status,
            stage={"succeeded": "已完成", "failed": "失败", "cancelled": "已取消", "interrupted": "意外中断"}[status],
            finished_at=time.time(), queue_position=None, error_code=error_code, error_summary=error_summary,
            missing_observations=0, missing_first_at=None,
        )

    @staticmethod
    def _interruption_result(job: dict[str, Any]) -> tuple[str, str | None, str | None]:
        if job.get("cancel_requested_at") is not None:
            return "cancelled", None, None
        return "interrupted", "execution_interrupted", "ComfyUI 执行被意外中断，可检查设备状态后重新提交"

    async def _observe_missing(self, job: dict[str, Any]) -> dict[str, Any] | None:
        now = time.time()
        first_at = float(job.get("missing_first_at") or now)
        observations = int(job.get("missing_observations") or 0) + 1
        confirmed = (
            observations >= self._MISSING_CONFIRMATIONS
            and now - first_at >= self._MISSING_GRACE_SECONDS
        )
        if confirmed:
            return await self.db.update_active_job(
                job["id"], status="interrupted", stage="意外中断",
                error_code="missing_upstream",
                error_summary="连续确认后，ComfyUI 中仍找不到这个未完成任务",
                finished_at=now, queue_position=None,
                missing_observations=observations, missing_first_at=first_at,
            )
        return await self.db.update_active_job(
            job["id"], stage=f"确认任务状态（{observations}）",
            error_code="upstream_temporarily_missing", error_summary=None,
            missing_observations=observations, missing_first_at=first_at,
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

    @staticmethod
    def _progress_number(value: Any, default: int = 0) -> int | float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            return default
        if not number == number or number < 0:
            return default
        return int(number) if number.is_integer() else number

    @staticmethod
    def _progress_node_stage(preset: Preset, node: dict[str, Any], fallback_node_id: Any = None) -> str | None:
        node_ids = (
            node.get("display_node_id"),
            node.get("real_node_id"),
            node.get("node_id"),
            fallback_node_id,
        )
        for node_id in node_ids:
            if node_id is not None:
                stage = preset.stages.get(str(node_id))
                if stage:
                    return stage
        return None

    async def _handle_progress_state(
        self, job_id: str, preset: Preset, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        nodes = data.get("nodes")
        if not isinstance(nodes, dict):
            return None

        candidates: list[tuple[dict[str, Any], Any]] = []
        for node_id, node in nodes.items():
            if isinstance(node, dict) and str(node.get("state", "")).lower() != "pending":
                candidates.append((node, node_id))
        if not candidates:
            return None

        running = [item for item in candidates if str(item[0].get("state", "")).lower() == "running"]
        node, fallback_node_id = (running or candidates)[-1]
        stage = self._progress_node_stage(preset, node, fallback_node_id)
        values: dict[str, Any] = {
            "status": "running",
            "queue_position": 0,
            "progress_value": self._progress_number(node.get("value")),
            "progress_max": self._progress_number(node.get("max")),
            "missing_observations": 0,
            "missing_first_at": None,
        }
        if stage:
            values["stage"] = stage
        return await self.db.update_active_job(job_id, **values)

    async def _capture_output(self, job_id: str, entry: dict[str, Any]) -> bool:
        preset = self.presets[(await self.db.get_job(job_id))["preset_id"]]
        captured = False
        for binding in preset.manifest["output_bindings"]:
            output = entry.get("outputs", {}).get(str(binding["node"]), {})
            descriptors: list[dict[str, Any]] = []
            for key in binding.get("history_keys", ("images", "videos", "files")):
                value = output.get(key)
                if isinstance(value, list):
                    descriptors.extend(item for item in value if isinstance(item, dict))
                elif isinstance(value, dict):
                    descriptors.append(value)
            for ordinal, descriptor in enumerate(descriptors):
                try:
                    path = self.files.register_artifact(
                        job_id, str(binding["id"]), ordinal, descriptor, str(binding["kind"])
                    )
                except (FileValidationError, OSError):
                    continue
                size = path.stat().st_size
                await self.db.add_artifact(
                    job_id, "output", str(binding["id"]), ordinal, path,
                    str(binding["kind"]), mimetypes.guess_type(path.name)[0],
                    descriptor.get("filename"), size,
                )
                if binding.get("primary") and binding["kind"] == "video" and ordinal == 0:
                    await self.db.add_file(job_id, "output", path, size)
                captured = True
        return captured

    async def _recover_missing_outputs(self) -> None:
        for job in await self.db.succeeded_without_output():
            now = time.time()
            attempts = int(job.get("recovery_attempts") or 0) + 1
            age = now - float(job.get("finished_at") or job["created_at"])
            try:
                history = await self.comfy.history(job["id"])
                entry = history.get(job["id"]) if isinstance(history, dict) else None
                if isinstance(entry, dict) and await self._capture_output(job["id"], entry):
                    updated = await self.db.get_job(job["id"])
                    self.events.publish("job", self.public_job(updated))
                    continue
                error = "ComfyUI 历史记录中尚未找到输出文件"
            except ComfyError as exc:
                error = safe_summary(str(exc))
            if attempts >= 8 or age >= 24 * 60 * 60:
                updated = await self.db.update_job(
                    job["id"], status="output_missing", stage="输出缺失",
                    error_code="output_missing", error_summary="多次恢复后仍未找到输出，可人工重试",
                    recovery_attempts=attempts, recovery_next_at=None, recovery_last_error=error,
                )
                self.events.publish("job", self.public_job(updated))
            else:
                delay = min(3600, 30 * 2 ** (attempts - 1))
                await self.db.update_job(
                    job["id"], recovery_attempts=attempts,
                    recovery_next_at=now + delay, recovery_last_error=error,
                )

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
            values: dict[str, Any] = {
                "status": "running", "queue_position": 0,
                "missing_observations": 0, "missing_first_at": None,
            }
            if node:
                values["stage"] = preset.stages.get(node, "运行中")
            if not job.get("started_at"):
                values["started_at"] = time.time()
            updated = await self.db.update_active_job(job_id, **values)
        elif event_type == "progress_state":
            updated = await self._handle_progress_state(job_id, preset, data)
        elif event_type == "progress":
            node = {"node_id": data.get("node")}
            stage = self._progress_node_stage(preset, node) or "采样"
            updated = await self.db.update_active_job(
                job_id,
                status="running",
                stage=stage,
                progress_value=self._progress_number(data.get("value")),
                progress_max=self._progress_number(data.get("max")),
                missing_observations=0,
                missing_first_at=None,
            )
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
            status, error_code, error_summary = self._interruption_result(job)
            updated = await self.db.update_active_job(
                job_id, status=status,
                stage="已取消" if status == "cancelled" else "意外中断",
                error_code=error_code, error_summary=error_summary,
                finished_at=time.time(), queue_position=None,
            )
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
        result = {key: value for key, value in job.items() if key not in {"files", "workflow_snapshot"}}
        result["seed"] = str(result["seed"])
        preset = self.presets.get(job["preset_id"])
        result["preset_name"] = preset.manifest["name"] if preset else job["preset_id"]
        input_files = [file for file in job.get("files", []) if self.files.role_kind(file["role"]) is not None]
        result["input_count"] = len(input_files)
        result["media_counts"] = {
            kind: sum(self.files.role_kind(file["role"]) == kind for file in input_files)
            for kind in ("image", "video", "audio")
        }
        phase = preset.phase_for_stage(job.get("stage")) if preset else None
        result["progress_phase"] = phase
        if job.get("status") == "succeeded":
            result["progress_percent"] = 100
        elif phase in self._PROGRESS_STARTS and job.get("progress_value") is not None and job.get("progress_max"):
            sample = max(0, min(100, round(job["progress_value"] * 100 / job["progress_max"])))
            result["progress_percent"] = self._PROGRESS_STARTS[phase] + round(self._PROGRESS_WEIGHTS[phase] * sample / 100)
        elif phase in self._PROGRESS_STARTS:
            result["progress_percent"] = self._PROGRESS_STARTS[phase]
        return result
