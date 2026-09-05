from __future__ import annotations

import copy
import json
import secrets
import time
from typing import Any

from aiohttp import web

from .workflow_registry import CANONICAL_FL2VA_ASSET_IDS


FL2VA_ENTRY_ID = "h3-fl2va-group"
LEGACY_FL2VA_ENTRY_ID = "h3-fl2va"
DEFAULT_GENERATION_MODE = "v4_600step"
GENERATION_MODES = {
    "original": "h3-fl2va",
    "lightx2v": "h3-fl2va-lightx2v",
    "v4_600step": "h3-fl2va-v4step600",
}
PRESET_TO_GENERATION_MODE = {preset_id: mode for mode, preset_id in GENERATION_MODES.items()}
FL2VA_PRESET_IDS = frozenset(
    set(PRESET_TO_GENERATION_MODE) | set(CANONICAL_FL2VA_ASSET_IDS)
)
_STANDARDIZED_PROMPT_KEY = "_v042_standardized_prompt"


def _normalize_generation_mode(value: Any) -> str:
    mode = str(value or DEFAULT_GENERATION_MODE).strip().lower()
    if mode not in GENERATION_MODES:
        raise ValueError("生成模式必须是 original / lightx2v / v4_600step")
    return mode


def _connection_source(value: Any) -> str | None:
    if isinstance(value, (list, tuple)) and value:
        return str(value[0])
    return None


def _preview_node_for_standardized_prompt(preset: Any) -> str | None:
    standardizer = preset.manifest.get("h3_prompt_standardizer")
    if not isinstance(standardizer, dict) or standardizer.get("node") is None:
        return None
    standardizer_node = str(standardizer["node"])
    switches = {
        str(node_id)
        for node_id, node in preset.template.items()
        if isinstance(node, dict)
        and node.get("class_type") == "LazySwitchKJ"
        and _connection_source((node.get("inputs") or {}).get("on_true")) == standardizer_node
    }
    for node_id, node in preset.template.items():
        if not isinstance(node, dict) or node.get("class_type") != "PreviewAny":
            continue
        if _connection_source((node.get("inputs") or {}).get("source")) in switches:
            return str(node_id)
    return None


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


def _standardized_prompt_from_history(service: Any, job: dict[str, Any], entry: dict[str, Any]) -> str | None:
    preset = service.presets.get(str(job.get("preset_id") or ""))
    if preset is None or preset.id not in FL2VA_PRESET_IDS:
        return None
    values = job.get("input_values") if isinstance(job.get("input_values"), dict) else {}
    enabled = values.get("prompt_standardization")
    if enabled is None:
        spec = preset.manifest.get("parameters", {}).get("prompt_standardization", {})
        enabled = spec.get("default", True) if isinstance(spec, dict) else True
    if enabled is not True:
        return None
    preview_node = _preview_node_for_standardized_prompt(preset)
    outputs = entry.get("outputs") if isinstance(entry, dict) else None
    if preview_node is None or not isinstance(outputs, dict):
        return None
    text = _history_text(outputs.get(preview_node))
    return text if isinstance(text, str) and text.strip() else None


