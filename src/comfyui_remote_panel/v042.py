from __future__ import annotations

import copy
import secrets
from typing import Any


FL2VA_ENTRY_ID = "h3-fl2va"
DEFAULT_GENERATION_MODE = "v4_600step"
GENERATION_MODES = {
    "original": "h3-fl2va",
    "lightx2v": "h3-fl2va-lightx2v",
    "v4_600step": "h3-fl2va-v4step600",
}
PRESET_TO_GENERATION_MODE = {preset_id: mode for mode, preset_id in GENERATION_MODES.items()}
FL2VA_PRESET_IDS = frozenset(PRESET_TO_GENERATION_MODE)


def _normalize_generation_mode(value: Any) -> str:
    mode = str(value or DEFAULT_GENERATION_MODE).strip().lower()
    if mode not in GENERATION_MODES:
        raise ValueError("生成模式必须是 original / lightx2v / v4_600step")
    return mode


def _install_preset_behavior() -> None:
    from . import preset as preset_module

    if getattr(preset_module.Preset.build_prompt, "_v042_h3_fl2va", False):
        return

    original_validate_parameters = preset_module.Preset.validate_parameters
    original_build_prompt = preset_module.Preset.build_prompt
    original_public_metadata = preset_module.Preset.public_metadata

    def validate_parameters_v042(
        self,
        values: dict[str, Any],
        *,
        allow_empty_prompt: bool = False,
    ) -> dict[str, Any]:
        standardizer = self.manifest.get("h3_prompt_standardizer")
        if isinstance(standardizer, dict):
            spec = self.manifest.get("parameters", {}).get("prompt_standardization", {})
            enabled = values.get("prompt_standardization", spec.get("default", True))
            if enabled is True:
                allow_empty_prompt = False
        return original_validate_parameters(
            self, values, allow_empty_prompt=allow_empty_prompt
        )

    def build_prompt_v042(
        self,
        values: dict[str, Any],
        job_id: str,
        media: dict[str, str],
    ) -> dict[str, Any]:
        router = self.manifest.get("h3_aspect_router")
        standardizer = self.manifest.get("h3_prompt_standardizer")
        if not isinstance(router, dict) and not isinstance(standardizer, dict):
            return original_build_prompt(self, values, job_id, media)

        # v0.4 handled reference aspect by dynamically inserting size nodes and
        # overriding the generation node width/height. These H3 workflows own
        # the decision through H3AspectRouter instead, so disable only that
        # legacy injection on an isolated Preset copy.
        temporary = copy.copy(self)
        temporary.manifest = copy.deepcopy(self.manifest)
        temporary.manifest["reference_aspect"] = {
            "parameter_value": "__v042_disabled_reference__",
            "legacy_parameter_value": "__v042_disabled_legacy__",
            "video_parameter_value": "__v042_disabled_video__",
        }
        prompt = original_build_prompt(temporary, values, job_id, media)

        if isinstance(router, dict):
            node_id = str(router["node"])
            input_name = str(router.get("input", "aspect_source"))
            reference_parameter = router.get("reference_parameter", "reference")
            prompt[node_id]["inputs"][input_name] = (
                router.get("reference_value", "auto")
                if values.get("aspect_ratio") == reference_parameter
                else router.get("output_value", "output")
            )

        if isinstance(standardizer, dict):
            node_id = str(standardizer["node"])
            seed_input = str(standardizer.get("seed_input", "seed"))
            prompt[node_id]["inputs"][seed_input] = secrets.randbelow(1 << 64)

        return prompt

    def public_metadata_v042(self):
        result = original_public_metadata(self)
        modes = self.manifest.get("generation_modes")
        if isinstance(modes, dict):
            result["generation_modes"] = copy.deepcopy(modes)
        return result

    validate_parameters_v042._v042_h3_fl2va = True  # type: ignore[attr-defined]
    build_prompt_v042._v042_h3_fl2va = True  # type: ignore[attr-defined]
    public_metadata_v042._v042_h3_fl2va = True  # type: ignore[attr-defined]
    preset_module.Preset.validate_parameters = validate_parameters_v042
    preset_module.Preset.build_prompt = build_prompt_v042
    preset_module.Preset.public_metadata = public_metadata_v042


def _install_job_service() -> None:
    from . import jobs as jobs_module
    from . import preset as preset_module

    if getattr(jobs_module.JobService.create, "_v042_fl2va_modes", False):
        return

    original_create = jobs_module.JobService.create
    original_retry = jobs_module.JobService.retry
    original_public_job = jobs_module.JobService.public_job

    async def create_v042(
        self,
        fields: dict[str, Any],
        uploaded: list[dict[str, Any]],
        job_id: str | None = None,
        *,
        is_test: bool = False,
    ) -> dict[str, Any]:
        routed = dict(fields)
        preset_id = str(routed.get("preset_id") or "")
        if not preset_id:
            return await original_create(
                self, routed, uploaded, job_id, is_test=is_test
            )

        if preset_id == FL2VA_ENTRY_ID:
            try:
                mode = _normalize_generation_mode(routed.get("generation_mode"))
            except ValueError as exc:
                raise preset_module.PresetError(str(exc)) from exc
            routed["preset_id"] = GENERATION_MODES[mode]
        elif preset_id in FL2VA_PRESET_IDS:
            # Direct IDs remain accepted for backward compatibility.
            mode = PRESET_TO_GENERATION_MODE[preset_id]
        else:
            mode = None

        routed.pop("generation_mode", None)
        return await original_create(
            self, routed, uploaded, job_id, is_test=is_test
        )

    async def retry_v042(self, job_id: str) -> dict[str, Any]:
        draft = await original_retry(self, job_id)
        preset_id = str(draft.get("preset_id") or "")
        mode = PRESET_TO_GENERATION_MODE.get(preset_id)
        if mode is not None:
            draft["generation_mode"] = mode
            draft["preset_id"] = FL2VA_ENTRY_ID
        return draft

    def public_job_v042(self, job: dict[str, Any] | None):
        result = original_public_job(self, job)
        if result is None or job is None:
            return result
        preset_id = str(job.get("preset_id") or "")
        mode = PRESET_TO_GENERATION_MODE.get(preset_id)
        if mode is not None:
            result["generation_mode"] = mode
        return result

    create_v042._v042_fl2va_modes = True  # type: ignore[attr-defined]
    retry_v042._v042_fl2va_modes = True  # type: ignore[attr-defined]
    public_job_v042._v042_fl2va_modes = True  # type: ignore[attr-defined]
    jobs_module.JobService.create = create_v042
    jobs_module.JobService.retry = retry_v042
    jobs_module.JobService.public_job = public_job_v042


def install() -> None:
    """Install the v0.4.2 FL2VA mode routing and H3 prompt/aspect contract."""

    _install_preset_behavior()
    _install_job_service()
