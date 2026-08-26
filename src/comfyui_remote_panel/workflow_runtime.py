from __future__ import annotations

from decimal import Decimal, InvalidOperation
import json
import secrets
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
    original_validate_parameters = Preset.validate_parameters
    original_public_metadata = Preset.public_metadata
    original_apply_history = JobService._apply_history
    original_handle_ws_event = JobService.handle_ws_event
    original_cancel = JobService.cancel
    original_observe_missing = JobService._observe_missing
    original_recover_missing_outputs = JobService._recover_missing_outputs
    original_handle_progress_state = JobService._handle_progress_state
    original_public_job = JobService.public_job

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

    def _check_step(name: str, value: int | float, spec: dict[str, Any]) -> None:
        step = spec.get("step")
        if step is None:
            return
        try:
            step_value = Decimal(str(step))
            if step_value <= 0:
                return
            base = Decimal(str(spec.get("minimum", 0)))
            quotient = (Decimal(str(value)) - base) / step_value
        except (InvalidOperation, ValueError, ZeroDivisionError) as exc:
            raise PresetError(f"{name} 步进配置无效") from exc
        if quotient != quotient.to_integral_value():
            raise PresetError(f"{name} 步进不合法")

    def _number_value(name: str, value: Any, spec: dict[str, Any]) -> float:
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise PresetError(f"{name} 必须是数字")
        number = float(value)
        _check_step(name, number, spec)
        step = spec.get("step")
        if step is None:
            return number
        try:
            decimal_step = Decimal(str(step)).normalize()
            places = max(0, -decimal_step.as_tuple().exponent)
        except (InvalidOperation, ValueError):
            places = 12
        return round(number, places)

    def _random_seed(spec: dict[str, Any]) -> int:
        minimum = int(spec.get("minimum", 0))
        maximum = int(spec.get("maximum", 2**64 - 1))
        if maximum < minimum:
            raise PresetError("seed 范围无效")
        span = maximum - minimum + 1
        return minimum + secrets.randbelow(span)

    def validate_parameters(
        self: Preset, values: dict[str, Any], *, allow_empty_prompt: bool = False
    ) -> dict[str, Any]:
        # H3 keeps its established normalization path. Generic workflows instead
        # honor each `/object_info` Schema step; a 0.01 denoise must not be
        # silently rounded to one decimal place by the legacy H3 validator.
        if self.manifest.get("family", "generic") != "generic":
            return original_validate_parameters(self, values, allow_empty_prompt=allow_empty_prompt)

        specs = self.manifest["parameters"]
        result: dict[str, Any] = {}
        for name, spec in specs.items():
            value = values.get(name, spec.get("default"))
            if name == "prompt":
                if not isinstance(value, str) or not value.strip():
                    if not allow_empty_prompt:
                        raise PresetError("提示词不能为空")
                    result[name] = ""
                    continue
                result[name] = value.strip()
                continue
            if name == "seed":
                # Generic workflow semantics intentionally preserve ComfyUI's
                # literal seed contract: only an empty/null value means random.
                # Integer 0 is a real, reproducible seed and must stay 0.
                if value is None:
                    seed = _random_seed(spec)
                elif isinstance(value, int) and not isinstance(value, bool):
                    seed = value
                elif isinstance(value, str) and value.isascii() and value.isdigit():
                    seed = int(value)
                else:
                    raise PresetError("种子必须是整数")
                minimum, maximum = spec.get("minimum"), spec.get("maximum")
                if minimum is not None and seed < minimum:
                    raise PresetError(f"{name} 低于允许范围")
                if maximum is not None and seed > maximum:
                    raise PresetError(f"{name} 超出允许范围")
                _check_step(name, seed, spec)
                result[name] = str(seed)
                continue

            kind = spec["type"]
            if kind == "integer":
                if not isinstance(value, int) or isinstance(value, bool):
                    raise PresetError(f"{name} 必须是整数")
                _check_step(name, value, spec)
            elif kind == "number":
                value = _number_value(name, value, spec)
            elif kind == "string":
                if not isinstance(value, str):
                    raise PresetError(f"{name} 必须是文本")
            elif kind == "boolean":
                if not isinstance(value, bool):
                    raise PresetError(f"{name} 必须是布尔值")
            elif kind == "enum":
                if value not in spec["values"]:
                    raise PresetError(f"不支持的 {name}")

            minimum, maximum = spec.get("minimum"), spec.get("maximum")
            if minimum is not None and value < minimum:
                raise PresetError(f"{name} 低于允许范围")
            if maximum is not None and value > maximum:
                raise PresetError(f"{name} 超出允许范围")
            result[name] = value
        return result

    def public_metadata(self: Preset) -> dict[str, Any]:
        result = original_public_metadata(self)
        result["capability_profile"] = self.manifest.get("capability_profile", {})
        result["workflow_confidence"] = self.manifest.get("workflow_confidence")
        result["preflight"] = self.manifest.get("preflight", {})
        return result

    async def handle_progress_state(
        self: JobService, job_id: str, preset: Preset, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        if preset.manifest.get("family", "generic") != "generic" or preset.stages:
            return await original_handle_progress_state(self, job_id, preset, data)

        # ComfyUI progress_state can contain completed helper nodes such as 1/1.
        # For an arbitrary imported graph that value is not an overall progress
        # percentage. Keep it as liveness only and let real `progress` events
        # drive numeric progress.
        nodes = data.get("nodes")
        if not isinstance(nodes, dict) or not any(isinstance(node, dict) for node in nodes.values()):
            return None
        return await self.db.update_active_job(
            job_id,
            status="running",
            queue_position=0,
            missing_observations=0,
            missing_first_at=None,
        )

    def public_job(self: JobService, job: dict[str, Any] | None) -> dict[str, Any] | None:
        result = original_public_job(self, job)
        if result is None or job is None:
            return result
        preset = self.presets.get(job["preset_id"])
        if not preset or preset.manifest.get("family", "generic") != "generic":
            return result

        if job.get("status") == "succeeded":
            result["progress_percent"] = 100
            return result

        value = job.get("progress_value")
        maximum = job.get("progress_max")
        if value is not None and maximum:
            sample = max(0, min(100, round(float(value) * 100 / float(maximum))))
            # Reserve 100 for execution_success. Imported graphs may still have
            # decode/save nodes after the sampler reaches its own 100%.
            result["progress_percent"] = min(95, sample)
            result["progress_phase"] = "sampling"
        elif job.get("status") in {"submitting", "queued", "running"}:
            result["progress_percent"] = 0
        return result

    async def persist_runtime_result(service: JobService, job: dict[str, Any] | None) -> None:
        if not job or job.get("status") not in _RUNTIME_TERMINAL:
            return
        workflow_id = str(job.get("workflow_id") or job.get("preset_id") or "")
        preset = service.presets.get(workflow_id)
        if not preset or preset.manifest.get("family", "generic") != "generic":
            return
        try:
            revision = int(job.get("workflow_revision") or preset.revision)
        except (TypeError, ValueError):
            revision = preset.revision

        job_status = str(job["status"])
        if job_status == "succeeded":
            artifacts = await service.db.list_artifacts(str(job["id"]))
            outputs = [item for item in artifacts if item.get("direction") == "output"]
            if outputs:
                status = "PASS"
                message = "Runtime execution passed"
                details: list[str] = []
            else:
                status = "WARN"
                message = "Runtime execution passed; output capture pending"
                details = []
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

        # A result from an older running revision must never change the live
        # metadata of a newer revision selected in the creation UI.
        if revision == preset.revision:
            preset.manifest.setdefault("preflight", {})["runtime"] = dict(runtime)

        # Persist runtime evidence on the exact revision used by this job. Runtime
        # evidence is mutable metadata and must not create another revision.
        async with service.db._lock:
            with service.db._connect() as db:
                row = db.execute(
                    "SELECT definition_json FROM workflows WHERE id = ? AND revision = ?",
                    (workflow_id, revision),
                ).fetchone()
                if row is None:
                    return
                definition = json.loads(row["definition_json"])
                definition.setdefault("manifest", {}).setdefault("preflight", {})["runtime"] = runtime
                db.execute(
                    "UPDATE workflows SET definition_json = ?, updated_at = ? WHERE id = ? AND revision = ?",
                    (json.dumps(definition, ensure_ascii=False), time.time(), workflow_id, revision),
                )

    async def apply_history(self: JobService, job: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
        result = await original_apply_history(self, job, entry)
        await persist_runtime_result(self, result)
        return result

    async def handle_ws_event(self: JobService, event: dict[str, Any]) -> None:
        await original_handle_ws_event(self, event)
        # execution_success already flows through the patched _apply_history.
        if event.get("type") == "execution_success":
            return
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

    async def recover_missing_outputs(self: JobService) -> None:
        pending_ids = [str(job["id"]) for job in await self.db.succeeded_without_output()]
        await original_recover_missing_outputs(self)
        for job_id in pending_ids:
            await persist_runtime_result(self, await self.db.get_job(job_id))

    Preset.validate_media_roles = validate_media_roles
    Preset.validate_parameters = validate_parameters
    Preset.public_metadata = public_metadata
    JobService._handle_progress_state = handle_progress_state
    JobService.public_job = public_job
    JobService._apply_history = apply_history
    JobService.handle_ws_event = handle_ws_event
    JobService.cancel = cancel
    JobService._observe_missing = observe_missing
    JobService._recover_missing_outputs = recover_missing_outputs