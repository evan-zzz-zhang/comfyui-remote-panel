from pathlib import Path

import pytest

from comfyui_remote_panel.app import create_app
from comfyui_remote_panel.config import Config


ROOT = Path(__file__).resolve().parents[1]
LOGIN = {"Tailscale-User-Login": "owner@example.com"}


@pytest.mark.asyncio
async def test_app_js_response_includes_recovery_lite_extension(tmp_path, aiohttp_client):
    config = Config(
        host="127.0.0.1",
        port=8190,
        public_origin="https://device.example.ts.net",
        allowed_logins=("owner@example.com",),
        comfyui_base_url="http://127.0.0.1:1",
        comfyui_input_dir=tmp_path / "input",
        comfyui_output_dir=tmp_path / "output",
        minimum_comfyui_version="0.26.0",
        data_dir=tmp_path / "data",
        workflow_dir=ROOT / "workflows",
        monitoring_interval=60,
        nvidia_smi_timeout=.1,
    )
    client = await aiohttp_client(create_app(config))

    response = await client.get("/static/app.js", headers=LOGIN)
    assert response.status == 200
    source = await response.text()
    assert "function renderMetrics" in source
    assert "/api/comfyui/control/force_restart" in source
    assert "Panel 在线" in source
    assert response.headers["Cache-Control"] == "no-store, max-age=0"