def _install_database_behavior() -> None:
    from . import db as db_module

    if hasattr(db_module.Database, "set_standardized_prompt_v042"):
        return

    async def set_standardized_prompt_v042(self, job_id: str, prompt: str) -> dict[str, Any] | None:
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
                values[_STANDARDIZED_PROMPT_KEY] = prompt
                connection.execute(
                    "UPDATE jobs SET input_values_json = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(values, ensure_ascii=False), time.time(), job_id),
                )
        return await self.get_job(job_id)

    db_module.Database.set_standardized_prompt_v042 = set_standardized_prompt_v042


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
        variant_model_overrides: dict[str, dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        router = self.manifest.get("h3_aspect_router")
        standardizer = self.manifest.get("h3_prompt_standardizer")
        if not isinstance(router, dict) and not isinstance(standardizer, dict):
            return original_build_prompt(self, values, job_id, media, variant_model_overrides)

        if isinstance(router, dict):
            reference_parameter = router.get("reference_parameter", "reference")
            if values.get("aspect_ratio") == reference_parameter and not any(
                role in media for role in ("first", "last")
            ):
                raise preset_module.PresetError("参考图比例需要至少上传一张参考图")

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
        prompt = original_build_prompt(temporary, values, job_id, media, variant_model_overrides)

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
    original_apply_history = jobs_module.JobService._apply_history

    async def require_enabled(self, preset_id: str, *, is_test: bool = False) -> None:
        if is_test:
            return
        get_workflow = getattr(self.db, "get_workflow", None)
        if not callable(get_workflow):
            return
        item = await get_workflow(preset_id)
        if item is not None and item.get("status") != "enabled":
            mode = PRESET_TO_GENERATION_MODE.get(preset_id, preset_id)
            raise preset_module.PresetError(f"生成模式 {mode} 对应工作流已禁用")

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

        # The virtual group entry keeps the user-facing FL2VA workflow separate
        # from the physical original preset. The previous v0.4.2 entry contract
        # (h3-fl2va + generation_mode) remains accepted while this branch is in
        # development, and h3-fl2va without generation_mode again means original.
        unified_request = preset_id == FL2VA_ENTRY_ID or (
            preset_id == LEGACY_FL2VA_ENTRY_ID and "generation_mode" in routed
        )
        if unified_request:
            try:
                mode = _normalize_generation_mode(routed.get("generation_mode"))
            except ValueError as exc:
                raise preset_module.PresetError(str(exc)) from exc
            target_id = GENERATION_MODES[mode]
            await require_enabled(self, target_id, is_test=is_test)
            routed["preset_id"] = target_id
        elif preset_id in FL2VA_PRESET_IDS:
            await require_enabled(self, preset_id, is_test=is_test)

        routed.pop("generation_mode", None)
        return await original_create(
            self, routed, uploaded, job_id, is_test=is_test
        )

    async def retry_v042(self, job_id: str) -> dict[str, Any]:
        draft = await original_retry(self, job_id)
        values = draft.get("values")
        if isinstance(values, dict):
            values.pop(_STANDARDIZED_PROMPT_KEY, None)
        preset_id = str(draft.get("preset_id") or "")
        mode = PRESET_TO_GENERATION_MODE.get(preset_id)
        if mode is not None:
            draft["generation_mode"] = mode
            draft["preset_id"] = FL2VA_ENTRY_ID
        return draft

    async def apply_history_v042(self, job: dict[str, Any], entry: dict[str, Any]) -> dict[str, Any]:
        standardized_prompt = _standardized_prompt_from_history(self, job, entry)
        if standardized_prompt:
            await self.db.set_standardized_prompt_v042(job["id"], standardized_prompt)
        return await original_apply_history(self, job, entry)

    def public_job_v042(self, job: dict[str, Any] | None):
        result = original_public_job(self, job)
        if result is None or job is None:
            return result
        values = dict(result.get("input_values") or {})
        result["standardized_prompt"] = values.pop(_STANDARDIZED_PROMPT_KEY, None)
        result["input_values"] = values
        preset_id = str(job.get("preset_id") or "")
        mode = PRESET_TO_GENERATION_MODE.get(preset_id)
        if mode is not None:
            result["generation_mode"] = mode
        return result

    create_v042._v042_fl2va_modes = True  # type: ignore[attr-defined]
    retry_v042._v042_fl2va_modes = True  # type: ignore[attr-defined]
    apply_history_v042._v042_fl2va_modes = True  # type: ignore[attr-defined]
    public_job_v042._v042_fl2va_modes = True  # type: ignore[attr-defined]
    jobs_module.JobService.create = create_v042
    jobs_module.JobService.retry = retry_v042
    jobs_module.JobService._apply_history = apply_history_v042
    jobs_module.JobService.public_job = public_job_v042


def _virtual_metadata(presets: dict[str, Any]) -> dict[str, Any] | None:
    source = presets.get(LEGACY_FL2VA_ENTRY_ID) or next(
        (preset for preset in presets.values() if preset.manifest.get("family") == "fl2va"),
        None,
    )
    if source is None:
        return None
    result = source.public_metadata()
    result.update({
        "id": FL2VA_ENTRY_ID,
        "name": "MiniMax H3 FL2VA",
        "description": "首尾帧视频生成 · 原版 / LightX2V / v4_600step",
        "asset_role": "virtual",
        "available": True,
    })
    return result


def _install_app() -> None:
    from . import app as app_module

    if getattr(app_module.create_app, "_v042_fl2va_api", False):
        return
    original = app_module.create_app

    def create_app_v042(*args: Any, **kwargs: Any):
        application = original(*args, **kwargs)

        @web.middleware
        async def v042_api(request: web.Request, handler):
            response = await handler(request)
            if request.method != "GET" or request.path != "/api/presets" or not isinstance(response, web.Response):
                return response
            try:
                payload = json.loads(response.text or "{}")
            except (TypeError, json.JSONDecodeError):
                return response
            items = payload.get("items") if isinstance(payload, dict) else None
            if not isinstance(items, list):
                return response
            items = [item for item in items if item.get("id") != FL2VA_ENTRY_ID]
            virtual = _virtual_metadata(application["presets"])
            if virtual is not None:
                items.append(virtual)
            replacement = web.json_response({"items": items}, status=response.status)
            for key, value in response.headers.items():
                if key.lower() not in {"content-type", "content-length"}:
                    replacement.headers[key] = value
            return replacement

        application.middlewares.insert(0, v042_api)
        return application

    create_app_v042._v042_fl2va_api = True  # type: ignore[attr-defined]
    app_module.create_app = create_app_v042


def install() -> None:
    """Install the v0.4.2 FL2VA mode routing and H3 prompt/aspect contract."""

    _install_database_behavior()
    _install_preset_behavior()
    _install_job_service()
    _install_app()
