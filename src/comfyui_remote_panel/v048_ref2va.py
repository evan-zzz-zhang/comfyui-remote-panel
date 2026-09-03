"""v0.4.8 Ref2VA workflow-family routing.

The Ref2VA path is intentionally layered on top of the accepted v0.4.7
implementation.  Its collection media contract stays in ``Preset`` while the
family-specific routing and prompt capture live here.
"""

from __future__ import annotations

import copy
import json
import time
from typing import Any

from aiohttp import web

from .inference_profile import InferenceProfileError, normalize_inference_profile, resolve_inference_profile
from .workflow_registry import (
    CANONICAL_REF2VA_ASSET_IDS,
    REF2VA_FAMILY,
    REF2VA_GENERATION_MODES,
    REF2VA_LEGACY_TO_KEY,
    REF2VA_PROMPT_BACKENDS,
    WorkflowAssetKey,
    ref2va_asset_key,
    resolve_ref2va_asset,
)


REF2VA_ENTRY_ID = "h3-ref2va-group"
DEFAULT_REF2VA_GENERATION_MODE = "v4step600"
DEFAULT_REF2VA_PROMPT_BACKEND = "raw"
DEFAULT_REF2VA_INFERENCE_PROFILE = "auto"
REF2VA_LEGACY_IDS = frozenset(REF2VA_LEGACY_TO_KEY)
REF2VA_PRESET_IDS = frozenset(set(REF2VA_LEGACY_IDS) | set(CANONICAL_REF2VA_ASSET_IDS))
_STANDARDIZED_PROMPT_KEY = "_v048_standardized_prompt"
_RECOVERY_BATCH_SIZE = 25
_RECOVERY_MAX_ATTEMPTS = 3


def _mode(value: Any) -> str:
    value = str(value or DEFAULT_REF2VA_GENERATION_MODE).strip().lower()
    if value == "v4_600step":
        value = "v4step600"
    if value not in REF2VA_GENERATION_MODES:
        raise ValueError("Ref2VA 生成模式必须是 original / lightx2v / v4step600")
    return value


def _backend(value: Any) -> str:
    value = str(value or DEFAULT_REF2VA_PROMPT_BACKEND).strip().lower()
    if value in {"off", "raw"}:
        value = "raw"
    if value not in REF2VA_PROMPT_BACKENDS:
        raise ValueError("Ref2VA Prompt Backend 必须是 raw / ollama / qwen35")
    return value


def _display_mode(mode: str) -> str:
    return mode


def _legacy_key(preset_id: str) -> WorkflowAssetKey | None:
    value = REF2VA_LEGACY_TO_KEY.get(preset_id)
    return WorkflowAssetKey(REF2VA_FAMILY, *value) if value is not None else None


def _canonical_key(preset: Any) -> WorkflowAssetKey | None:
    return ref2va_asset_key(preset)


def _history_text(value: Any, preferred: tuple[str, ...] = ()) -> str | None:
    if isinstance(value, dict):
        for key in preferred:
            if key in value:
                text = _history_text(value[key])
                if text:
                    return text
        for key in ("text", "value", "string", "standardized_prompt", "final_prompt"):
            if key in value:
                text = _history_text(value[key])
                if text:
                    return text
    elif isinstance(value, (list, tuple)):
        for item in value:
            text = _history_text(item, preferred)
            if text:
                return text
    elif isinstance(value, str) and value.strip():
        return value
    return None


