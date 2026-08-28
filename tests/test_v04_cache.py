from types import SimpleNamespace

import pytest

from comfyui_remote_panel.app import create_app
from comfyui_remote_panel.config import Config


def _config(tmp_path) -> Config:
    return Config(
        host="127.0.0.1",
        port=8190,
        public_origin="http://127.0.0.1:8190",
        allowed_logins=(),
        comfyui_base_url="http://127.0.0.1:8188",
        comfyui_input_dir=tmp_path / "input",
        comfyui_output_dir=tmp_path / "output",
        minimum_comfyui_version="0.0.0",
        data_dir=tmp_path / "data",
        workflow_dir=tmp_path / "workflows",
        monitoring_interval=3.0,
        nvidia_smi_timeout=2.0,
        auth_provider="local",
    )


def test_v04_create_app_installs_static_no_store_guard(tmp_path) -> None:
    app = create_app(_config(tmp_path))
    callbacks = [item for item in app.on_response_prepare if getattr(item, "__name__", "") == "no_store_static"]
    assert len(callbacks) == 1


@pytest.mark.asyncio
async def test_v04_static_no_store_headers_are_explicit(tmp_path) -> None:
    app = create_app(_config(tmp_path))
    callback = next(item for item in app.on_response_prepare if getattr(item, "__name__", "") == "no_store_static")
    response = SimpleNamespace(headers={})
    await callback(SimpleNamespace(path="/static/app.js"), response)
    assert response.headers["Cache-Control"] == "no-store, max-age=0"
    assert response.headers["Pragma"] == "no-cache"
    assert response.headers["Expires"] == "0"


@pytest.mark.asyncio
async def test_v04_cache_guard_does_not_rewrite_api_headers(tmp_path) -> None:
    app = create_app(_config(tmp_path))
    callback = next(item for item in app.on_response_prepare if getattr(item, "__name__", "") == "no_store_static")
    response = SimpleNamespace(headers={"Cache-Control": "no-store"})
    await callback(SimpleNamespace(path="/api/presets"), response)
    assert response.headers == {"Cache-Control": "no-store"}
