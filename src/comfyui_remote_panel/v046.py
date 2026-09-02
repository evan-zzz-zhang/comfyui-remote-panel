from __future__ import annotations

import asyncio
import time
from typing import Any

from .workflow_registry import (
    CANONICAL_FL2VA_ASSET_IDS,
    FL2VA_GENERATION_MODES,
    asset_key,
    resolve_fl2va_asset,
)
from .inference_profile import (
    InferenceProfileError,
    resolve_inference_profile,
)


DEFAULT_STANDARDIZATION_MODE = "ollama"
STANDARDIZATION_MODES = frozenset({"off", "ollama", "comfyui"})
QWEN_GENERATION_MODES = {
    "original": "h3-fl2va-qwen35-4b",
    "lightx2v": "h3-fl2va-lightx2v-qwen35-4b",
    "v4_600step": "h3-fl2va-v4step600-qwen35-4b",
}
CANONICAL_FL2VA_PRESET_IDS = CANONICAL_FL2VA_ASSET_IDS
CANONICAL_QWEN_PRESET_IDS = frozenset(
    f"fl2va_{generation_mode}_qwen35" for generation_mode in FL2VA_GENERATION_MODES
)
QWEN_PRESET_TO_GENERATION_MODE = {
    preset_id: mode for mode, preset_id in QWEN_GENERATION_MODES.items()
}
QWEN_PRESET_TO_GENERATION_MODE.update({
    preset_id: preset_id.removeprefix("fl2va_").removesuffix("_qwen35")
    for preset_id in CANONICAL_QWEN_PRESET_IDS
})
QWEN_FL2VA_PRESET_IDS = frozenset(QWEN_PRESET_TO_GENERATION_MODE)

_FL2VA_PROGRESS_OFF = {
    "prepare": (0, 10),
    "sampling": (10, 68),
    "decode": (78, 12),
    "compose": (90, 7),
    "save": (97, 3),
}
_FL2VA_PROGRESS_STANDARDIZED = {
    "prepare": (0, 8),
    "standardize": (8, 12),
    "sampling": (20, 60),
    "decode": (80, 11),
    "compose": (91, 6),
    "save": (97, 3),
}
_OFFLINE_CONFIRMATIONS = 3


def _normalize_standardization_mode(value: Any) -> str:
    mode = str(value or DEFAULT_STANDARDIZATION_MODE).strip().lower()
    mode = {
        "raw": "off",
        "qwen35": "comfyui",
    }.get(mode, mode)
    if mode not in STANDARDIZATION_MODES:
        raise ValueError("标准化提示词必须是 off / ollama / comfyui")
    return mode


def _history_text(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, (list, tuple)):
        for item in value:
            text = _history_text(item)
            if text is not None:
                return text
    if isinstance(value, dict):
        for key in ("text", "value", "string"):
            if key in value:
                text = _history_text(value[key])
                if text is not None:
                    return text
    return None


def _qwen_standardized_prompt(service: Any, job: dict[str, Any], entry: dict[str, Any]) -> str | None:
    preset_id = str(job.get("preset_id") or "")
    if preset_id not in QWEN_FL2VA_PRESET_IDS:
        return None
    preset = service.presets.get(preset_id)
    if preset is None:
        return None
    standardizer = preset.manifest.get("prompt_standardizer")
    if not isinstance(standardizer, dict) or standardizer.get("backend") != "comfyui":
        return None
    history_node = standardizer.get("history_node")
    outputs = entry.get("outputs") if isinstance(entry, dict) else None
    if history_node is None or not isinstance(outputs, dict):
        return None
    text = _history_text(outputs.get(str(history_node)))
    return text if isinstance(text, str) and text.strip() else None


