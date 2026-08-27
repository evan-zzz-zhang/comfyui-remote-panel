from __future__ import annotations

import sqlite3

from .config import Config
from .db import Database
from .preset import Preset, load_presets, preset_from_definition


async def load_doctor_presets(config: Config) -> dict[str, Preset]:
    """Load packaged presets plus enabled persisted user workflow revisions.

    Built-in packaged presets remain authoritative so Doctor keeps their normal
    optional-dependency severity. A source checkout may also expose the same
    packaged workflow IDs through ``config.workflow_dir``; those duplicate
    copies must not replace the packaged presets or Doctor will mistake optional
    built-ins for user workflows and promote missing models to FAIL.

    Non-builtin Configurator workflows live in the configured workflow directory
    and/or panel.db and are added explicitly for compatibility reporting. Draft
    or disabled persisted workflows do not block machine readiness.
    """
    packaged = load_presets()
    presets = dict(packaged)

    configured = load_presets(config.workflow_dir)
    for preset_id, preset in configured.items():
        if preset_id not in packaged:
            presets[preset_id] = preset

    if not config.database_path.is_file():
        return presets

    database = Database(config.database_path)
    try:
        rows = await database.list_workflows()
    except sqlite3.Error:
        return presets

    for item in rows:
        if item.get("builtin") and item["id"] in presets:
            continue
        if item.get("status") != "enabled":
            continue
        definition = item.get("definition")
        if not isinstance(definition, dict):
            continue
        preset = preset_from_definition(definition, config.workflow_dir / str(item["id"]))
        presets[preset.id] = preset
    return presets
