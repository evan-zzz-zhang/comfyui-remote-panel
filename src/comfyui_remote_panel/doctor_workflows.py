from __future__ import annotations

import sqlite3

from .config import Config
from .db import Database
from .preset import Preset, load_presets, preset_from_definition


async def load_doctor_presets(config: Config) -> dict[str, Preset]:
    """Load packaged presets plus latest persisted user workflow revisions.

    Built-in packaged presets remain authoritative so Doctor keeps their normal
    optional-dependency severity. Non-builtin Configurator workflows live only
    in panel.db and must be added explicitly for compatibility reporting.
    """
    presets = load_presets(config.workflow_dir)
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
        definition = item.get("definition")
        if not isinstance(definition, dict):
            continue
        preset = preset_from_definition(definition, config.workflow_dir / str(item["id"]))
        presets[preset.id] = preset
    return presets