def _apply_fl2va_progress(
    result: dict[str, Any], job: dict[str, Any], standardization_mode: str
) -> None:
    phase = result.get("progress_phase")
    if str(job.get("stage") or "") == "标准化提示词":
        phase = "standardize"
    elif phase == "build":
        phase = "prepare"
    result["progress_phase"] = phase

    if job.get("status") == "succeeded":
        result["progress_percent"] = 100
        return

    ranges = (
        _FL2VA_PROGRESS_OFF
        if standardization_mode == "off"
        else _FL2VA_PROGRESS_STANDARDIZED
    )
    if phase not in ranges:
        return

    start, weight = ranges[phase]
    # Only sampler progress is a trustworthy continuous percentage. Model
    # loading, prompt standardization, decoding and saving are semantic stages;
    # inventing time-based progress for them would be misleading.
    if phase == "sampling" and job.get("progress_value") is not None and job.get("progress_max"):
        sample = max(
            0,
            min(
                100,
                round(job["progress_value"] * 100 / job["progress_max"]),
            ),
        )
        result["progress_percent"] = start + round(weight * sample / 100)
    else:
        result["progress_percent"] = start


def _install_database_timing() -> None:
    from . import db as db_module

    if getattr(db_module.Database._job_from_row, "_v046_execution_timing", False):
        return

    original_job_from_row = db_module.Database._job_from_row

    def job_from_row_v046(self, row, files):
        item = original_job_from_row(self, row, files)
        now = float(item.get("finished_at") or time.time())
        created_at = float(item.get("created_at") or now)
        started_at = item.get("started_at")

        if started_at is None:
            queue_end = now
            queue_elapsed = max(0, round(queue_end - created_at))
            execution_elapsed = 0
        else:
            started = float(started_at)
            queue_elapsed = max(0, round(started - created_at))
            execution_elapsed = max(0, round(now - started))

        item["queue_elapsed_seconds"] = queue_elapsed
        item["execution_elapsed_seconds"] = execution_elapsed
        # Preserve the established field for old clients, but redefine it as
        # actual execution time. Queue waiting must never inflate generation
        # performance numbers.
        item["elapsed_seconds"] = execution_elapsed
        return item

    job_from_row_v046._v046_execution_timing = True  # type: ignore[attr-defined]
    db_module.Database._job_from_row = job_from_row_v046


def _install_preset_behavior() -> None:
    from . import preset as preset_module

    if getattr(preset_module.Preset.validate_parameters, "_v046_qwen_standardizer", False):
        return

    original_validate_parameters = preset_module.Preset.validate_parameters

    def validate_parameters_v046(
        self,
        values: dict[str, Any],
        *,
        allow_empty_prompt: bool = False,
    ) -> dict[str, Any]:
        standardizer = self.manifest.get("prompt_standardizer")
        if isinstance(standardizer, dict) and standardizer.get("backend") == "comfyui":
            allow_empty_prompt = False
        return original_validate_parameters(
            self, values, allow_empty_prompt=allow_empty_prompt
        )

    validate_parameters_v046._v046_qwen_standardizer = True  # type: ignore[attr-defined]
    preset_module.Preset.validate_parameters = validate_parameters_v046


