from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from comfyui_remote_panel.db import Database
from comfyui_remote_panel.files import FileStore, FileValidationError
from comfyui_remote_panel.jobs import JobService
import comfyui_remote_panel.v041 as v041


def _record(job_id: str, **overrides) -> dict:
    record = {
        "id": job_id,
        "preset_id": "workflow",
        "status": "succeeded",
        "mode": "test",
        "prompt": "test",
        "duration_seconds": 5,
        "aspect_ratio": "1:1",
        "megapixels": 1.0,
        "seed": 0,
        "scheduler": "normal",
        "sampler": "euler",
        "steps": 8,
        "input_values": {},
    }
    record.update(overrides)
    return record


@pytest.mark.asyncio
async def test_retry_contract_exposes_retained_artifact_identity_without_paths(tmp_path: Path):
    db = Database(tmp_path / "jobs.db")
    await db.initialize()
    files = FileStore(tmp_path / "input", tmp_path / "output", tmp_path / "data")
    files.initialize()
    source = files.input_root / "rp_aaaaaaaaaaaa_image_0.png"
    Image.new("RGB", (1155, 866), "white").save(source)
    metadata = {
        "image_0": {
            "source_width": 4032,
            "source_height": 3024,
            "effective_width": 1155,
            "effective_height": 866,
            "resolution_policy": "auto",
            "target_megapixels": 1.0,
            "resized": True,
            "orientation_applied": False,
        }
    }
    await db.create_job(
        _record("source", media_metadata=metadata),
        [{"role": "image_0", "path": source, "size_bytes": source.stat().st_size}],
    )

    service = object.__new__(JobService)
    service.db = db
    service.files = files
    draft = await service.retry("source")

    assert draft["retry_source_id"] == "source"
    assert draft["input_roles"] == ["image_0"]
    assert draft["retry_keep_roles"] == ["image_0"]
    assert len(draft["retained_media"]) == 1
    retained = draft["retained_media"][0]
    assert retained["artifact_id"] > 0
    assert retained["role"] == "image_0"
    assert retained["kind"] == "image"
    assert retained["size_bytes"] == source.stat().st_size
    assert "path" not in retained


@pytest.mark.asyncio
async def test_retry_copy_reuses_prepared_metadata_for_same_resolution_without_processing(monkeypatch, tmp_path: Path):
    files = FileStore(tmp_path / "input", tmp_path / "output", tmp_path / "data")
    files.initialize()
    source = files.input_root / "rp_aaaaaaaaaaaa_image_0.png"
    Image.new("RGB", (1224, 816), "white").save(source)
    source_metadata = {
        "source_width": 6000,
        "source_height": 4000,
        "effective_width": 1224,
        "effective_height": 816,
        "resolution_policy": "auto",
        "target_megapixels": 1.0,
        "resized": True,
        "orientation_applied": False,
    }
    context = {
        "retained_sources": {v041._path_key(source)},
        "metadata_by_source": {v041._path_key(source): source_metadata},
        "prepared_by_destination": {},
    }
    token = v041._RETRY_MEDIA_CONTEXT.set(context)
    calls = []

    def process(path, policy, target):
        calls.append((path, policy, target))
        return {"processed": True}

    monkeypatch.setattr(v041, "_ORIGINAL_PROCESS_RESOLUTION", process)
    try:
        copied = await files.copy_input_async(source, "bbbbbbbbbbbb", "image_0")
        result = v041._process_resolution_v041(Path(copied["path"]), "auto", 1.0)
    finally:
        v041._RETRY_MEDIA_CONTEXT.reset(token)

    assert calls == []
    assert result == source_metadata
    assert Path(copied["path"]) != source
    Path(copied["path"]).unlink()
    assert source.exists()


@pytest.mark.asyncio
async def test_changed_retry_resolution_processes_only_private_copy(monkeypatch, tmp_path: Path):
    files = FileStore(tmp_path / "input", tmp_path / "output", tmp_path / "data")
    files.initialize()
    source = files.input_root / "rp_aaaaaaaaaaaa_image_0.png"
    Image.new("RGB", (1224, 816), "white").save(source)
    source_bytes = source.read_bytes()
    source_metadata = {
        "source_width": 6000,
        "source_height": 4000,
        "effective_width": 1224,
        "effective_height": 816,
        "resolution_policy": "auto",
        "target_megapixels": 1.0,
    }
    context = {
        "retained_sources": {v041._path_key(source)},
        "metadata_by_source": {v041._path_key(source): source_metadata},
        "prepared_by_destination": {},
    }
    token = v041._RETRY_MEDIA_CONTEXT.set(context)
    calls = []

    def process(path, policy, target):
        calls.append((Path(path), policy, target))
        return {"resolution_policy": policy, "target_megapixels": target}

    monkeypatch.setattr(v041, "_ORIGINAL_PROCESS_RESOLUTION", process)
    try:
        copied = await files.copy_input_async(source, "bbbbbbbbbbbb", "image_0")
        result = v041._process_resolution_v041(Path(copied["path"]), "auto", 0.5)
    finally:
        v041._RETRY_MEDIA_CONTEXT.reset(token)

    assert calls == [(Path(copied["path"]), "auto", 0.5)]
    assert result == {"resolution_policy": "auto", "target_megapixels": 0.5}
    assert source.read_bytes() == source_bytes


@pytest.mark.asyncio
async def test_missing_retained_source_fails_clearly(tmp_path: Path):
    files = FileStore(tmp_path / "input", tmp_path / "output", tmp_path / "data")
    files.initialize()
    missing = files.input_root / "rp_aaaaaaaaaaaa_image_0.png"
    context = {
        "retained_sources": {v041._path_key(missing)},
        "metadata_by_source": {},
        "prepared_by_destination": {},
    }
    token = v041._RETRY_MEDIA_CONTEXT.set(context)
    try:
        with pytest.raises(FileValidationError, match="原任务参考素材已不存在"):
            await files.copy_input_async(missing, "bbbbbbbbbbbb", "image_0")
    finally:
        v041._RETRY_MEDIA_CONTEXT.reset(token)
