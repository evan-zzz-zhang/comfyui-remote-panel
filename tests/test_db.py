import json
import sqlite3
import time

import pytest

from comfyui_remote_panel.db import Database


@pytest.mark.asyncio
async def test_database_lifecycle_and_big_seed(tmp_path):
    db = Database(tmp_path / "panel.db")
    await db.initialize()
    record = {
        "id": "id", "preset_id": "preset", "status": "submitting", "mode": "纯文字",
        "prompt": "test", "duration_seconds": 5, "aspect_ratio": "9:16", "megapixels": 0.4,
        "seed": 2**64 - 1,
    }
    await db.create_job(record, [])
    job = await db.get_job("id")
    assert job["seed"] == str(2**64 - 1)
    assert job["status"] == "submitting"
    await db.update_job("id", status="running", started_at=time.time(), progress_value=4, progress_max=8)
    job = await db.get_job("id")
    assert job["progress_percent"] == 50
    await db.delete_job("id")
    assert await db.get_job("id") is None


@pytest.mark.asyncio
async def test_active_jobs_are_not_truncated_at_one_hundred(tmp_path):
    db = Database(tmp_path / "jobs.db")
    await db.initialize()
    for index in range(105):
        await db.create_job({
            "id": f"job-{index}", "preset_id": "preset", "status": "queued", "mode": "纯文字",
            "prompt": "test", "duration_seconds": 5, "aspect_ratio": "9:16",
            "megapixels": 0.4, "seed": index,
        }, [])
    assert len(await db.active_jobs()) == 105


@pytest.mark.asyncio
async def test_succeeded_without_output_excludes_jobs_with_video(tmp_path):
    db = Database(tmp_path / "jobs.db")
    await db.initialize()
    for job_id in ("missing", "complete"):
        await db.create_job({
            "id": job_id, "preset_id": "preset", "status": "succeeded", "mode": "纯文字",
            "prompt": "test", "duration_seconds": 5, "aspect_ratio": "9:16",
            "megapixels": 0.4, "seed": 1,
        }, [])
    await db.add_file("complete", "output", tmp_path / "video.mp4", 10)
    assert [job["id"] for job in await db.succeeded_without_output()] == ["missing"]

    await db.update_job("missing", recovery_attempts=1, recovery_next_at=time.time() + 60)
    assert await db.succeeded_without_output() == []


@pytest.mark.asyncio
async def test_active_update_cannot_overwrite_terminal_status(tmp_path):
    db = Database(tmp_path / "jobs.db")
    await db.initialize()
    await db.create_job({
        "id": "job", "preset_id": "preset", "status": "queued", "mode": "纯文字",
        "prompt": "test", "duration_seconds": 5, "aspect_ratio": "9:16", "megapixels": 0.4, "seed": 1,
    }, [])
    await db.update_job("job", status="cancelled")
    job = await db.update_active_job("job", status="failed", error_summary="late event")
    assert job["status"] == "cancelled"
    assert job["error_summary"] is None


@pytest.mark.asyncio
async def test_compare_and_set_requires_exact_expected_status(tmp_path):
    db = Database(tmp_path / "jobs.db")
    await db.initialize()
    await db.create_job({
        "id": "job", "preset_id": "preset", "status": "submitting", "mode": "纯文字",
        "prompt": "test", "duration_seconds": 5, "aspect_ratio": "9:16",
        "megapixels": 0.4, "seed": "9007199254740993",
    }, [])

    updated, job = await db.update_job_if_status("job", {"queued"}, status="failed")
    assert updated is False
    assert job["status"] == "submitting"

    updated, job = await db.update_job_if_status("job", {"submitting"}, status="cancelled")
    assert updated is True
    assert job["status"] == "cancelled"


@pytest.mark.asyncio
async def test_builtin_refresh_preserves_user_display_name_and_status(tmp_path):
    db = Database(tmp_path / "workflows.db")
    await db.initialize()
    original = {
        "manifest": {
            "id": "builtin-demo", "name": "官方名称", "revision": 1,
        },
        "workflow": {},
    }
    saved = await db.save_workflow(original, status="enabled", builtin=True)
    assert saved["name"] == "官方名称"

    renamed = json.loads(json.dumps(original))
    renamed["manifest"]["name"] = "我的显示名称"
    renamed["manifest"]["revision"] = 1
    await db.save_workflow(renamed, status="draft", builtin=False)
    await db.set_workflow_status("builtin-demo", "disabled")

    refreshed = await db.save_workflow(original, status="enabled", builtin=True)
    assert refreshed["name"] == "我的显示名称"
    assert refreshed["definition"]["manifest"]["name"] == "我的显示名称"
    assert refreshed["status"] == "disabled"
    assert refreshed["builtin"] is True


@pytest.mark.asyncio
async def test_schema_v3_migrates_recovery_and_v04_creation_fields(tmp_path):
    path = tmp_path / "jobs.db"
    with sqlite3.connect(path) as db:
        db.executescript(
            """
            CREATE TABLE jobs (
                id TEXT PRIMARY KEY, preset_id TEXT NOT NULL, status TEXT NOT NULL,
                mode TEXT NOT NULL, prompt TEXT NOT NULL, duration_seconds INTEGER NOT NULL,
                aspect_ratio TEXT NOT NULL, megapixels REAL NOT NULL, seed TEXT NOT NULL,
                scheduler TEXT NOT NULL, sampler TEXT NOT NULL, steps INTEGER NOT NULL,
                queue_position INTEGER, stage TEXT, progress_value INTEGER, progress_max INTEGER,
                error_code TEXT, error_summary TEXT, created_at REAL NOT NULL,
                started_at REAL, finished_at REAL, recovery_attempts INTEGER NOT NULL DEFAULT 0,
                recovery_next_at REAL, recovery_last_error TEXT, updated_at REAL NOT NULL
            );
            CREATE TABLE job_files (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
                role TEXT NOT NULL, path TEXT NOT NULL UNIQUE, size_bytes INTEGER NOT NULL,
                UNIQUE(job_id, role)
            );
            PRAGMA user_version = 3;
            """
        )

    db = Database(path)
    await db.initialize()
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6
        columns = {row[1] for row in connection.execute("PRAGMA table_info(jobs)")}
        counters = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'seed_counters'"
        ).fetchone()
    assert {"cancel_requested_at", "missing_observations", "missing_first_at"} <= columns
    assert {"seed_policy", "seed_value", "actual_seed", "media_metadata_json"} <= columns
    assert counters is not None
