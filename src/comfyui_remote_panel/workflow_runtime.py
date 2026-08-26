from __future__ import annotations

import json
import time
from typing import Any

from .jobs import JobService
from .preset import Preset, PresetError


_INSTALLED = False
_RUNTIME_TERMINAL = {"succeeded", "failed", "cancelled", "interrupted", "output_missing"}


def install_workflow_runtime() -> None:
    """Install narrow Generic Workflow runtime extensions.

    Keeping this migration shim isolated avoids changing H3's proven manifest
    implementation while Configurator 2.0 adds required slot semantics, a public
    capability profile and persisted runtime preflight evidence. It can be
    removed once schema_version 3 folds these fields into Preset directly.
    """
    global _INSTALLED
    if _INSTALLED:
        return
    _INSTALLED = True

    original_validate_media_roles = Preset.validate_media_roles
    original_public_metadata = Preset.public_metadata
    original_apply_history = JobService._apply_history
    original_handle_ws_event = JobService.handle_ws_event
    original_cancel = JobService.cancel
    original_observe_missing = JobService._observe_missing

    def validate_media_roles(self: Preset, roles: set[str]) -> tuple[str, bool]:
        media = self.media_binding
        if media.get("type") == "slots":
            slots = media.get("slots", {})
            if roles - set(slots):
                raise PresetError("工作流收到了未声明的媒体槽位")
            required = {
                role for role, slot in slots.items()
                if isinstance(slot, dict) and (
                    slot.get("required") is True
                    or isinstance(slot.get("ui"), dict) and slot["ui"].get("optional") is False
                )
            }
            missing = sorted(required - roles)
            if missing:
                labels = [
                    str(slots[role].get("ui", {}).get("label") or role)
                    for role in missing
                ]
                raise PresetError(f"缺少必需素材：{'、'.join(labels)}")
            return ("纯文字" if not roles else f"{len(roles)} 个媒体输入"), False
        return original_validate_media_roles(self, roles)

    def public_metadata(self: Preset) -> dict[str, Any]:
        result = original_public_metadata(self)
        result["capability_profile"] = self.manifest.get("capability_profile", {})
        result["workflow_confidence"] = self.manifest.get("workflow_confidence")
        result["preflight"] = self.manifest.get("preflight", {})
        return result

    async def persist_runtime_result(service: JobService, job: dict[str, Any] | None) -> None:
        if not job or job.get("status") not in _RUNTIME_TERMINAL:
            return
        workflow_id = str(job.get("workflow_id") or job.get("preset_id") or "")
        preset = service.presets.get(workflow_id)
        if not preset or preset.manifest.get("family", "generic") != "generic":
            return

        job_status = str(job["status"])
        if job_status == "succeeded":
            status = "PASS"
            message = "Runtime execution passed"
            details: list[str] = []
        elif job_status == "cancelled":
            status = "WARN"
            message = "Runtime test cancelled"
            details = []
        else:
            status = "FAIL"
            message = "Runtime execution failed"
            summary = str(job.get("error_summary") or "ComfyUI execution did not complete successfully")
            details = [summary[:500]]
        runtime = {"status": status, "message": message, "details": details, "tested_at": time.time()}

        # Update the live preset immediately so /api/presets reflects the result.
        preset.manifest.setdefault("preflight", {})["runtime"] = dict(runtime)

        # Persist only the latest workflow definition and never create a new
        # revision merely because runtime evidence changed.
        async with service.db._lock:
            with service.db._connect() as db:
                row = db.execute(
                    "SELECT revision, definition_json FROM workflows WHERE id = ? ORDER BY revision DESC LIMIT 1",
                    (workflow_id,),
                ).fetchone()
                if row is None:
                    return
                definition = json.loads(row["definition_json"])
                definition.setdefault("manifest", {}).setdefault("preflight", {})["runtime"] = runtime
                db.execute(
                    "UPDATE workflows SET definition_json = ?, updated_at = ? WHERE id = ? AND revision = ?",
                    (json.dumps(definition, ensure_ascii=False), time.time(), workflow_id, row["revision"]),
                )

    async def apply_history(self: JobService, job: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
        result = await original_apply_history(self, job, entry)
        await persist_runtime_result(self, result)
        return result

    async def handle_ws_event(self: JobService, event: dict[str, Any]) -> None:
        await original_handle_ws_event(self, event)
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        prompt_id = data.get("prompt_id")
        if isinstance(prompt_id, str):
            await persist_runtime_result(self, await self.db.get_job(prompt_id))

    async def cancel(self: JobService, job_id: str) -> dict[str, Any]:
        result = await original_cancel(self, job_id)
        await persist_runtime_result(self, result)
        return result

    async def observe_missing(self: JobService, job: dict[str, Any]) -> dict[str, Any] | None:
        result = await original_observe_missing(self, job)
        await persist_runtime_result(self, result)
        return result

    Preset.validate_media_roles = validate_media_roles
    Preset.public_metadata = public_metadata
    JobService._apply_history = apply_history
    JobService.handle_ws_event = handle_ws_event
    JobService.cancel = cancel
    JobService._observe_missing = observe_missing