def _captured_prompt(service: Any, job: dict[str, Any], entry: dict[str, Any]) -> str | None:
    preset = service.presets.get(str(job.get("preset_id") or ""))
    if preset is None or str(preset.manifest.get("family", "")).lower() != REF2VA_FAMILY:
        return None
    capture = preset.manifest.get("prompt_capture")
    if not isinstance(capture, dict):
        return None
    outputs = entry.get("outputs") if isinstance(entry, dict) else None
    if not isinstance(outputs, dict):
        return None

    def read(spec: Any) -> str | None:
        if not isinstance(spec, dict) or spec.get("history_node") is None:
            return None
        value = outputs.get(str(spec["history_node"]))
        return _history_text(value, (str(spec.get("history_field")),) if spec.get("history_field") else ())

    text = read(capture)
    if text:
        return text
    fallbacks = capture.get("fallbacks", [])
    if isinstance(fallbacks, list):
        for fallback in fallbacks:
            text = read(fallback)
            if text:
                return text
    return None


def _representative_source(graph: dict[str, Any], media: dict[str, str]) -> str | None:
    image_roles = [role for role in media if role == "first" or role == "image_0"]
    image_roles += [role for role in media if role.startswith("image_") and role not in image_roles]
    for role in image_roles:
        filename = media.get(role)
        for node_id, node in graph.items():
            if isinstance(node, dict) and node.get("class_type") == "LoadImage":
                if (node.get("inputs") or {}).get("image") == filename:
                    return str(node_id)

    video_roles = [role for role in media if role == "video_0"]
    video_roles += [role for role in media if role.startswith("video_") and role not in video_roles]
    for role in video_roles:
        filename = media.get(role)
        load_id = None
        for node_id, node in graph.items():
            if isinstance(node, dict) and node.get("class_type") == "LoadVideo":
                if (node.get("inputs") or {}).get("file") == filename:
                    load_id = str(node_id)
                    break
        if load_id is None:
            continue
        for node_id, node in graph.items():
            if isinstance(node, dict) and node.get("class_type") == "GetVideoComponents":
                if (node.get("inputs") or {}).get("video") == [load_id, 0]:
                    frame_id = "9500"
                    while frame_id in graph:
                        frame_id = str(int(frame_id) + 1)
                    graph[frame_id] = {
                        "class_type": "ImageFromBatch",
                        "inputs": {"images": [str(node_id), 0], "batch_index": 0, "length": 1},
                    }
                    return frame_id
    return None


def _install_database() -> None:
    from . import db as db_module

    if getattr(db_module.Database.save_workflow, "_v048_ref2va_status", False):
        return
    original = db_module.Database.save_workflow

    async def save_workflow_v048(self, definition, *, status="draft", builtin=False):
        manifest = definition.get("manifest", {}) if isinstance(definition, dict) else {}
        if builtin and manifest.get("asset_role") == "canonical" and manifest.get("family") == REF2VA_FAMILY:
            legacy_ids = manifest.get("legacy_ids", [])
            async with self._lock:
                with self._connect() as connection:
                    canonical = connection.execute(
                        "SELECT 1 FROM workflows WHERE id = ? LIMIT 1", (manifest.get("id"),)
                    ).fetchone()
                    if canonical is None:
                        for legacy_id in legacy_ids if isinstance(legacy_ids, list) else []:
                            row = connection.execute(
                                "SELECT status FROM workflows WHERE id = ? ORDER BY revision DESC LIMIT 1",
                                (legacy_id,),
                            ).fetchone()
                            if row is not None:
                                status = row["status"]
                                break
        return await original(self, definition, status=status, builtin=builtin)

    save_workflow_v048._v048_ref2va_status = True  # type: ignore[attr-defined]
    db_module.Database.save_workflow = save_workflow_v048


