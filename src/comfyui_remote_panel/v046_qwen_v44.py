from __future__ import annotations

import copy
from typing import Any

from .files import FileStore


_VARIANT = "qwen35-v4.4"
_HISTORY_FALLBACK_NODE = "177"
_HISTORY_FALLBACK_FIELD = "text"


def _find_named_text(value: Any, field: str) -> str | None:
    if isinstance(value, dict):
        if field in value:
            candidate = value[field]
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
            if isinstance(candidate, (list, tuple)):
                for item in candidate:
                    if isinstance(item, str) and item.strip():
                        return item.strip()
        for nested in value.values():
            text = _find_named_text(nested, field)
            if text:
                return text
    elif isinstance(value, (list, tuple)):
        for nested in value:
            text = _find_named_text(nested, field)
            if text:
                return text
    return None


def _install_media_validation() -> None:
    from . import preset as preset_module

    if getattr(preset_module.Preset.validate_media_roles, "_v046_qwen_v44", False):
        return

    original_validate_media_roles = preset_module.Preset.validate_media_roles

    def validate_media_roles_v046_qwen_v44(self, roles: set[str]) -> tuple[str, bool]:
        if self.manifest.get("workflow_variant") != _VARIANT:
            return original_validate_media_roles(self, roles)
        allowed = {"first", "last"}
        if roles - allowed:
            raise preset_module.PresetError("工作流收到了未声明的媒体槽位")
        return ("纯文字" if not roles else f"{len(roles)} 个输入", bool(roles))

    validate_media_roles_v046_qwen_v44._v046_qwen_v44 = True  # type: ignore[attr-defined]
    preset_module.Preset.validate_media_roles = validate_media_roles_v046_qwen_v44


def _install_prompt_builder() -> None:
    from . import preset as preset_module

    if getattr(preset_module.Preset.build_prompt, "_v046_qwen_v44", False):
        return

    original_build_prompt = preset_module.Preset.build_prompt

    def build_prompt_v046_qwen_v44(
        self,
        values: dict[str, Any],
        job_id: str,
        media: dict[str, str],
        variant_model_overrides: dict[str, dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        if self.manifest.get("workflow_variant") != _VARIANT:
            return original_build_prompt(self, values, job_id, media, variant_model_overrides)

        self.validate_media_roles(set(media))
        normalized = self.validate_parameters(values, allow_empty_prompt=False)
        reference = self.manifest.get("reference_aspect", {})
        aspect_value = normalized.get("aspect_ratio")
        reference_values = {
            reference.get("parameter_value"),
            reference.get("legacy_parameter_value", "reference"),
            reference.get("video_parameter_value"),
        }
        use_reference = aspect_value in reference_values

        prompt = copy.deepcopy(self.template)
        for node_id, inputs in self.model_overrides.items():
            prompt[node_id]["inputs"].update(inputs)
        effective_profile = values.get("_v047_effective_inference_profile")
        if effective_profile:
            self._apply_variant_model_overrides(prompt, effective_profile, variant_model_overrides)

        for name, spec in self.manifest["parameters"].items():
            value = normalized[name]
            if name == "seed":
                value = int(value)
            if spec["type"] == "enum":
                value = spec["values"][value]
                if isinstance(value, str) and value.startswith("__reference_"):
                    continue
            prompt[str(spec["node"])]["inputs"][spec["input"]] = value

        output_key = FileStore.storage_key(job_id) if len(str(job_id)) >= 36 else str(job_id)
        output_node = prompt[self.output_node]
        if "filename_prefix" in output_node.get("inputs", {}):
            output_node["inputs"]["filename_prefix"] = f"h3_remote/{output_key}"

        media_binding = self.media_binding
        if media_binding.get("type") != "slots":
            raise preset_module.PresetError("Qwen v4.4 媒体绑定配置无效")
        slots = media_binding.get("slots", {})
        for role, filename in media.items():
            slot = slots.get(role)
            if not isinstance(slot, dict):
                raise preset_module.PresetError("工作流收到了未声明的媒体槽位")
            node_id = str(slot.get("node"))
            input_name = slot.get("input")
            prompt[node_id]["inputs"][input_name] = filename

        if use_reference and not any(role in media for role in ("first", "last")):
            raise preset_module.PresetError("参考图比例需要至少上传一张参考图")

        if reference.get("strategy") == "resolver_toggle":
            resolver_node = str(reference.get("resolver_node"))
            resolver_input = str(reference.get("resolver_input") or "use_reference_aspect")
            if resolver_node not in prompt or resolver_input not in prompt[resolver_node].get("inputs", {}):
                raise preset_module.PresetError("Qwen v4.4 参考画幅绑定无效")
            prompt[resolver_node]["inputs"][resolver_input] = bool(use_reference)

        return prompt

    build_prompt_v046_qwen_v44._v046_qwen_v44 = True  # type: ignore[attr-defined]
    preset_module.Preset.build_prompt = build_prompt_v046_qwen_v44


def _install_standardized_prompt_capture() -> None:
    from . import v046 as v046_module

    original = v046_module._qwen_standardized_prompt
    if getattr(original, "_v046_qwen_v44", False):
        return

    def qwen_standardized_prompt_v44(service: Any, job: dict[str, Any], entry: dict[str, Any]) -> str | None:
        preset = service.presets.get(str(job.get("preset_id") or ""))
        if preset is None or preset.manifest.get("workflow_variant") != _VARIANT:
            return original(service, job, entry)

        standardizer = preset.manifest.get("prompt_standardizer")
        outputs = entry.get("outputs") if isinstance(entry, dict) else None
        if not isinstance(standardizer, dict) or not isinstance(outputs, dict):
            return None
        history_node = standardizer.get("history_node")
        history_field = standardizer.get("history_field")
        if history_node is None or not isinstance(history_field, str):
            return None

        text = _find_named_text(outputs.get(str(history_node)), history_field)
        if text:
            return text

        # H3SaveVideoWithPromptMetadata writes run metadata into the video file,
        # but real ComfyUI history does not always expose that metadata in the
        # save node's output payload. PreviewAny(177) is wired directly to
        # H3OfficialSkillPromptWriterQwen output 0 (the final prompt used by H3),
        # so it is the reliable history fallback while standardization is fixed on.
        return _find_named_text(
            outputs.get(_HISTORY_FALLBACK_NODE), _HISTORY_FALLBACK_FIELD
        )

    qwen_standardized_prompt_v44._v046_qwen_v44 = True  # type: ignore[attr-defined]
    v046_module._qwen_standardized_prompt = qwen_standardized_prompt_v44


def install() -> None:
    """Adapt the bundled ComfyUI Qwen route to the upstream v4.4 API graphs only."""

    _install_media_validation()
    _install_prompt_builder()
    _install_standardized_prompt_capture()
