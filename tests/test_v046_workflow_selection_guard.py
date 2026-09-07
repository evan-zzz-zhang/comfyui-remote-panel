from __future__ import annotations

from pathlib import Path

import pytest

from comfyui_remote_panel.app import create_app
from comfyui_remote_panel.config import Config


ROOT = Path(__file__).resolve().parents[1]
LOGIN = {"Tailscale-User-Login": "owner@example.com"}
GUARD_JS = (
    ROOT
    / "src"
    / "comfyui_remote_panel"
    / "static"
    / "v046_workflow_selection_guard.js"
).read_text(encoding="utf-8")


def _config(tmp_path: Path) -> Config:
    return Config(
        host="127.0.0.1",
        port=8190,
        public_origin="https://device.example.ts.net",
        allowed_logins=("owner@example.com",),
        comfyui_base_url="http://127.0.0.1:1",
        comfyui_input_dir=tmp_path / "comfy-input",
        comfyui_output_dir=tmp_path / "comfy-output",
        minimum_comfyui_version="0.26.0",
        data_dir=tmp_path / "data",
        workflow_dir=ROOT / "workflows",
        monitoring_interval=60,
        nvidia_smi_timeout=.1,
    )


@pytest.mark.asyncio
async def test_root_loads_h3_runtime_after_base_frontend(tmp_path, aiohttp_client):
    client = await aiohttp_client(create_app(_config(tmp_path)))
    response = await client.get("/", headers=LOGIN)
    assert response.status == 200
    html = await response.text()
    assert html.count('/static/h3_creation_runtime.js?v=0.4.8.6') == 1
    assert html.index("h3_advanced_controller.js") < html.index("h3_creation_runtime.js")
    assert html.index("h3_creation_runtime.js") < html.index("h3_fl2va_adapter.js")
    assert html.index("h3_fl2va_adapter.js") < html.index("h3_ref2va_adapter.js")


def test_selection_guard_is_now_a_non_duplicating_compatibility_asset():
    assert "Compatibility placeholder" in GUARD_JS
    assert "applyPreset" not in GUARD_JS
    assert "uploadForm" not in GUARD_JS
    assert "MutationObserver" not in GUARD_JS


def test_h3_runtime_owns_selection_and_upload_wrappers():
    runtime = (ROOT / "src" / "comfyui_remote_panel" / "static" / "h3_creation_runtime.js").read_text(encoding="utf-8")
    assert "applyPreset = applyPresetWithH3" in runtime
    assert "uploadForm = uploadFormWithH3" in runtime


def test_fl2va_aspect_compatibility_is_adapter_owned():
    runtime = (ROOT / "src" / "comfyui_remote_panel" / "static" / "h3_creation_runtime.js").read_text(encoding="utf-8")
    assert 'option.value === "9:16"' in runtime
    assert 'reference.value = "reference"' in runtime


def test_selection_guard_does_not_rewrite_ref2va_rendering():
    assert "ref2va" not in GUARD_JS
