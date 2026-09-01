"""Inference profile validation for workflow-family selections.

Profiles are intentionally resolved from manifest metadata.  The Panel must
not manufacture model filenames when a workflow does not declare a compatible
variant.
"""

from __future__ import annotations

from typing import Any


INFERENCE_PROFILES = ("auto", "int8", "fp16_bf16")


class InferenceProfileError(ValueError):
    pass


def normalize_inference_profile(value: Any) -> str:
    profile = str(value or "auto").strip().lower()
    profile = {
        "fp16": "fp16_bf16",
        "bf16": "fp16_bf16",
        "fp16/bf16": "fp16_bf16",
    }.get(profile, profile)
    if profile not in INFERENCE_PROFILES:
        raise InferenceProfileError("模型配置必须是 auto / int8 / fp16_bf16")
    return profile


def resolve_inference_profile(preset: Any, requested: Any = None) -> tuple[str, str]:
    """Return ``(requested, effective)`` for a manifest-backed preset.

    ``auto`` uses the manifest's current asset.  Explicit alternatives must
    be declared by the manifest; otherwise failing is safer than silently
    running a different model than the user selected.
    """

    requested_profile = normalize_inference_profile(requested)
    model_profile = preset.manifest.get("model_profile", {})
    main_model = model_profile.get("main_model", {}) if isinstance(model_profile, dict) else {}
    current = normalize_inference_profile(main_model.get("current", "int8"))
    variants = main_model.get("variants", {}) if isinstance(main_model, dict) else {}

    if requested_profile == "auto":
        return requested_profile, current
    if requested_profile == current:
        return requested_profile, current
    if isinstance(variants, dict) and requested_profile in variants:
        variant = variants[requested_profile]
        if isinstance(variant, dict) and variant.get("available") is False:
            raise InferenceProfileError(f"模型配置 {requested_profile} 当前不可用")
        return requested_profile, requested_profile
    raise InferenceProfileError(
        f"工作流 {preset.id} 未声明可用的模型配置 {requested_profile}"
    )
