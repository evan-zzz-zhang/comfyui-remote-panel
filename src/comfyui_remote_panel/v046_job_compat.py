from __future__ import annotations


_OLD_PROGRESS_STARTS = {"build": 0, "sampling": 10, "decode": 70, "compose": 85, "save": 95}
_OLD_PROGRESS_WEIGHTS = {"build": 10, "sampling": 60, "decode": 15, "compose": 10, "save": 5}


def install() -> None:
    """Keep pre-v0.4.2 records on the historical progress mapping."""

    from . import jobs as jobs_module
    from .v042 import FL2VA_PRESET_IDS

    if getattr(jobs_module.JobService.public_job, "_v046_legacy_progress_compat", False):
        return

    original_public_job = jobs_module.JobService.public_job

    def public_job_v046_legacy_progress(self, job):
        result = original_public_job(self, job)
        if result is None or job is None:
            return result
        preset_id = str(job.get("preset_id") or "")
        values = job.get("input_values")
        if preset_id not in FL2VA_PRESET_IDS or not isinstance(values, dict) or "prompt_standardization" in values:
            return result

        preset = self.presets.get(preset_id)
        phase = preset.phase_for_stage(job.get("stage")) if preset else None
        result["progress_phase"] = phase
        if job.get("status") == "succeeded":
            result["progress_percent"] = 100
        elif phase in _OLD_PROGRESS_STARTS and job.get("progress_value") is not None and job.get("progress_max"):
            sample = max(0, min(100, round(job["progress_value"] * 100 / job["progress_max"])))
            result["progress_percent"] = _OLD_PROGRESS_STARTS[phase] + round(_OLD_PROGRESS_WEIGHTS[phase] * sample / 100)
        elif phase in _OLD_PROGRESS_STARTS:
            result["progress_percent"] = _OLD_PROGRESS_STARTS[phase]
        return result

    public_job_v046_legacy_progress._v046_legacy_progress_compat = True  # type: ignore[attr-defined]
    jobs_module.JobService.public_job = public_job_v046_legacy_progress