def _install_job_service() -> None:
    from . import jobs as jobs_module
    from . import preset as preset_module
    from .v042 import FL2VA_ENTRY_ID, FL2VA_PRESET_IDS, GENERATION_MODES

    if getattr(jobs_module.JobService.create, "_v046_standardizer_modes", False):
        return

    original_create = jobs_module.JobService.create
    original_retry = jobs_module.JobService.retry
    original_public_job = jobs_module.JobService.public_job
    original_apply_history = jobs_module.JobService._apply_history
    original_reconcile_once = jobs_module.JobService.reconcile_once

    def normalize_generation_mode(value: Any) -> str:
        mode = str(value or "v4_600step").strip().lower()
        if mode not in GENERATION_MODES:
            raise preset_module.PresetError(
                "生成模式必须是 original / lightx2v / v4_600step"
            )
        return mode

    async def require_enabled(self, preset_id: str, label: str) -> None:
        get_workflow = getattr(self.db, "get_workflow", None)
        if not callable(get_workflow):
            return
        item = await get_workflow(preset_id)
        if item is not None and item.get("status") != "enabled":
            raise preset_module.PresetError(f"{label} 对应工作流已禁用")

    async def create_v046(
        self,
        fields: dict[str, Any],
        uploaded: list[dict[str, Any]],
        job_id: str | None = None,
        *,
        is_test: bool = False,
    ) -> dict[str, Any]:
        routed = dict(fields)
        preset_id = str(routed.get("preset_id") or "")

        async def resolve_profile(preset: Any) -> None:
            try:
                requested, effective = resolve_inference_profile(
                    preset, routed.get("inference_profile")
                )
            except InferenceProfileError as exc:
                raise preset_module.PresetError(str(exc)) from exc
            current_profile = str(
                preset.manifest.get("model_profile", {})
                .get("main_model", {})
                .get("current", "int8")
            ).strip().lower()
            validate_variant = getattr(self.comfy, "validate_preset_variant", None)
            if effective != current_profile and callable(validate_variant):
                diagnostics = await validate_variant(preset, effective)
                if diagnostics:
                    raise preset_module.PresetError("；".join(diagnostics[:3]))
            routed["_v047_inference_profile"] = requested
            routed["_v047_effective_inference_profile"] = effective

        if preset_id == FL2VA_ENTRY_ID:
            mode = normalize_generation_mode(routed.get("generation_mode"))
            raw_backend = routed.get("prompt_backend")
            if raw_backend is not None:
                raw_standardization_mode = {
                    "raw": "off",
                    "ollama": "ollama",
                    "qwen35": "comfyui",
                }.get(str(raw_backend).strip().lower(), raw_backend)
            else:
                raw_standardization_mode = routed.get("prompt_standardization_mode")
            if raw_standardization_mode is None and "prompt_standardization" in routed:
                legacy = routed.get("prompt_standardization")
                if legacy is False:
                    raw_standardization_mode = "off"
                elif legacy is True:
                    raw_standardization_mode = "ollama"
            try:
                standardization_mode = _normalize_standardization_mode(
                    raw_standardization_mode
                )
            except ValueError as exc:
                raise preset_module.PresetError(str(exc)) from exc

            backend = {
                "off": "raw",
                "ollama": "ollama",
                "comfyui": "qwen35",
            }[standardization_mode]
            try:
                target = resolve_fl2va_asset(
                    self.presets,
                    family="fl2va",
                    generation_mode=mode,
                    prompt_backend=backend,
                )
            except ValueError as exc:
                raise preset_module.PresetError(str(exc)) from exc

            target_id = target.id
            await require_enabled(
                self, target_id,
                f"{mode} + Qwen3.5 标准化" if backend == "qwen35" else f"{mode} + {backend} 标准化",
            )
            await resolve_profile(target)
            routed["_v047_prompt_backend"] = backend
            if standardization_mode == "comfyui":
                routed["preset_id"] = target_id
                routed.pop("generation_mode", None)
                routed.pop("prompt_standardization_mode", None)
                routed.pop("prompt_standardization", None)
                routed.pop("ollama_model", None)
                return await original_create(
                    self, routed, uploaded, job_id, is_test=is_test
                )

            routed["preset_id"] = target_id
            routed.pop("generation_mode", None)
            routed.pop("prompt_standardization_mode", None)
            routed.pop("prompt_standardization", None)
            if standardization_mode == "off":
                routed.pop("ollama_model", None)
            return await original_create(
                self, routed, uploaded, job_id, is_test=is_test
            )

        if preset_id in QWEN_FL2VA_PRESET_IDS:
            mode = QWEN_PRESET_TO_GENERATION_MODE[preset_id]
            await require_enabled(self, preset_id, f"{mode} + Qwen3.5 标准化")
            routed.pop("generation_mode", None)
            routed.pop("prompt_standardization_mode", None)
            routed.pop("prompt_standardization", None)
            routed.pop("ollama_model", None)
            preset = self.presets.get(preset_id)
            if preset is not None:
                await resolve_profile(preset)
            routed["_v047_prompt_backend"] = "qwen35"
        elif preset_id in CANONICAL_FL2VA_PRESET_IDS:
            preset = self.presets.get(preset_id)
            if preset is not None:
                await resolve_profile(preset)
            routed["_v047_prompt_backend"] = preset.manifest.get("prompt_backend", "raw") if preset else "raw"
        return await original_create(
            self, routed, uploaded, job_id, is_test=is_test
        )

    async def retry_v046(self, job_id: str) -> dict[str, Any]:
        draft = await original_retry(self, job_id)
        preset_id = str(draft.get("preset_id") or "")
        values = draft.get("values")
        if not isinstance(values, dict):
            values = {}
            draft["values"] = values

        qwen_mode = QWEN_PRESET_TO_GENERATION_MODE.get(preset_id)
        if qwen_mode is not None:
            display_mode = "v4_600step" if qwen_mode == "v4step600" else qwen_mode
            draft["preset_id"] = FL2VA_ENTRY_ID
            draft["generation_mode"] = display_mode
            draft["prompt_standardization_mode"] = "comfyui"
            draft["prompt_backend"] = "qwen35"
            values["prompt_standardization_mode"] = "comfyui"
            values["prompt_backend"] = "qwen35"
            return draft

        presets = getattr(self, "presets", {})
        preset = presets.get(preset_id) if isinstance(presets, dict) else None
        canonical = asset_key(preset) if preset is not None else None
        if canonical is not None:
            draft["preset_id"] = FL2VA_ENTRY_ID
            draft["generation_mode"] = (
                "v4_600step" if canonical.generation_mode == "v4step600" else canonical.generation_mode
            )
            draft["prompt_backend"] = canonical.prompt_backend
            draft["prompt_standardization_mode"] = (
                "off" if canonical.prompt_backend == "raw" else "comfyui" if canonical.prompt_backend == "qwen35" else "ollama"
            )
            values["prompt_backend"] = canonical.prompt_backend
            values["prompt_standardization_mode"] = draft["prompt_standardization_mode"]
            return draft

        mode = draft.get("generation_mode")
        if preset_id == FL2VA_ENTRY_ID and mode in GENERATION_MODES:
            standardization_mode = (
                "off" if values.get("prompt_standardization") is False else "ollama"
            )
            draft["prompt_standardization_mode"] = standardization_mode
            draft["prompt_backend"] = "raw" if standardization_mode == "off" else "ollama"
            values["prompt_standardization_mode"] = standardization_mode
            values["prompt_backend"] = draft["prompt_backend"]
        return draft

    async def apply_history_v046(
        self, job: dict[str, Any], entry: dict[str, Any]
    ) -> dict[str, Any]:
        standardized_prompt = _qwen_standardized_prompt(self, job, entry)
        result = await original_apply_history(self, job, entry)
        if standardized_prompt:
            setter = getattr(self.db, "set_standardized_prompt_v042", None)
            if callable(setter):
                refreshed = await setter(job["id"], standardized_prompt)
                if refreshed is not None:
                    result = refreshed
        return result

    async def recover_standardized_prompts_v046(self) -> None:
        """Backfill Qwen prompt text after ComfyUI history becomes complete."""

        now = time.time()
        last_run = float(getattr(self, "_last_standardized_prompt_recovery", 0) or 0)
        if now - last_run < 30:
            return
        self._last_standardized_prompt_recovery = now

        list_succeeded = getattr(self.db, "succeeded_jobs", None)
        if not callable(list_succeeded):
            return
        setter = getattr(self.db, "set_standardized_prompt_v042", None)
        if not callable(setter):
            return

        found = recovered = failed = 0
        for job in await list_succeeded():
            if str(job.get("preset_id") or "") not in QWEN_FL2VA_PRESET_IDS:
                continue
            if not any(file.get("role") == "output" for file in job.get("files", [])):
                continue
            values = job.get("input_values")
            if isinstance(values, dict) and str(values.get("_v042_standardized_prompt") or "").strip():
                continue
            found += 1
            try:
                history = await self.comfy.history(str(job["id"]))
                entry = history.get(str(job["id"])) if isinstance(history, dict) else None
                text = _qwen_standardized_prompt(self, job, entry) if isinstance(entry, dict) else None
                if text:
                    refreshed = await setter(str(job["id"]), text)
                    if refreshed is not None:
                        recovered += 1
                        self.events.publish("job", self.public_job(refreshed))
                    else:
                        failed += 1
                else:
                    failed += 1
            except Exception:
                failed += 1
                jobs_module.log.exception(
                    "standardized prompt recovery failed for job %s", job.get("id")
                )
        if found:
            jobs_module.log.info(
                "standardized prompt recovery: found=%d recovered=%d failed=%d",
                found, recovered, failed,
            )

    async def reconcile_once_v046(self) -> None:
        await original_reconcile_once(self)
        await recover_standardized_prompts_v046(self)

    def public_job_v046(self, job: dict[str, Any] | None):
        result = original_public_job(self, job)
        if result is None or job is None:
            return result
        preset_id = str(job.get("preset_id") or "")
        values = result.get("input_values")
        if not isinstance(values, dict):
            values = {}
        stored_backend = values.get("_v047_prompt_backend")
        stored_profile = values.get("_v047_inference_profile")
        effective_profile = values.get("_v047_effective_inference_profile")
        if stored_backend:
            result["prompt_backend"] = stored_backend
        if stored_profile:
            result["inference_profile"] = stored_profile
        if effective_profile:
            result["effective_inference_profile"] = effective_profile
        for key in (
            "_v047_prompt_backend",
            "_v047_inference_profile",
            "_v047_effective_inference_profile",
        ):
            values.pop(key, None)
        result["input_values"] = values
        standardization_mode: str | None = None
        preset = self.presets.get(preset_id)
        canonical = asset_key(preset) if preset is not None else None
        if canonical is not None:
            display_mode = (
                "v4_600step"
                if canonical.generation_mode == "v4step600"
                else canonical.generation_mode
            )
            result["generation_mode"] = display_mode
            result["prompt_backend"] = canonical.prompt_backend
            result["prompt_standardization_mode"] = (
                "off" if canonical.prompt_backend == "raw" else canonical.prompt_backend
            )
            standardization_mode = (
                "off" if canonical.prompt_backend == "raw" else canonical.prompt_backend
            )
        else:
            qwen_mode = QWEN_PRESET_TO_GENERATION_MODE.get(preset_id)
        if canonical is None and qwen_mode is not None:
            result["generation_mode"] = qwen_mode
            result["prompt_backend"] = "qwen35"
            result["prompt_standardization_mode"] = "comfyui"
            standardization_mode = "comfyui"
        elif canonical is None and preset_id in FL2VA_PRESET_IDS:
            values = result.get("input_values")
            if not isinstance(values, dict):
                values = {}
            standardization_mode = (
                "off" if values.get("prompt_standardization") is False else "ollama"
            )
            result["prompt_standardization_mode"] = standardization_mode
            result["prompt_backend"] = (
                "raw" if standardization_mode == "off" else "ollama"
            )

        if standardization_mode is not None:
            _apply_fl2va_progress(result, job, standardization_mode)
        return result

    create_v046._v046_standardizer_modes = True  # type: ignore[attr-defined]
    retry_v046._v046_standardizer_modes = True  # type: ignore[attr-defined]
    apply_history_v046._v046_standardizer_modes = True  # type: ignore[attr-defined]
    public_job_v046._v046_standardizer_modes = True  # type: ignore[attr-defined]
    reconcile_once_v046._v046_standardizer_modes = True  # type: ignore[attr-defined]
    jobs_module.JobService.create = create_v046
    jobs_module.JobService.retry = retry_v046
    jobs_module.JobService._apply_history = apply_history_v046
    jobs_module.JobService.public_job = public_job_v046
    jobs_module.JobService._recover_standardized_prompts_v046 = recover_standardized_prompts_v046
    jobs_module.JobService.reconcile_once = reconcile_once_v046


