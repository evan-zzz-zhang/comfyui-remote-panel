import sqlite3

import pytest

from comfyui_remote_panel.db import Database


@pytest.mark.asyncio
async def test_existing_v6_marker_is_normalized_without_losing_history(tmp_path):
    path = tmp_path / "panel.db"
    db = Database(path)
    await db.initialize()
    await db.create_job({
        "id": "keep-me",
        "preset_id": "preset",
        "status": "succeeded",
        "mode": "test",
        "prompt": "history must survive rollback compatibility",
        "duration_seconds": 5,
        "aspect_ratio": "1:1",
        "megapixels": 0.4,
        "seed": 0,
    }, [])

    # Simulate a database created by the first v0.4 beta, which used marker 6.
    with sqlite3.connect(path) as connection:
        connection.execute("PRAGMA user_version = 6")

    reopened = Database(path)
    await reopened.initialize()

    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 5
        columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
        assert {"seed_policy", "seed_value", "actual_seed", "media_metadata_json"} <= columns
        assert connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'seed_counters'"
        ).fetchone() is not None

    job = await reopened.get_job("keep-me")
    assert job is not None
    assert job["prompt"] == "history must survive rollback compatibility"
