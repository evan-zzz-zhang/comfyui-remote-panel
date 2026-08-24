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