def _install_offline_reconciliation() -> None:
    from . import jobs as jobs_module
    from .comfy import ComfyError

    if getattr(jobs_module.JobService.reconcile_loop, "_v046_offline_reconciliation", False):
        return

    async def interrupt_active_for_offline_v046(self, offline_since: float) -> None:
        for job in await self.db.active_jobs():
            status = str(job.get("status") or "")
            if status == "running":
                stage = "ComfyUI 已离线"
                summary = "ComfyUI 在任务执行期间离线，任务已中断"
            elif status == "queued":
                stage = "排队已中断"
                summary = "ComfyUI 已离线，排队任务已失效"
            else:
                stage = "提交已中断"
                summary = "ComfyUI 已离线，任务提交状态已失效"
            updated = await self.db.update_active_job(
                job["id"],
                status="interrupted",
                stage=stage,
                error_code="comfyui_offline",
                error_summary=summary,
                finished_at=offline_since,
                queue_position=None,
                progress_value=None,
                progress_max=None,
                missing_observations=0,
                missing_first_at=None,
            )
            if updated:
                self.events.publish("job", self.public_job(updated))

    async def reconcile_loop_v046(self, interval: float = 3.0) -> None:
        failures = 0
        offline_since: float | None = None
        while not self._stop.is_set():
            try:
                await self.reconcile_once()
            except ComfyError:
                now = time.time()
                failures += 1
                if offline_since is None:
                    offline_since = now
                if failures >= _OFFLINE_CONFIRMATIONS:
                    await interrupt_active_for_offline_v046(self, offline_since)
            except Exception:
                jobs_module.log.exception("job reconciliation failed")
            else:
                failures = 0
                offline_since = None
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=interval)
            except asyncio.TimeoutError:
                pass

    interrupt_active_for_offline_v046._v046_offline_reconciliation = True  # type: ignore[attr-defined]
    reconcile_loop_v046._v046_offline_reconciliation = True  # type: ignore[attr-defined]
    jobs_module.JobService._interrupt_active_for_offline_v046 = interrupt_active_for_offline_v046
    jobs_module.JobService.reconcile_loop = reconcile_loop_v046


