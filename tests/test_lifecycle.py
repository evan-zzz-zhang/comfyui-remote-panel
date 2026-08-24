from pathlib import Path
from unittest.mock import Mock

from comfyui_remote_panel.comfy import ComfyClient
from comfyui_remote_panel.config import Config
from comfyui_remote_panel.lifecycle import ComfyLifecycle


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


def test_process_match_requires_executable_and_every_configured_argument(tmp_path):
    manager = lifecycle(tmp_path)
    process = Mock()
    process.exe.return_value = str(tmp_path / "python.exe")
    process.cmdline.return_value = [str(tmp_path / "python.exe"), "-s", r"ComfyUI\main.py", "--extra"]
    assert manager._matches(process) is True

    process.cmdline.return_value = [str(tmp_path / "python.exe"), "ComfyUI/main.py"]
    assert manager._matches(process) is False

    process.exe.return_value = str(tmp_path / "other-python.exe")
    assert manager._matches(process) is False


def test_control_snapshot_disables_conflicting_actions(tmp_path):
    manager = lifecycle(tmp_path)
    offline = manager.snapshot(False)
    assert offline["can_start"] is True
    assert offline["can_stop"] is False

    manager.operation = "restart"
    busy = manager.snapshot(True)
    assert busy["can_start"] is False
    assert busy["can_stop"] is False
    assert busy["can_restart"] is False
