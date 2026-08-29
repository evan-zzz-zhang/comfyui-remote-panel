from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from comfyui_remote_panel.comfy import ComfyClient
from comfyui_remote_panel.config import Config
from comfyui_remote_panel.lifecycle import ComfyLifecycle, LifecycleError


def lifecycle(tmp_path: Path) -> ComfyLifecycle:
    executable = tmp_path / "python.exe"
    executable.touch()
    config = Config(
        host="127.0.0.1",
        port=8190,
        public_origin="https://device.example.ts.net",
        allowed_logins=("owner@example.com",),
        comfyui_base_url="http://127.0.0.1:8188",
        comfyui_input_dir=tmp_path / "input",
        comfyui_output_dir=tmp_path / "output",
        minimum_comfyui_version="0.26.0",
        data_dir=tmp_path / "data",
        workflow_dir=tmp_path / "workflows",
        monitoring_interval=3,
        nvidia_smi_timeout=1,
        comfyui_control_enabled=True,
        comfyui_start_command=("python.exe", "-s", "ComfyUI/main.py"),
        comfyui_working_dir=tmp_path,
    )
    comfy = ComfyClient(config.comfyui_base_url, config.minimum_comfyui_version, "test")
    return ComfyLifecycle(config, comfy)


def test_force_restart_is_not_advertised_while_comfyui_is_online(tmp_path):
    manager = lifecycle(tmp_path)
    snapshot = manager.snapshot(True, managed_process_alive=True)
    assert snapshot["state"] == "online"
    assert snapshot["can_force_restart"] is False


@pytest.mark.asyncio
async def test_force_restart_api_is_refused_while_comfyui_is_online(tmp_path):
    manager = lifecycle(tmp_path)
    manager._is_online = AsyncMock(return_value=True)

    with pytest.raises(LifecycleError, match="普通重启"):
        await manager.trigger("force_restart")
