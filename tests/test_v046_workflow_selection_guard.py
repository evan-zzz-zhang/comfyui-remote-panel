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
async def test_root_loads_selection_guard_after_v046_routing(tmp_path, aiohttp_client):
    client = await aiohttp_client(create_app(_config(tmp_path)))
    response = await client.get("/", headers=LOGIN)
    assert response.status == 200
    html = await response.text()
    guard = '<script src="/static/v046_workflow_selection_guard.js?v=0.4.6.2" defer></script>'
    assert html.count(guard) == 1
    assert html.index("v046_fl2va_ui.js") < html.index("v046_workflow_selection_guard.js")
    assert html.index("v046_job_runtime_ui.js") < html.index("v046_workflow_selection_guard.js")


def test_selection_guard_repairs_silent_native_select_drift_before_submit():
    assert 'const FL2VA_ENTRY_ID = "h3-fl2va-group"' in GUARD_JS
    assert 'function renderedSpecializedFamily()' in GUARD_JS
    assert 'renderedSpecializedFamily() !== "fl2va"' in GUARD_JS
    assert 'if (select.value !== FL2VA_ENTRY_ID) select.value = FL2VA_ENTRY_ID' in GUARD_JS
    assert 'loadPresets = async function(...args)' in GUARD_JS
    assert 'loadWorkflows = async function(...args)' in GUARD_JS
    assert 'queueMicrotask(restoreRenderedInvariants)' in GUARD_JS
    assert 'path === "/api/jobs" && renderedSpecializedFamily() === "fl2va"' in GUARD_JS
    assert 'formData.set("preset_id", FL2VA_ENTRY_ID)' in GUARD_JS


def test_selection_guard_repairs_status_toggle_rebuilds_after_v042_timer():
    assert 'apiAction = async function(path, options = {})' in GUARD_JS
    assert '/^\\/api\\/workflows\\/[^/]+\\/status$/.test(path)' in GUARD_JS
    assert 'window.setTimeout(restoreRenderedInvariants, 0)' in GUARD_JS


def test_selection_guard_defaults_fl2va_aspect_to_9_16_without_explicit_choice():
    assert 'const DEFAULT_FL2VA_ASPECT = "9:16"' in GUARD_JS
    assert 'let explicitFl2vaAspect = null' in GUARD_JS
    assert 'function aspectFromOverrides(overrides)' in GUARD_JS
    assert 'function desiredFl2vaAspect(select)' in GUARD_JS
    assert 'return DEFAULT_FL2VA_ASPECT' in GUARD_JS
    assert 'explicitFl2vaAspect = aspect' in GUARD_JS
    assert 'explicitFl2vaAspectSource = "user"' in GUARD_JS
    assert 'formData.set("aspect_ratio", desired)' in GUARD_JS
    assert 'event.target.closest?.("#clear-retry")' in GUARD_JS


def test_selection_guard_does_not_rewrite_ref2va_rendering():
    assert 'if (fl2vaVisible && !ref2vaVisible) return "fl2va"' in GUARD_JS
    assert 'if (ref2vaVisible && !fl2vaVisible) return "ref2va"' in GUARD_JS
    assert 'if (renderedSpecializedFamily() !== "fl2va") return' in GUARD_JS
