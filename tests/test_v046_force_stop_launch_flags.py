from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import psutil

from comfyui_remote_panel.comfy import ComfyClient
from comfyui_remote_panel.config import Config
from comfyui_remote_panel.lifecycle import ComfyLifecycle


def lifecycle(tmp_path: Path) -> ComfyLifecycle:
    executable = tmp_path / "python.exe"
    executable.touch()
    (tmp_path / "ComfyUI").mkdir()
    (tmp_path / "ComfyUI" / "main.py").touch()
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
        comfyui_start_command=(
            "python.exe",
            "-s",
            "ComfyUI/main.py",
            "--enable-manager",
            "--use-sage-attention",
        ),
        comfyui_working_dir=tmp_path,
    )
    comfy = ComfyClient(config.comfyui_base_url, config.minimum_comfyui_version, "test")
    return ComfyLifecycle(config, comfy)


def test_force_stop_discovery_tolerates_optional_flag_changed_after_process_started(tmp_path, monkeypatch):
    manager = lifecycle(tmp_path)
    executable = str(tmp_path / "python.exe")
    process = Mock(pid=4321)
    process.exe.return_value = executable
    process.cwd.return_value = str(tmp_path)
    process.cmdline.return_value = [
        executable,
        "-s",
        "ComfyUI/main.py",
        "--enable-manager",
    ]
    listener = SimpleNamespace(
        status=psutil.CONN_LISTEN,
        pid=4321,
        laddr=SimpleNamespace(port=8188),
    )
    monkeypatch.setattr(psutil, "net_connections", Mock(return_value=[listener]))
    monkeypatch.setattr(psutil, "Process", Mock(return_value=process))

    assert manager._matches(process) is False
    assert manager._verified_listener_process() is process


def test_force_stop_discovery_still_rejects_wrong_working_directory(tmp_path, monkeypatch):
    manager = lifecycle(tmp_path)
    executable = str(tmp_path / "python.exe")
    other_cwd = tmp_path / "other"
    other_cwd.mkdir()
    process = Mock(pid=4321)
    process.exe.return_value = executable
    process.cwd.return_value = str(other_cwd)
    process.cmdline.return_value = [
        executable,
        "-s",
        "ComfyUI/main.py",
        "--enable-manager",
    ]
    listener = SimpleNamespace(
        status=psutil.CONN_LISTEN,
        pid=4321,
        laddr=SimpleNamespace(port=8188),
    )
    monkeypatch.setattr(psutil, "net_connections", Mock(return_value=[listener]))
    monkeypatch.setattr(psutil, "Process", Mock(return_value=process))

    assert manager._verified_listener_process() is None
