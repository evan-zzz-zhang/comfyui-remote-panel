from __future__ import annotations

from pathlib import Path

import pytest

from comfyui_remote_panel.app import create_app
from comfyui_remote_panel.config import Config


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "comfyui_remote_panel" / "static"
JS = (STATIC / "v042_ui.js").read_text(encoding="utf-8")
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")


def _config(tmp_path: Path) -> Config:
    return Config(
        host="127.0.0.1",
        port=8190,
        public_origin="https://device.example.ts.net",
        allowed_logins=("owner@example.com",),
        comfyui_base_url="http://127.0.0.1:1",
        comfyui_input_dir=tmp_path / "comfy-input",
        comfyui_output_dir=tmp_path / "comfy-output",
        minimum_comfyui_version="0.0.0",
        data_dir=tmp_path / "data",
        workflow_dir=ROOT / "workflows",
        monitoring_interval=60,
        nvidia_smi_timeout=.1,
    )


def test_fl2va_mode_ui_stays_inside_existing_advanced_settings():
    assert '#advanced-settings' in JS
    assert '.advanced-grid' in JS
    assert '生成模式' in JS
    assert '使用 H3 提示词标准化' in JS
    assert 'prompt-field' not in JS
    assert 'settings-close' not in JS
    assert 'v042_ui.js' not in INDEX


def test_generation_mode_defaults_to_v4_and_uses_local_storage():
    assert 'const ENTRY_ID = "h3-fl2va-group"' in JS
    assert 'const DEFAULT_MODE = "v4_600step"' in JS
    assert 'comfy-remote.fl2va.generation-mode' in JS
    assert 'window.localStorage.getItem(MODE_STORAGE_KEY)' in JS
    assert 'window.localStorage.setItem(MODE_STORAGE_KEY, mode)' in JS
    assert 'loadPresets = async function()' in JS
    assert 'applyPreset(ENTRY_ID)' in JS


def test_lightx2v_has_deterministic_mode_defaults():
    assert 'lightx2v: { scheduler: "simple", sampler: "euler", steps: 8 }' in JS
    assert 'v4_600step: { scheduler: "beta", sampler: "euler", steps: 8 }' in JS
    assert 'original: { scheduler: "simple", sampler: "res_multistep", steps: 20 }' in JS
    assert 'applyModeDefaults(next)' in JS


def test_prompt_requirement_tracks_standardizer_and_frame_presence():
    assert 'const hasFrame = ["#first-frame", "#last-frame"].some' in JS
    assert 'prompt.required = Boolean(toggle?.checked) || !hasFrame' in JS


def test_standardizer_uses_compact_toggle_instead_of_raw_checkbox_ui():
    assert 'class="v042-switch"' in JS
    assert '.v042-switch input:checked + i' in JS


def test_fl2va_values_json_is_merged_and_deduplicated_before_upload():
    assert 'formData.getAll("values_json")' in JS
    assert 'formData.delete("values_json")' in JS
    assert 'formData.set("values_json", JSON.stringify(values))' in JS
    assert 'values.generation_mode = mode' in JS
    assert 'values.prompt_standardization = standardize' in JS
    assert 'values.media_resolution = mediaResolution' in JS
    assert 'dedupeScalarFields(formData)' in JS


def test_physical_fl2va_presets_are_hidden_from_creation_picker_but_keep_mode_status():
    assert 'const ENTRY_ID = "h3-fl2va-group"' in JS
    assert 'function physicalPresetIds()' in JS
    assert 'function hidePhysicalWorkflowChoices()' in JS
    assert 'button.remove()' in JS
    assert 'function modeEnabled(mode)' in JS
    assert 'item.status === "enabled"' in JS
    assert 'new MutationObserver(() => queueMicrotask(hidePhysicalWorkflowChoices))' in JS


@pytest.mark.asyncio
async def test_root_loads_v042_script_after_existing_frontend_layers(tmp_path, aiohttp_client):
    client = await aiohttp_client(create_app(_config(tmp_path)))
    response = await client.get("/", headers={"Tailscale-User-Login": "owner@example.com"})
    assert response.status == 200
    html = await response.text()
    assert html.count('<script src="/static/v042_ui.js?v=0.4.2.1" defer></script>') == 1
    assert '<script src="/static/v041_ui.js?v=0.4.1" defer></script>' in html
    assert '<label class="creation-section prompt-field">' in html