def _install_preset() -> None:
    from . import preset as preset_module

    if getattr(preset_module.Preset.build_prompt, "_v048_ref2va_prompt", False):
        return
    original = preset_module.Preset.build_prompt

    def build_prompt_v048(self, values, job_id, media, variant_model_overrides=None):
        graph = original(self, values, job_id, media, variant_model_overrides)
        if str(self.manifest.get("family", "")).lower() != REF2VA_FAMILY:
            return graph
        backend = str(self.manifest.get("prompt_backend", "raw")).lower()
        standardizer = self.manifest.get("prompt_standardizer")
        if backend == "raw" or not isinstance(standardizer, dict):
            return graph
        node_id = str(standardizer.get("node") or "")
        if node_id not in graph:
            return graph
        # Native Ref2VA standardization consumes the complete collection
        # binding on its conditioning node. The legacy generic standardizer
        # and the Qwen writer still accept the representative first frame.
        node_class = graph[node_id].get("class_type")
        if node_class == "H3Ref2VAOllamaConditioning":
            return graph
        if node_class not in {"H3PromptStandardizer", "H3OfficialSkillPromptWriterQwen"}:
            return graph
        representative = _representative_source(graph, media)
        inputs = graph[node_id].setdefault("inputs", {})
        inputs.pop("last_frame", None)
        if representative is None:
            inputs.pop("first_frame", None)
        else:
            inputs["first_frame"] = [representative, 0]
        return graph

    build_prompt_v048._v048_ref2va_prompt = True  # type: ignore[attr-defined]
    preset_module.Preset.build_prompt = build_prompt_v048


