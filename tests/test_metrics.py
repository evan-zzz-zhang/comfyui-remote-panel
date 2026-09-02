import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import pytest

import comfyui_remote_panel.metrics as metrics_module
from comfyui_remote_panel.comfy import ComfyClient
from comfyui_remote_panel.metrics import MetricsService
from comfyui_remote_panel.preset import load_presets


ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_selector", [
    r"MiniMax-H3\model.safetensors",
    "MiniMax-H3/model.safetensors",
])
async def test_variant_validation_matches_separators_but_returns_exact_runtime_selector(runtime_selector):
    preset = load_presets(ROOT / "workflows")["fl2va_original_raw"]
    preset.manifest["model_profile"]["main_model"]["variants"]["fp16_bf16"] = {
        "available": True,
        "dependencies": [{
            "category": "diffusion_models",
            "name": "MiniMax-H3/model.safetensors",
            "node": "105:6",
            "input": "unet_name",
        }],
    }
    client = ComfyClient("http://127.0.0.1:8188", "0.26.0", "test")

    async def request(_method, path, **_kwargs):
        assert path == "/models/diffusion_models"
        return [runtime_selector]

    client._json = request
    assert await client.validate_preset_variant(preset, "fp16_bf16") == []
    diagnostics, overrides = await client.resolve_preset_variant(preset, "fp16_bf16")
    assert diagnostics == []
    assert overrides == {"105:6": {"unet_name": runtime_selector}}

    graph = preset.build_prompt(
        {
            "prompt": "variant selector",
            "duration_seconds": 5,
            "aspect_ratio": "9:16",
            "megapixels": 0.4,
            "seed": "1",
            "_v047_effective_inference_profile": "fp16_bf16",
        },
        "variant-selector-job",
        {},
        overrides,
    )
    assert graph["105:6"]["inputs"]["unet_name"] == runtime_selector


@pytest.mark.asyncio
async def test_batch_preset_validation_deduplicates_requests_and_publishes_atomically():
    presets = list(load_presets(ROOT / "workflows").values())
    client = ComfyClient("http://127.0.0.1:8188", "0.26.0", "test")
    first_request = asyncio.Event()
    release = asyncio.Event()
    calls: list[str] = []
    models = {
        str(dependency["name"])
        for preset in presets
        for dependency in preset.manifest["dependencies"]
    }

    async def request(_method, path, **_kwargs):
        calls.append(path)
        if path.startswith("/api/jobs/"):
            return {"cancelled": False}
        if path.startswith("/object_info/"):
            if not first_request.is_set():
                first_request.set()
                await release.wait()
            node_type = path.rsplit("/", 1)[-1]
            return {node_type: {"input": {}}}
        if path.startswith("/models/"):
            return sorted(models)
        raise AssertionError(path)

    client._json = request
    presets[0].model_overrides = {"sentinel": {"value": "unchanged"}}
    validation = asyncio.create_task(client.validate_presets(
        presets, {"system": {"comfyui_version": "0.30.0"}}
    ))
    await asyncio.wait_for(first_request.wait(), timeout=2)
    assert presets[0].model_overrides == {"sentinel": {"value": "unchanged"}}
    release.set()
    await validation

    object_calls = [path for path in calls if path.startswith("/object_info/")]
    model_calls = [path for path in calls if path.startswith("/models/")]
    assert len(object_calls) == len(set(object_calls))
    assert len(model_calls) == len(set(model_calls))
    assert len([path for path in calls if path.startswith("/api/jobs/")]) == 1
    assert all(preset.available for preset in presets)
    assert "sentinel" not in presets[0].model_overrides


@pytest.mark.asyncio
async def test_metrics_collect_is_single_flight(tmp_path):
    service = MetricsService(
        Mock(), Mock(), {}, Mock(), tmp_path, 3, 1,
    )
    release = asyncio.Event()

    async def collect_once():
        await release.wait()
        return {"ok": True}

    service._collect_once = AsyncMock(side_effect=collect_once)
    first = asyncio.create_task(service.collect())
    second = asyncio.create_task(service.collect())
    await asyncio.sleep(0)
    release.set()

    assert await asyncio.gather(first, second) == [{"ok": True}, {"ok": True}]
    service._collect_once.assert_awaited_once_with()


class _FakeNvidiaProcess:
    returncode = 0

    async def communicate(self):
        return b"0, Test GPU, 12, 1024, 8192, 55, 123.4\n", b""

    def kill(self):
        pass


@pytest.mark.asyncio
async def test_nvidia_smi_uses_create_no_window_on_windows(tmp_path, monkeypatch):
    calls = []

    async def fake_create_subprocess_exec(*args, **kwargs):
        calls.append((args, kwargs))
        return _FakeNvidiaProcess()

    monkeypatch.setattr(metrics_module.sys, "platform", "win32")
    monkeypatch.setattr(metrics_module.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    service = MetricsService(Mock(), Mock(), {}, Mock(), tmp_path, 3, 1)

    gpus = await service._nvidia_gpus()

    assert len(gpus) == 1
    assert calls[0][0][0] == "nvidia-smi"
    assert calls[0][1]["creationflags"] == getattr(
        metrics_module.subprocess, "CREATE_NO_WINDOW", 0x08000000
    )


@pytest.mark.asyncio
async def test_nvidia_smi_does_not_pass_windows_creationflags_elsewhere(tmp_path, monkeypatch):
    calls = []

    async def fake_create_subprocess_exec(*args, **kwargs):
        calls.append((args, kwargs))
        return _FakeNvidiaProcess()

    monkeypatch.setattr(metrics_module.sys, "platform", "linux")
    monkeypatch.setattr(metrics_module.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    service = MetricsService(Mock(), Mock(), {}, Mock(), tmp_path, 3, 1)

    gpus = await service._nvidia_gpus()

    assert len(gpus) == 1
    assert "creationflags" not in calls[0][1]
