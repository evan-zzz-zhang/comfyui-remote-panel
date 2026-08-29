import asyncio
import re
from pathlib import Path

import pytest

from comfyui_remote_panel import __version__
from comfyui_remote_panel.app import create_app
from comfyui_remote_panel.config import Config
from comfyui_remote_panel.recovery_lite import _build_info, _launch_stdin


ROOT = Path(__file__).resolve().parents[1]
LOGIN = {"Tailscale-User-Login": "owner@example.com"}


def test_visible_windows_console_keeps_default_stdio_handles():
    assert _launch_stdin("nt", True) is None
    assert _launch_stdin("nt", False) == asyncio.subprocess.DEVNULL
    assert _launch_stdin("posix", True) == asyncio.subprocess.DEVNULL


def test_build_info_never_exposes_local_repository_path():
    info = _build_info("0.4.0")
    assert info["version"] == "0.4.0"
    assert set(info) == {"version", "branch", "commit", "tracked_dirty", "source"}
    assert info["source"] in {"git", "package"}
    if info["commit"] is not None:
        assert re.fullmatch(r"[0-9a-f]{40}", info["commit"])
    serialized = repr(info).lower()
    assert "repository_root" not in serialized
    assert "\\users\\" not in serialized
    assert "/home/" not in serialized


@pytest.mark.asyncio
async def test_about_endpoint_exposes_acceptance_identity(tmp_path, aiohttp_client):
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

    unauthorized = await client.get("/api/about")
    assert unauthorized.status == 403

    response = await client.get("/api/about", headers=LOGIN)
    assert response.status == 200
    info = await response.json()
    assert info["version"] == __version__
    assert set(info) == {"version", "branch", "commit", "tracked_dirty", "source"}

    source = (ROOT / "src" / "comfyui_remote_panel" / "static" / "recovery_lite.js").read_text(encoding="utf-8")
    assert 'fetch("/api/about")' in source
    assert "验收版本" in source
    assert "本地有已跟踪修改" in source