def _install_lifecycle_interruption_hook() -> None:
    from . import app as app_module
    from . import lifecycle as lifecycle_module

    if not getattr(lifecycle_module.ComfyLifecycle._stop, "_v046_job_interrupt", False):
        original_stop = lifecycle_module.ComfyLifecycle._stop
        original_force_stop = lifecycle_module.ComfyLifecycle._force_stop

        async def notify_jobs(self) -> None:
            callback = getattr(self, "_v046_jobs_offline_callback", None)
            if callable(callback):
                await callback(time.time())

        async def stop_v046(self) -> None:
            await original_stop(self)
            await notify_jobs(self)

        async def force_stop_v046(self) -> None:
            await original_force_stop(self)
            await notify_jobs(self)

        stop_v046._v046_job_interrupt = True  # type: ignore[attr-defined]
        force_stop_v046._v046_job_interrupt = True  # type: ignore[attr-defined]
        lifecycle_module.ComfyLifecycle._stop = stop_v046
        lifecycle_module.ComfyLifecycle._force_stop = force_stop_v046

    if getattr(app_module.create_app, "_v046_lifecycle_jobs", False):
        return

    original_create_app = app_module.create_app

    def create_app_v046_lifecycle_jobs(*args: Any, **kwargs: Any):
        application = original_create_app(*args, **kwargs)
        lifecycle = application["lifecycle"]
        jobs = application["jobs"]

        async def interrupt_after_managed_stop(offline_since: float) -> None:
            await jobs._interrupt_active_for_offline_v046(offline_since)

        lifecycle._v046_jobs_offline_callback = interrupt_after_managed_stop
        return application

    create_app_v046_lifecycle_jobs._v046_lifecycle_jobs = True  # type: ignore[attr-defined]
    app_module.create_app = create_app_v046_lifecycle_jobs


def install() -> None:
    """Install v0.4.6 FL2VA routing plus job progress/timing reliability."""

    _install_database_timing()
    _install_preset_behavior()
    _install_job_service()
    _install_offline_reconciliation()
    _install_lifecycle_interruption_hook()
