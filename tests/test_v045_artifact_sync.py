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
    input_values: dict | None = None,
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
        "input_values": input_values or {"prompt": "test"},
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
@pytest.mark.parametrize("failure", [PermissionError("denied"), OSError("temporary I/O failure")])
async def test_output_probe_errors_keep_job_and_all_files(tmp_path, monkeypatch, failure):
    service, db, files = await _service(tmp_path)
    job = await _job(db, files, "job-uncertain")
    output = await _output(db, files, "job-uncertain", "output.mp4")

    def fail_probe(path):
        raise failure

    monkeypatch.setattr(files, "validate_artifact_file", fail_probe)
    await service.reconcile_output_artifacts_v045()

    assert await db.get_job(job["id"]) is not None
    assert output.exists()
    assert (files.input_root / "job-uncertain-first.png").exists()
    outputs = [item for item in await db.list_artifacts(job["id"]) if item["direction"] == "output"]
    assert len(outputs) == 1


@pytest.mark.asyncio
async def test_missing_and_uncertain_outputs_keep_entire_job(tmp_path, monkeypatch):
    service, db, files = await _service(tmp_path)
    job = await _job(db, files, "job-mixed")
    missing = await _output(db, files, "job-mixed", "missing.mp4", exists=False, ordinal=0)
    uncertain = await _output(db, files, "job-mixed", "uncertain.mp4", exists=True, ordinal=1)

    def probe(path):
        if path == missing:
            raise FileNotFoundError(path)
        raise OSError("temporary I/O failure")

    monkeypatch.setattr(files, "validate_artifact_file", probe)
    await service.reconcile_output_artifacts_v045()

    assert await db.get_job(job["id"]) is not None
    assert uncertain.exists()
    outputs = [item for item in await db.list_artifacts(job["id"]) if item["direction"] == "output"]
    assert [Path(item["path"]) for item in outputs] == [missing, uncertain]


@pytest.mark.asyncio
async def test_output_restored_before_auto_purge_aborts_cleanup(tmp_path, monkeypatch):
    service, db, files = await _service(tmp_path)
    job = await _job(db, files, "job-restored")
    output = await _output(db, files, "job-restored", "restored.mp4", exists=False)
    calls = 0

    def probe(path):
        nonlocal calls
        calls += 1
        if calls == 1:
            output.write_bytes(b"restored")
            raise FileNotFoundError(path)
        return path

    monkeypatch.setattr(files, "validate_artifact_file", probe)
    await service.reconcile_output_artifacts_v045()

    assert calls == 2
    assert await db.get_job(job["id"]) is not None
    assert output.exists()
    assert (files.input_root / "job-restored-first.png").exists()


@pytest.mark.asyncio
async def test_jobs_without_registered_outputs_and_active_jobs_are_not_removed(tmp_path):
    service, db, files = await _service(tmp_path)
    await _job(db, files, "failed-no-output", status="failed")
    await _job(db, files, "running-output", status="running")
    await _output(db, files, "running-output", "running-missing.mp4", exists=False)

    await service.reconcile_output_artifacts_v045()

    assert (await db.get_job("failed-no-output"))["status"] == "failed"
    assert (await db.get_job("running-output"))["status"] == "running"


@pytest.mark.asyncio
async def test_manual_purge_removes_secondary_output_artifacts(tmp_path):
    service, db, files = await _service(tmp_path)
    await _job(db, files, "job-purge")
    first = await _output(db, files, "job-purge", "first.mp4", ordinal=0)
    second = await _output(db, files, "job-purge", "second.mp4", ordinal=1)

    await service.purge("job-purge")

    assert await db.get_job("job-purge") is None
    assert not first.exists()
    assert not second.exists()
    assert not any(files.input_root.iterdir())


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
async def test_retry_keeps_custom_ollama_model_from_job_values(tmp_path):
    service, db, files = await _service(tmp_path)
    await _job(
        db,
        files,
        "custom-model-job",
        input_values={"prompt": "test", "ollama_model": "qwen3:8b"},
    )

    draft = await service.retry("custom-model-job")

    assert draft["ollama_model"] == "qwen3:8b"
    assert draft["values"]["ollama_model"] == "qwen3:8b"


@pytest.mark.asyncio
async def test_legacy_retry_recovers_ollama_model_from_workflow_snapshot(tmp_path):
    service, db, files = await _service(tmp_path)
    preset = load_presets()["h3-fl2va-v4step600"]
    legacy_snapshot = copy.deepcopy(preset.snapshot())
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
