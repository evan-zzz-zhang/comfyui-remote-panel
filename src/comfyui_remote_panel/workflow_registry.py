"""Manifest-backed workflow family resolution.

The registry deliberately resolves canonical assets from manifest metadata.  It
does not infer a workflow from its directory name, node labels, or load order.
Legacy ``h3-*`` preset ids remain available to read existing jobs while new
FL2VA submissions resolve through this module.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


FL2VA_FAMILY = "fl2va"
FL2VA_GENERATION_MODES = frozenset({"original", "v4step600", "lightx2v"})
FL2VA_PROMPT_BACKENDS = frozenset({"raw", "ollama", "qwen35"})
CANONICAL_FL2VA_ASSET_IDS = frozenset(
    f"fl2va_{generation_mode}_{prompt_backend}"
    for generation_mode in FL2VA_GENERATION_MODES
    for prompt_backend in FL2VA_PROMPT_BACKENDS
)

REF2VA_FAMILY = "ref2va"
REF2VA_GENERATION_MODES = frozenset({"original", "lightx2v", "v4step600"})
REF2VA_PROMPT_BACKENDS = frozenset({"raw", "ollama", "qwen35"})
CANONICAL_REF2VA_ASSET_IDS = frozenset(
    f"ref2va_{generation_mode}_{prompt_backend}"
    for generation_mode in REF2VA_GENERATION_MODES
    for prompt_backend in REF2VA_PROMPT_BACKENDS
)
REF2VA_LEGACY_TO_KEY = {
    "h3-ref2va": ("original", "raw"),
    "h3-ref2va-lightx2v": ("lightx2v", "raw"),
    "h3-ref2va-v4step600": ("v4step600", "raw"),
}


@dataclass(frozen=True)
class WorkflowAssetKey:
    family: str
    generation_mode: str
    prompt_backend: str


class WorkflowResolutionError(ValueError):
    """Raised when a manifest-backed asset cannot be resolved unambiguously."""


def _canonical(preset: Any) -> bool:
    manifest = getattr(preset, "manifest", {})
    return (
        manifest.get("asset_role") == "canonical"
        and str(manifest.get("family", "")).lower() == FL2VA_FAMILY
    )


def _normalize_key(family: Any, generation_mode: Any, prompt_backend: Any) -> WorkflowAssetKey:
    normalized_family = str(family or "").strip().lower()
    normalized_mode = str(generation_mode or "").strip().lower()
    if normalized_mode == "v4_600step":
        normalized_mode = "v4step600"
    normalized_backend = str(prompt_backend or "").strip().lower()
    if normalized_family != FL2VA_FAMILY:
        raise WorkflowResolutionError(f"unsupported workflow family: {normalized_family or 'empty'}")
    if normalized_mode not in FL2VA_GENERATION_MODES:
        raise WorkflowResolutionError(f"unsupported FL2VA generation mode: {normalized_mode or 'empty'}")
    if normalized_backend not in FL2VA_PROMPT_BACKENDS:
        raise WorkflowResolutionError(f"unsupported FL2VA prompt backend: {normalized_backend or 'empty'}")
    return WorkflowAssetKey(normalized_family, normalized_mode, normalized_backend)


def _normalize_ref2va_key(
    family: Any, generation_mode: Any, prompt_backend: Any
) -> WorkflowAssetKey:
    normalized_family = str(family or "").strip().lower()
    normalized_mode = str(generation_mode or "").strip().lower()
    if normalized_mode == "v4_600step":
        normalized_mode = "v4step600"
    normalized_backend = str(prompt_backend or "").strip().lower()
    if normalized_family != REF2VA_FAMILY:
        raise WorkflowResolutionError(f"unsupported workflow family: {normalized_family or 'empty'}")
    if normalized_mode not in REF2VA_GENERATION_MODES:
        raise WorkflowResolutionError(f"unsupported Ref2VA generation mode: {normalized_mode or 'empty'}")
    if normalized_backend not in REF2VA_PROMPT_BACKENDS:
        raise WorkflowResolutionError(f"unsupported Ref2VA prompt backend: {normalized_backend or 'empty'}")
    return WorkflowAssetKey(normalized_family, normalized_mode, normalized_backend)


def list_fl2va_assets(presets: Mapping[str, Any]) -> list[Any]:
    """Return canonical FL2VA assets in deterministic manifest order."""

    return sorted(
        (preset for preset in presets.values() if _canonical(preset)),
        key=lambda preset: (
            str(preset.manifest.get("generation_mode", "")),
            str(preset.manifest.get("prompt_backend", "")),
            str(preset.id),
        ),
    )


def resolve_fl2va_asset(
    presets: Mapping[str, Any], *, family: Any, generation_mode: Any, prompt_backend: Any
) -> Any:
    """Resolve one canonical FL2VA asset using manifest-declared dimensions."""

    key = _normalize_key(family, generation_mode, prompt_backend)
    matches = [
        preset
        for preset in list_fl2va_assets(presets)
        if str(preset.manifest.get("generation_mode", "")).lower() == key.generation_mode
        and str(preset.manifest.get("prompt_backend", "")).lower() == key.prompt_backend
    ]
    if len(matches) != 1:
        raise WorkflowResolutionError(
            f"expected one FL2VA asset for {key.generation_mode}/{key.prompt_backend}, found {len(matches)}"
        )
    return matches[0]


def list_ref2va_assets(presets: Mapping[str, Any]) -> list[Any]:
    """Return canonical Ref2VA assets in deterministic manifest order."""

    return sorted(
        (
            preset
            for preset in presets.values()
            if getattr(preset, "manifest", {}).get("asset_role") == "canonical"
            and str(getattr(preset, "manifest", {}).get("family", "")).lower() == REF2VA_FAMILY
        ),
        key=lambda preset: (
            str(preset.manifest.get("generation_mode", "")),
            str(preset.manifest.get("prompt_backend", "")),
            str(preset.id),
        ),
    )


def resolve_ref2va_asset(
    presets: Mapping[str, Any], *, family: Any, generation_mode: Any, prompt_backend: Any
) -> Any:
    """Resolve one canonical Ref2VA asset from its declared dimensions."""

    key = _normalize_ref2va_key(family, generation_mode, prompt_backend)
    matches = [
        preset
        for preset in list_ref2va_assets(presets)
        if str(preset.manifest.get("generation_mode", "")).lower() == key.generation_mode
        and str(preset.manifest.get("prompt_backend", "")).lower() == key.prompt_backend
    ]
    if len(matches) != 1:
        raise WorkflowResolutionError(
            f"expected one Ref2VA asset for {key.generation_mode}/{key.prompt_backend}, found {len(matches)}"
        )
    return matches[0]


def asset_key(preset: Any) -> WorkflowAssetKey | None:
    """Read a canonical asset key, returning ``None`` for legacy presets."""

    if not _canonical(preset):
        return None
    family = preset.manifest.get("family")
    return _normalize_key(
        family,
        preset.manifest.get("generation_mode"),
        preset.manifest.get("prompt_backend"),
    )


def ref2va_asset_key(preset: Any) -> WorkflowAssetKey | None:
    """Read a canonical Ref2VA asset key without changing FL2VA routing."""

    manifest = getattr(preset, "manifest", {})
    if (
        manifest.get("asset_role") != "canonical"
        or str(manifest.get("family", "")).strip().lower() != REF2VA_FAMILY
    ):
        return None
    return _normalize_ref2va_key(
        manifest.get("family"),
        manifest.get("generation_mode"),
        manifest.get("prompt_backend"),
    )
