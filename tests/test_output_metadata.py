from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from PIL import Image

from comfyui_remote_panel.db import Database


def _record(job_id: str) -> dict:
    return {
        "id": job_id,
        "preset_id": "workflow",
        "status": "succeeded",
        "mode": "test",
        "prompt": "",
        "duration_seconds": 5,
        "aspect_ratio": "1:1",
        "megapixels": 1.0,
        "seed": 0,
        "scheduler": "normal",
        "sampler": "euler",
        "steps": 8,
    }


@pytest.mark.asyncio
async def test_image_output_metadata_is_read_from_actual_file(tmp_path: Path):
    db = Database(tmp_path / "jobs.db")
    await db.initialize()
    await db.create_job(_record("image"), [])

    output = tmp_path / "actual.png"
    Image.new("RGB", (1024, 1536), "white").save(output, format="PNG")
    artifact_id = await db.add_artifact(
        "image",
        "output",
        "primary",
        0,
        output,
        "image",
        "image/png",
        "actual.png",
        output.stat().st_size,
    )

    artifact = await db.get_artifact("image", artifact_id)
    assert artifact is not None
    assert artifact["metadata"] == {"width": 1024, "height": 1536, "format": "PNG"}
    assert artifact["size_bytes"] == output.stat().st_size


@pytest.mark.asyncio
async def test_historical_image_output_metadata_is_backfilled_lazily(tmp_path: Path):
    db = Database(tmp_path / "jobs.db")
    await db.initialize()
    await db.create_job(_record("history"), [])

    output = tmp_path / "history.webp"
    Image.new("RGB", (777, 555), "white").save(output, format="WEBP")
    with sqlite3.connect(db.path) as connection:
        cursor = connection.execute(
            """INSERT INTO job_artifacts(
                job_id, direction, binding_id, ordinal, path, kind,
                mime_type, original_name, size_bytes, metadata_json
            ) VALUES (?, 'output', 'primary', 0, ?, 'image', 'image/webp', ?, ?, NULL)""",
            ("history", str(output), "history.webp", output.stat().st_size),
        )
        artifact_id = int(cursor.lastrowid)
        assert connection.execute(
            "SELECT metadata_json FROM job_artifacts WHERE id = ?", (artifact_id,)
        ).fetchone()[0] is None

    artifacts = await db.list_artifacts("history")
    artifact = next(item for item in artifacts if item["id"] == artifact_id)
    assert artifact["metadata"] == {"width": 777, "height": 555, "format": "WEBP"}

    with sqlite3.connect(db.path) as connection:
        raw = connection.execute(
            "SELECT metadata_json FROM job_artifacts WHERE id = ?", (artifact_id,)
        ).fetchone()[0]
    assert json.loads(raw) == artifact["metadata"]


@pytest.mark.asyncio
async def test_missing_historical_image_does_not_break_artifact_listing(tmp_path: Path):
    db = Database(tmp_path / "jobs.db")
    await db.initialize()
    await db.create_job(_record("missing"), [])
    missing = tmp_path / "missing.png"
    with sqlite3.connect(db.path) as connection:
        connection.execute(
            """INSERT INTO job_artifacts(
                job_id, direction, binding_id, ordinal, path, kind,
                mime_type, original_name, size_bytes, metadata_json
            ) VALUES (?, 'output', 'primary', 0, ?, 'image', 'image/png', ?, 0, NULL)""",
            ("missing", str(missing), "missing.png"),
        )

    artifacts = await db.list_artifacts("missing")
    assert len(artifacts) == 1
    assert artifacts[0]["metadata"] is None


@pytest.mark.asyncio
async def test_metadata_column_is_additive_without_schema_marker_bump(tmp_path: Path):
    db = Database(tmp_path / "jobs.db")
    await db.initialize()

    with sqlite3.connect(db.path) as connection:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        columns = {row[1] for row in connection.execute("PRAGMA table_info(job_artifacts)")}
        assert version == 5
        assert "metadata_json" in columns
        # A v0.4.0-style explicit read ignores the additive column.
        connection.execute(
            """SELECT id, direction, binding_id, ordinal, path, kind, mime_type,
                      original_name, size_bytes FROM job_artifacts"""
        ).fetchall()
