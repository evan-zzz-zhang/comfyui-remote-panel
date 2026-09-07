from __future__ import annotations

import json
import time
from typing import Any


_TIMING_KEY = "_v046_phase_timing"
_TIMING_FIELDS = frozenset({
    "standardization_started_at",
    "standardization_finished_at",
    "generation_started_at",
    "generation_finished_at",
})


def _phase(service: Any, job: dict[str, Any] | None) -> str | None:
    if not job:
        return None
    stage = str(job.get("stage") or "")
    if stage == "标准化提示词":
        return "standardize"
    preset = service.presets.get(str(job.get("preset_id") or ""))
    phase = preset.phase_for_stage(stage) if preset else None
    return "prepare" if phase == "build" else phase


def _elapsed(start: Any, end: Any) -> int | None:
    if start is None:
        return None
    try:
        return max(0, round(float(end) - float(start)))
    except (TypeError, ValueError):
        return None


def _install_database_behavior() -> None:
    from . import db as db_module

    if hasattr(db_module.Database, "update_phase_timing_v046"):
        return

    async def update_phase_timing_v046(self, job_id: str, **updates: float) -> dict[str, Any] | None:
        unknown = set(updates) - _TIMING_FIELDS
        if unknown:
            raise ValueError(f"unsupported phase timing fields: {sorted(unknown)}")
        async with self._lock:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT input_values_json FROM jobs WHERE id = ?", (job_id,)
                ).fetchone()
                if row is None:
                    return None
                try:
                    values = json.loads(row[0]) if row[0] else {}
                except json.JSONDecodeError:
                    values = {}
                if not isinstance(values, dict):
                    values = {}
                timing = values.get(_TIMING_KEY)
                if not isinstance(timing, dict):
                    timing = {}
                changed = False
                for key, value in updates.items():
                    if timing.get(key) is None:
                        timing[key] = float(value)
                        changed = True
                if changed:
                    values[_TIMING_KEY] = timing
                    connection.execute(
                        "UPDATE jobs SET input_values_json = ?, updated_at = ? WHERE id = ?",
                        (json.dumps(values, ensure_ascii=False), time.time(), job_id),
                    )
        return await self.get_job(job_id)

    db_module.Database.update_phase_timing_v046 = update_phase_timing_v046


def _install_prompt_capture_behavior() -> None:
    from . import db as db_module

    setter = getattr(db_module.Database, "set_standardized_prompt_v042", None)
    if not callable(setter) or getattr(setter, "_v046_phase_timing_capture", False):
        return

    original_setter = setter

    async def set_standardized_prompt_v046_timing(
        self, job_id: str, prompt: str
    ) -> dict[str, Any] | None:
        refreshed = await original_setter(self, job_id, prompt)
        if refreshed is None:
            return None

        values = refreshed.get("input_values")
        timing = values.get(_TIMING_KEY) if isinstance(values, dict) else None
        if not isinstance(timing, dict):
            timing = {}

        updates: dict[str, float] = {}
        if timing.get("standardization_finished_at") is None:
            started_at = timing.get("standardization_started_at")
            if started_at is None:
                # Qwen history capture can be the first observable boundary on
                # installs that do not emit a websocket standardize stage.
                started_at = refreshed.get("started_at") or refreshed.get("created_at")
                if started_at is not None:
                    updates["standardization_started_at"] = float(started_at)
            updates["standardization_finished_at"] = time.time()

        if updates:
            refreshed = await self.update_phase_timing_v046(job_id, **updates)
        return refreshed

    set_standardized_prompt_v046_timing._v046_phase_timing_capture = True  # type: ignore[attr-defined]
    db_module.Database.set_standardized_prompt_v042 = set_standardized_prompt_v046_timing


def _install_job_service_behavior() -> None:
    from . import jobs as jobs_module

    if getattr(jobs_module.JobService.handle_ws_event, "_v046_phase_timing", False):
        return

    original_handle_ws_event = jobs_module.JobService.handle_ws_event
    original_public_job = jobs_module.JobService.public_job
    original_retry = jobs_module.JobService.retry

    async def handle_ws_event_v046_timing(self, event: dict[str, Any]) -> None:
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        job_id = data.get("prompt_id")
        before = await self.db.get_job(job_id) if isinstance(job_id, str) else None
        before_phase = _phase(self, before)

        await original_handle_ws_event(self, event)

        if not isinstance(job_id, str):
            return
        after = await self.db.get_job(job_id)
        if after is None:
            return
        after_phase = _phase(self, after)
        now = time.time()
        updates: dict[str, float] = {}

        if after_phase == "standardize":
            updates["standardization_started_at"] = now
        if after_phase == "sampling":
            updates["generation_started_at"] = now
        if before_phase == "standardize" and after_phase != "standardize":
            updates["standardization_finished_at"] = now
        if before_phase == "sampling" and after_phase != "sampling":
            updates["generation_finished_at"] = now

        if updates:
            refreshed = await self.db.update_phase_timing_v046(job_id, **updates)
            if refreshed is not None:
                self.events.publish("job", self.public_job(refreshed))

    async def retry_v046_timing(self, job_id: str) -> dict[str, Any]:
        draft = await original_retry(self, job_id)
        values = draft.get("values")
        if isinstance(values, dict):
            values.pop(_TIMING_KEY, None)
        return draft

    def public_job_v046_timing(self, job: dict[str, Any] | None):
        result = original_public_job(self, job)
        if result is None or job is None:
            return result
        values = result.get("input_values")
        if not isinstance(values, dict):
            values = {}
            result["input_values"] = values
        timing = values.pop(_TIMING_KEY, None)
        if not isinstance(timing, dict):
            timing = {}

        phase = result.get("progress_phase")
        status = str(result.get("status") or "")
        terminal_end = result.get("finished_at") if status in {"succeeded", "failed", "cancelled", "interrupted", "output_missing"} else None
        now = float(terminal_end or time.time())

        standardization_start = timing.get("standardization_started_at")
        standardization_end = timing.get("standardization_finished_at")
        if standardization_start is not None and standardization_end is None:
            standardization_end = now if phase == "standardize" or terminal_end is not None else None

        generation_start = timing.get("generation_started_at")
        generation_end = timing.get("generation_finished_at")
        if generation_start is not None and generation_end is None:
            generation_end = now if phase == "sampling" or terminal_end is not None else None

        stored_values = job.get("input_values")
        backend = result.get("prompt_backend")
        if not isinstance(backend, str) and isinstance(stored_values, dict):
            backend = stored_values.get("_v048_prompt_backend")
        if backend == "raw" or result.get("prompt_standardization_mode") == "off":
            result["standardization_elapsed_seconds"] = 0
        else:
            result["standardization_elapsed_seconds"] = _elapsed(
                standardization_start, standardization_end
            )
        result["generation_elapsed_seconds"] = _elapsed(
            generation_start, generation_end
        )
        return result

    handle_ws_event_v046_timing._v046_phase_timing = True  # type: ignore[attr-defined]
    retry_v046_timing._v046_phase_timing = True  # type: ignore[attr-defined]
    public_job_v046_timing._v046_phase_timing = True  # type: ignore[attr-defined]
    jobs_module.JobService.handle_ws_event = handle_ws_event_v046_timing
    jobs_module.JobService.retry = retry_v046_timing
    jobs_module.JobService.public_job = public_job_v046_timing


def install() -> None:
    """Persist prompt-standardization and sampler timings without a DB schema change."""

    _install_database_behavior()
    _install_prompt_capture_behavior()
    _install_job_service_behavior()
