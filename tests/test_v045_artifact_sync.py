from __future__ import annotations

import copy
from pathlib import Path

import pytest

from comfyui_remote_panel.db import Database
from comfyui_remote_panel.events import EventBus
from comfyui_remote_panel.files import FileStore
from comfyui_remote_panel.jobs import JobService
from comfyui_remote_panel.preset import load_presets
from comfyui_remote_panel.v045 import DEFAULT_OLLAMA_MODEL


class DummyComfy:
    pass


async def _service(tmp_path: Path) -> tuple[JobService, Database, FileStore]:
    db = Database(tmp_path / "data" / "jobs.db")
    files = FileStore(tmp_path / "input", tmp_path / "output", tmp_path / "data")
    files.initialize()
    await db.initialize()
    service = JobService(db, files, DummyComfy(), load_presets(), EventBus())
    return service, db, files


async def _job(
    db: Database,
    files: FileStore,
    job_id: str,
    *,
    status: str = "succeeded",
    with_input: bool = True,
    snapshot: dict | None = None,
) -> dict:
    inputs = []
    if with_input:
        path = files.input_root / f"{job_id}-first.png"
        path.write_bytes(b"input")
        inputs.append({"role": "first", "path": path, "size_bytes": path.stat().st_size})
    record = {
        "id": job_id,
        "preset_id": "h3-fl2va-v4step600",
        "workflow_id": "h3-fl2va-v4step600",
        "workflow_revision": 2,
        "workflow_snapshot": snapshot,
        "input_values": {"prompt": "test"},
        "status": status,
        "mode": "首帧",
        "prompt": "test",
        "duration_seconds": 5,
        "aspect_ratio": "9:16",
        "megapixels": 0.4,
        "seed": "1",
        "scheduler": "beta",
        "sampler": "euler",
        "steps": 8,
    }
    await db.create_job(record, inputs)
    return (await db.get_job(job_id)) or {}


async def _output(
    db: Database,
    files: FileStore,
    job_id: str,
    name: str,
    *,
    exists: bool = True,
    ordinal: int = 0,
) -> Path:
    path = files.output_root / name
    if exists:
        path.write_bytes(b"output")
    await db.add_artifact(
        job_id,
        "output",
        "result",
        ordinal,
        path,
        "video",
        "video/mp4",
        name,
        6,
    )
    return path


@pytest.mark.asyncio
async def test_missing_only_output_purges_job_and_managed_inputs(tmp_path):
    service, db, files = await _service(tmp_path)
    await _job(db, files, "job-one")
    await _output(db, files, "job-one", "missing.mp4", exists=False)

    await service.reconcile_output_artifacts_v045()

    assert await db.get_job("job-one") is None
    assert not any(files.input_root.iterdir())


@pytest.mark.asyncio
async def test_partial_missing_outputs_remove_only_missing_reference(tmp_path):
    service, db, files = await _service(tmp_path)
    await _job(db, files, "job-many")
    missing = await _output(db, files, "job-many", "missing.mp4", exists=False, ordinal=0)
    existing = await _output(db, files, "job-many", "existing.mp4", exists=True, ordinal=1)

    await service.reconcile_output_artifacts_v045()

    assert await db.get_job("job-many") is not None
    artifacts = [
        item for item in await db.list_artifacts("job-many")
        if item["direction"] == "output"
    ]
    assert [Path(item["path"]) for item in artifacts] == [existing]
    assert not missing.exists()
    assert existing.exists()


@pytest.mark.asyncio
async def test_all_missing_outputs_purge_multi_output_job(tmp_path):
    service, db, files = await _service(tmp_path)
    await _job(db, files, "job-gone")
    await _output(db, files, "job-gone", "missing-a.mp4", exists=False, ordinal=0)
    await _output(db, files, "job-gone", "missing-b.mp4", exists=False, ordinal=1)

    await service.reconcile_output_artifacts_v045()

    assert await db.get_job("job-gone") is None


@pytest.mark.asyncio
async def test_jobs_without_registered_outputs_and_active_jobs_are_not_removed(tmp_path):
    service, db, files = await _service(tmp_path)
    await _job(db, files, "failed-no-output", status="failed")
    await _job(db, files, "running-output", status="running")
    await _output(db, files, "running-output", "running-missing.mp4", exists=False)

    await service.reconcile_output_artifacts_v045()

    assert (await db.get_job("failed-no-output"))["status"] == "failed"
    assert (await db.get_job("running-output"))["status"] == "running"


def _values(preset, model: str | None = None):
    values = {
        name: spec.get("default")
        for name, spec in preset.manifest["parameters"].items()
    }
    values.update(prompt="test", seed="1", prompt_standardization=True)
    if model is not None:
        values["ollama_model"] = model
    return values


@pytest.mark.parametrize(
    ("preset_id", "node_id"),
    [
        ("h3-fl2va", "124"),
        ("h3-fl2va-lightx2v", "152"),
        ("h3-fl2va-v4step600", "152"),
    ],
)
def test_custom_ollama_model_is_bound_for_all_fl2va_modes(preset_id, node_id):
    preset = load_presets()[preset_id]
    prompt = preset.build_prompt(_values(preset, "qwen3:8b"), "job", {})
    assert prompt[node_id]["inputs"]["ollama_model"] == "qwen3:8b"
    assert preset.manifest["parameters"]["ollama_model"]["default"] == DEFAULT_OLLAMA_MODEL
    standardizer_lock = next(
        item for item in preset.manifest["locked"]
        if item["class_type"] == "H3PromptStandardizer"
    )
    assert "ollama_model" not in standardizer_lock.get("inputs", {})
    assert standardizer_lock["inputs"]["unload_after"] is True


def test_blank_ollama_model_falls_back_to_default():
    preset = load_presets()["h3-fl2va-v4step600"]
    values = _values(preset, "   ")
    normalized = preset.validate_parameters(values)
    assert normalized["ollama_model"] == DEFAULT_OLLAMA_MODEL
    prompt = preset.build_prompt(values, "job", {})
    assert prompt["152"]["inputs"]["ollama_model"] == DEFAULT_OLLAMA_MODEL


@pytest.mark.asyncio
async def test_legacy_retry_recovers_ollama_model_from_workflow_snapshot(tmp_path):
    service, db, files = await _service(tmp_path)
    preset = load_presets()["h3-fl2va-v4step600"]
    legacy_snapshot = preset.snapshot()
    legacy_snapshot = copy.deepcopy(legacy_snapshot)
    legacy_snapshot["manifest"]["parameters"].pop("ollama_model", None)
    lock = next(
        item for item in legacy_snapshot["manifest"]["locked"]
        if item["class_type"] == "H3PromptStandardizer"
    )
    lock.setdefault("inputs", {})["ollama_model"] = DEFAULT_OLLAMA_MODEL
    await _job(db, files, "legacy-job", snapshot=legacy_snapshot)

    draft = await service.retry("legacy-job")

    assert draft["ollama_model"] == DEFAULT_OLLAMA_MODEL
    assert draft["values"]["ollama_model"] == DEFAULT_OLLAMA_MODEL
