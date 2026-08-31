from __future__ import annotations

import time

import pytest

from comfyui_remote_panel.db import Database
from comfyui_remote_panel.events import EventBus
from comfyui_remote_panel.jobs import JobService


class _Files:
    @staticmethod
    def role_kind(_role: str):
        return None


class _Preset:
    manifest = {"name": "MiniMax H3 FL2VA", "family": "fl2va"}
    stages = {
        "prepare": "加载模型",
        "standardize": "标准化提示词",
        "sample": "采样",
        "decode": "解码画面",
    }

    @staticmethod
    def phase_for_stage(stage):
        return {
            "加载模型": "build",
            "标准化提示词": "build",
            "采样": "sampling",
            "解码画面": "decode",
            "合成视频": "compose",
            "保存视频": "save",
        }.get(stage)


async def _create_job(db: Database, job_id: str, *, status: str = "queued") -> None:
    await db.create_job(
        {
            "id": job_id,
            "preset_id": "h3-fl2va",
            "status": status,
            "mode": "text",
            "prompt": "test",
            "duration_seconds": 5,
            "aspect_ratio": "9:16",
            "megapixels": 0.4,
            "seed": "1",
            "scheduler": "simple",
            "sampler": "euler",
            "steps": 8,
            "input_values": {"prompt_standardization": True},
        },
        [],
    )


@pytest.mark.asyncio
async def test_queue_wait_does_not_count_as_execution_elapsed(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    await db.initialize()
    await _create_job(db, "queued")
    now = time.time()
    with db._connect() as connection:
        connection.execute(
            "UPDATE jobs SET created_at = ?, updated_at = ? WHERE id = ?",
            (now - 20, now - 20, "queued"),
        )

    queued = await db.get_job("queued")
    assert queued is not None
    assert queued["queue_elapsed_seconds"] >= 19
    assert queued["execution_elapsed_seconds"] == 0
    assert queued["elapsed_seconds"] == 0

    started_at = time.time() - 5
    await db.update_job("queued", status="running", started_at=started_at)
    running = await db.get_job("queued")
    assert running is not None
    assert 4 <= running["execution_elapsed_seconds"] <= 6
    assert running["elapsed_seconds"] == running["execution_elapsed_seconds"]


@pytest.mark.asyncio
async def test_offline_interruption_freezes_active_job_at_first_outage(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    await db.initialize()
    await _create_job(db, "running", status="running")
    started_at = time.time() - 12
    await db.update_job("running", started_at=started_at, stage="采样")

    service = JobService(db, _Files(), object(), {}, EventBus())
    offline_since = time.time() - 3
    await service._interrupt_active_for_offline_v046(offline_since)

    job = await db.get_job("running")
    assert job is not None
    assert job["status"] == "interrupted"
    assert job["stage"] == "ComfyUI 已离线"
    assert job["error_code"] == "comfyui_offline"
    assert job["finished_at"] == pytest.approx(offline_since)
    frozen = job["execution_elapsed_seconds"]
    time.sleep(0.02)
    again = await db.get_job("running")
    assert again is not None
    assert again["execution_elapsed_seconds"] == frozen


@pytest.mark.asyncio
async def test_queued_job_interrupted_offline_never_acquires_execution_time(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    await db.initialize()
    await _create_job(db, "queued-offline")
    service = JobService(db, _Files(), object(), {}, EventBus())

    await service._interrupt_active_for_offline_v046(time.time())
    job = await db.get_job("queued-offline")
    assert job is not None
    assert job["status"] == "interrupted"
    assert job["stage"] == "排队已中断"
    assert job["execution_elapsed_seconds"] == 0
    assert job["elapsed_seconds"] == 0


@pytest.mark.asyncio
async def test_phase_timings_are_persisted_and_private(tmp_path):
    db = Database(tmp_path / "jobs.sqlite3")
    await db.initialize()
    await _create_job(db, "phase")
    preset = _Preset()
    service = JobService(db, _Files(), object(), {"h3-fl2va": preset}, EventBus())

    await service.handle_ws_event(
        {"type": "execution_start", "data": {"prompt_id": "phase", "node": "standardize"}}
    )
    after_standardize = await db.get_job("phase")
    timing = after_standardize["input_values"].get("_v046_phase_timing")
    assert isinstance(timing, dict)
    assert timing.get("standardization_started_at") is not None

    await service.handle_ws_event(
        {"type": "execution_start", "data": {"prompt_id": "phase", "node": "sample"}}
    )
    await service.handle_ws_event(
        {"type": "execution_start", "data": {"prompt_id": "phase", "node": "decode"}}
    )
    stored = await db.get_job("phase")
    timing = stored["input_values"].get("_v046_phase_timing")
    assert timing.get("standardization_finished_at") is not None
    assert timing.get("generation_started_at") is not None
    assert timing.get("generation_finished_at") is not None

    public = service.public_job(stored)
    assert public["standardization_elapsed_seconds"] is not None
    assert public["generation_elapsed_seconds"] is not None
    assert "_v046_phase_timing" not in public["input_values"]


def test_fl2va_standardization_is_a_real_progress_stage():
    service = JobService(object(), _Files(), object(), {"h3-fl2va": _Preset()}, EventBus())
    base = {
        "id": "job",
        "preset_id": "h3-fl2va",
        "seed": "1",
        "status": "running",
        "files": [],
        "input_values": {"prompt_standardization": True},
        "progress_value": 50,
        "progress_max": 100,
    }

    standardized = service.public_job({**base, "stage": "标准化提示词"})
    assert standardized["progress_phase"] == "standardize"
    assert standardized["progress_percent"] == 8

    sampling = service.public_job({**base, "stage": "采样"})
    assert sampling["progress_phase"] == "sampling"
    assert sampling["progress_percent"] == 50

    off = service.public_job(
        {
            **base,
            "stage": "采样",
            "input_values": {"prompt_standardization": False},
        }
    )
    assert off["progress_percent"] == 44