def _install_jobs() -> None:
    from . import jobs as jobs_module
    from . import preset as preset_module

    if getattr(jobs_module.JobService.create, "_v048_ref2va", False):
        return
    original_create = jobs_module.JobService.create
    original_retry = jobs_module.JobService.retry
    original_apply_history = jobs_module.JobService._apply_history
    original_reconcile = jobs_module.JobService.reconcile_once
    original_public = jobs_module.JobService.public_job

    async def require_enabled(self, preset_id: str) -> None:
        getter = getattr(self.db, "get_workflow", None)
        if not callable(getter):
            return
        item = await getter(preset_id)
        if item is not None and item.get("status") != "enabled":
            raise preset_module.PresetError("Ref2VA 对应工作流已禁用")

    async def resolve_profile(self, routed: dict[str, Any], preset: Any) -> None:
        try:
            requested, effective = resolve_inference_profile(
                preset, routed.get("inference_profile", DEFAULT_REF2VA_INFERENCE_PROFILE)
            )
        except InferenceProfileError as exc:
            raise preset_module.PresetError(str(exc)) from exc
        current = normalize_inference_profile(
            preset.manifest.get("model_profile", {}).get("main_model", {}).get("current", "int8")
        )
        overrides: dict[str, dict[str, str]] = {}
        resolver = getattr(self.comfy, "resolve_preset_variant", None)
        validator = getattr(self.comfy, "validate_preset_variant", None)
        if effective != current and callable(resolver):
            diagnostics, overrides = await resolver(preset, effective)
            if diagnostics:
                raise preset_module.PresetError("；".join(diagnostics[:3]))
        elif effective != current and callable(validator):
            diagnostics = await validator(preset, effective)
            if diagnostics:
                raise preset_module.PresetError("；".join(diagnostics[:3]))
        routed["_v048_inference_profile"] = requested
        routed["_v048_effective_inference_profile"] = effective
        routed["_v048_variant_model_overrides"] = overrides
        routed.pop("inference_profile", None)

    async def create_v048(self, fields, uploaded, job_id=None, *, is_test=False):
        routed = dict(fields)
        preset_id = str(routed.get("preset_id") or "")
        if preset_id == REF2VA_ENTRY_ID:
            try:
                mode = _mode(routed.get("generation_mode"))
                backend = _backend(routed.get("prompt_backend"))
                target = resolve_ref2va_asset(
                    self.presets, family=REF2VA_FAMILY,
                    generation_mode=mode, prompt_backend=backend,
                )
            except ValueError as exc:
                raise preset_module.PresetError(str(exc)) from exc
            await require_enabled(self, target.id)
            await resolve_profile(self, routed, target)
            routed["_v048_generation_mode"] = mode
            routed["_v048_prompt_backend"] = backend
            routed["preset_id"] = target.id
            routed.pop("generation_mode", None)
            routed.pop("prompt_backend", None)
            return await original_create(self, routed, uploaded, job_id, is_test=is_test)

        preset = self.presets.get(preset_id)
        key = _canonical_key(preset)
        legacy = _legacy_key(preset_id)
        if key is not None:
            routed["_v048_generation_mode"] = key.generation_mode
            routed["_v048_prompt_backend"] = key.prompt_backend
            await resolve_profile(self, routed, preset)
        elif legacy is not None:
            routed["_v048_generation_mode"] = legacy.generation_mode
            routed["_v048_prompt_backend"] = legacy.prompt_backend
            routed["_v048_inference_profile"] = "auto"
            routed["_v048_effective_inference_profile"] = "int8"
        return await original_create(self, routed, uploaded, job_id, is_test=is_test)

    async def retry_v048(self, job_id: str):
        draft = await original_retry(self, job_id)
        preset_id = str(draft.get("preset_id") or "")
        presets = getattr(self, "presets", {})
        preset = presets.get(preset_id) if isinstance(presets, dict) else None
        key = _canonical_key(preset) or _legacy_key(preset_id)
        if key is None:
            return draft
        values = draft.setdefault("values", {})
        requested = values.get("_v048_inference_profile", "auto")
        effective = values.get("_v048_effective_inference_profile", "int8")
        mode, backend = key.generation_mode, key.prompt_backend
        draft.update({
            "preset_id": REF2VA_ENTRY_ID,
            "generation_mode": _display_mode(mode),
            "prompt_backend": backend,
            "inference_profile": requested,
        })
        values.update({
            "generation_mode": mode,
            "prompt_backend": backend,
            "inference_profile": requested,
            "effective_inference_profile": effective,
        })
        return draft

    async def apply_history_v048(self, job, entry):
        result = await original_apply_history(self, job, entry)
        text = _captured_prompt(self, job, entry)
        if text:
            setter = getattr(self.db, "set_standardized_prompt_v042", None)
            if callable(setter):
                refreshed = await setter(job["id"], text)
                if refreshed is not None:
                    result = refreshed
        return result

    async def recover_v048(self):
        list_succeeded = getattr(self.db, "succeeded_jobs", None)
        setter = getattr(self.db, "set_standardized_prompt_v042", None)
        if not callable(list_succeeded) or not callable(setter):
            return
        now = time.time()
        if now - float(getattr(self, "_v048_recovery_at", 0) or 0) < 30:
            return
        self._v048_recovery_at = now
        attempts = getattr(self, "_v048_recovery_attempts", {})
        self._v048_recovery_attempts = attempts
        jobs = await list_succeeded(limit=_RECOVERY_BATCH_SIZE, offset=0)
        for item in jobs:
            preset = self.presets.get(str(item.get("preset_id") or ""))
            if preset is None or preset.manifest.get("family") != REF2VA_FAMILY:
                continue
            if not any(file.get("role") == "output" for file in item.get("files", [])):
                continue
            values = item.get("input_values") if isinstance(item.get("input_values"), dict) else {}
            if values.get("_v042_standardized_prompt") or values.get(_STANDARDIZED_PROMPT_KEY):
                attempts.pop(str(item.get("id")), None)
                continue
            item_id = str(item.get("id"))
            if attempts.get(item_id, 0) >= _RECOVERY_MAX_ATTEMPTS:
                continue
            attempts[item_id] = attempts.get(item_id, 0) + 1
            history = await self.comfy.history(item_id)
            entry = history.get(item_id) if isinstance(history, dict) else None
            text = _captured_prompt(self, item, entry) if isinstance(entry, dict) else None
            if text:
                refreshed = await setter(item_id, text)
                if refreshed is not None:
                    attempts.pop(item_id, None)
                    self.events.publish("job", self.public_job(refreshed))

    async def reconcile_v048(self):
        await original_reconcile(self)
        await recover_v048(self)

    def public_job_v048(self, job):
        result = original_public(self, job)
        if result is None or job is None:
            return result
        preset_id = str(job.get("preset_id") or "")
        preset = self.presets.get(preset_id)
        key = _canonical_key(preset) or _legacy_key(preset_id)
        if key is None:
            return result
        mode, backend = key.generation_mode, key.prompt_backend
        values = result.get("input_values") if isinstance(result.get("input_values"), dict) else {}
        result["generation_mode"] = _display_mode(mode)
        result["prompt_backend"] = backend
        result["inference_profile"] = values.pop("_v048_inference_profile", "auto")
        result["effective_inference_profile"] = values.pop("_v048_effective_inference_profile", "int8")
        values.pop("_v048_generation_mode", None)
        values.pop("_v048_prompt_backend", None)
        values.pop("_v048_variant_model_overrides", None)
        result["input_values"] = values
        if backend == "raw":
            result["standardized_prompt"] = None
        return result

    create_v048._v048_ref2va = True  # type: ignore[attr-defined]
    jobs_module.JobService.create = create_v048
    jobs_module.JobService.retry = retry_v048
    jobs_module.JobService._apply_history = apply_history_v048
    jobs_module.JobService.reconcile_once = reconcile_v048
    jobs_module.JobService.public_job = public_job_v048


