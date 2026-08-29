from __future__ import annotations

from typing import Any

from . import v04


def install() -> None:
    """Small compatibility refinements that depend on the v0.4 core being installed."""
    original_media_resolution_for_role = v04._media_resolution_for_role

    def media_resolution_for_role(
        preset: Any, role: str, overrides: dict[str, Any]
    ) -> dict[str, Any]:
        # The creation UI intentionally collapses equal image-slot policies into
        # one `image` control. Apply that shared override to frame-pair roles
        # (`first`/`last`) and generic image slots alike unless a per-role value
        # was explicitly provided.
        effective = overrides
        if role not in overrides and isinstance(overrides.get("image"), dict):
            effective = dict(overrides)
            effective[role] = overrides["image"]
        return original_media_resolution_for_role(preset, role, effective)

    v04._media_resolution_for_role = media_resolution_for_role

    # v0.3 rows need a fallback seed value, but a v0.4 randomize job deliberately
    # has no base seed: only actual_seed is meaningful for that run.
    from .db import Database

    original_job_from_row = Database._job_from_row

    def job_from_row(self, row, files):
        item = original_job_from_row(self, row, files)
        if item.get("seed_policy") == "randomize":
            item["seed_value"] = None
        return item

    Database._job_from_row = job_from_row
