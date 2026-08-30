from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp import web

from comfyui_remote_panel.app import create_app
from comfyui_remote_panel.config import Config


ROOT = Path(__file__).resolve().parents[1]
LOGIN = {"Tailscale-User-Login": "owner@example.com"}
JS = (ROOT / "src" / "comfyui_remote_panel" / "static" / "v045_ollama_ui.js").read_text(encoding="utf-8")


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
async def test_root_injects_v045_ollama_selector_script(tmp_path, aiohttp_client):
    client = await aiohttp_client(create_app(_config(tmp_path)))
    response = await client.get("/", headers=LOGIN)
    assert response.status == 200
    html = await response.text()
    tag = '<script src="/static/v045_ollama_ui.js?v=0.4.5.1" defer></script>'
    assert html.count(tag) == 1


def test_ollama_ui_uses_real_select_and_disables_it_with_standardizer():
    assert 'fetch("/api/ollama/models"' in JS
    assert 'document.createElement("select")' in JS
    assert 'select.disabled = !standardizationEnabled()' in JS
    assert 'data-v045-ollama-model' in JS
    assert '（未检测到）' in JS
    assert '11434' not in JS