def _virtual_metadata(presets: dict[str, Any]) -> dict[str, Any] | None:
    source = presets.get("h3-ref2va") or next(
        (preset for preset in presets.values() if preset.manifest.get("family") == REF2VA_FAMILY), None
    )
    if source is None:
        return None
    result = source.public_metadata()
    result.update({
        "id": REF2VA_ENTRY_ID,
        "name": "MiniMax H3 Ref2VA",
        "description": "参考素材视频生成 · 原版 / LightX2V / v4_600step",
        "asset_role": "virtual",
        "available": True,
        "generation_modes": {
            "default": DEFAULT_REF2VA_GENERATION_MODE,
            "values": {
                "v4step600": {"label": "v4_600step", "preset_id": "ref2va_v4step600_raw"},
                "lightx2v": {"label": "LightX2V", "preset_id": "ref2va_lightx2v_raw"},
                "original": {"label": "原版", "preset_id": "ref2va_original_raw"},
            },
        },
        "prompt_backends": {
            "default": DEFAULT_REF2VA_PROMPT_BACKEND,
            "values": {
                "raw": {"label": "原始提示词"}, "ollama": {"label": "Ollama 标准化"},
                "qwen35": {"label": "Qwen3.5 标准化"},
            },
        },
        "inference_profiles": ["int8", "fp16_bf16"],
    })
    parameters = result.get("parameters")
    if isinstance(parameters, dict):
        for name, value in (("scheduler", "beta"), ("sampler", "euler"), ("steps", 8)):
            spec = parameters.get(name)
            if isinstance(spec, dict):
                spec["default"] = value
    return result


def _install_app() -> None:
    from . import app as app_module

    if getattr(app_module.create_app, "_v048_ref2va", False):
        return
    original = app_module.create_app

    def create_app_v048(*args: Any, **kwargs: Any):
        application = original(*args, **kwargs)

        @web.middleware
        async def v048_api(request: web.Request, handler):
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
            items = [item for item in items if str(item.get("family", "")).lower() != REF2VA_FAMILY]
            virtual = _virtual_metadata(application["presets"])
            if virtual is not None:
                items.append(virtual)
            replacement = web.json_response({"items": items}, status=response.status)
            for key, value in response.headers.items():
                if key.lower() not in {"content-type", "content-length"}:
                    replacement.headers[key] = value
            return replacement

        application.middlewares.insert(0, v048_api)
        return application

    create_app_v048._v048_ref2va = True  # type: ignore[attr-defined]
    app_module.create_app = create_app_v048


def install() -> None:
    _install_database()
    _install_preset()
    _install_jobs()
    _install_app()
