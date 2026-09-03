from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp import web

from comfyui_remote_panel.app import create_app
from comfyui_remote_panel.config import Config


ROOT = Path(__file__).resolve().parents[1]
LOGIN = {"Tailscale-User-Login": "owner@example.com"}
JS = (ROOT / "src" / "comfyui_remote_panel" / "static" / "v045_ollama_ui.js").read_text(encoding="utf-8")
SYNC_JS = (ROOT / "src" / "comfyui_remote_panel" / "static" / "v045_generation_sync.js").read_text(encoding="utf-8")


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
async def test_authenticated_ollama_model_endpoint_returns_installed_models(
    tmp_path, aiohttp_client, aiohttp_server, monkeypatch
):
    ollama = web.Application()

    async def tags(_):
        return web.json_response({
            "models": [
                {"name": "gemma4:e4b"},
                {"name": "qwen3:8b"},
                {"name": "qwen3:14b"},
                {"name": "deepseek-r1:8b"},
                {"name": "llama3.2:3b"},
            ]
        })

    ollama.router.add_get("/api/tags", tags)
    server = await aiohttp_server(ollama)
    monkeypatch.setenv("OLLAMA_HOST", str(server.make_url("/")).rstrip("/"))

    client = await aiohttp_client(create_app(_config(tmp_path)))
    response = await client.get("/api/ollama/models", headers=LOGIN)

    assert response.status == 200
    assert (await response.json())["items"] == [
        "gemma4:e4b",
        "qwen3:8b",
        "qwen3:14b",
        "deepseek-r1:8b",
        "llama3.2:3b",
    ]
    assert (await client.get("/api/ollama/models")).status == 403


@pytest.mark.asyncio
async def test_root_injects_v045_frontend_scripts_once(tmp_path, aiohttp_client):
    client = await aiohttp_client(create_app(_config(tmp_path)))
    response = await client.get("/", headers=LOGIN)
    assert response.status == 200
    html = await response.text()
    ollama_tag = '<script src="/static/v045_ollama_ui.js?v=0.4.8.2" defer></script>'
    sync_tag = '<script src="/static/v045_generation_sync.js?v=0.4.5.0" defer></script>'
    assert html.count(ollama_tag) == 1
    assert html.count(sync_tag) == 1


def test_ollama_ui_uses_real_select_and_disables_it_with_standardizer():
    assert 'fetch("/api/ollama/models"' in JS
    assert 'document.createElement("select")' in JS
    assert 'select.disabled = !standardizationEnabled(field)' in JS
    assert 'data-v045-ollama-model' in JS
    assert '（未检测到）' in JS
    assert '11434' not in JS


def test_shared_ollama_selector_supports_ref2va_with_family_storage_and_backend_state():
    assert '[data-v048-ref2va-ollama-model-field]' in JS
    assert '[data-v048-ref2va-prompt-backend]' in JS
    assert 'field?.dataset.ollamaStorageKey || STORAGE_KEY' in JS
    assert 'document.querySelectorAll(FIELD_SELECTOR)' in JS
    assert 'return document.querySelector(REF2VA_BACKEND_SELECTOR)?.value === "ollama"' in JS


def test_generation_summary_sync_reemits_authoritative_h3_controls_without_polling():
    workflow_ux = (ROOT / "src" / "comfyui_remote_panel" / "static" / "workflow_ux.js").read_text(encoding="utf-8")
    assert 'addEventListener("input", updateSettingsSummary)' in workflow_ux
    assert 'addEventListener("change", updateSettingsSummary)' in workflow_ux

    assert 'function emitH3GenerationState()' in SYNC_JS
    assert 'select[name="aspect_ratio"]' in SYNC_JS
    assert 'new Event("change", { bubbles: true })' in SYNC_JS
    assert 'input[name="duration_seconds"]' in SYNC_JS
    assert '#megapixels-value' in SYNC_JS
    assert 'if (name === "generate") emitH3GenerationState();' in SYNC_JS
    assert '[data-media-action="remove"]' in SYNC_JS
    assert '#clear-retry' in SYNC_JS
    assert '#preset-select' in SYNC_JS
    assert 'MutationObserver' not in SYNC_JS
    assert 'setInterval' not in SYNC_JS
    assert 'setTimeout' not in SYNC_JS
