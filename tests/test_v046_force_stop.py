from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import psutil
import pytest

from comfyui_remote_panel.comfy import ComfyClient
from comfyui_remote_panel.config import Config
from comfyui_remote_panel.lifecycle import ComfyLifecycle


ROOT = Path(__file__).resolve().parents[1]
FORCE_STOP_JS = (ROOT / "src" / "comfyui_remote_panel" / "static" / "v046_force_stop_ui.js").read_text(encoding="utf-8")
FRONTEND = (ROOT / "src" / "comfyui_remote_panel" / "v046_frontend.py").read_text(encoding="utf-8")


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


def test_snapshot_allows_force_stop_for_verified_unmanaged_listener(tmp_path):
    manager = lifecycle(tmp_path)
    control = manager.snapshot(
        False,
        verified_process_alive=True,
        managed_process_alive=False,
        unresponsive=True,
    )
    assert control["state"] == "unresponsive"
    assert control["can_start"] is False
    assert control["can_force_stop"] is True
    assert control["can_force_restart"] is False


def test_verified_listener_requires_configured_port_and_command(tmp_path, monkeypatch):
    manager = lifecycle(tmp_path)
    process = Mock(pid=4321)
    listener = SimpleNamespace(status=psutil.CONN_LISTEN, pid=4321, laddr=SimpleNamespace(port=8188))
    other = SimpleNamespace(status=psutil.CONN_LISTEN, pid=9999, laddr=SimpleNamespace(port=9000))
    monkeypatch.setattr(psutil, "net_connections", Mock(return_value=[listener, other]))
    monkeypatch.setattr(psutil, "Process", Mock(return_value=process))
    monkeypatch.setattr(manager, "_matches", Mock(return_value=True))

    assert manager._verified_listener_process() is process
    manager._matches.assert_called_once_with(process)


@pytest.mark.asyncio
async def test_force_stop_uses_verified_listener_when_record_is_missing(tmp_path, monkeypatch):
    manager = lifecycle(tmp_path)
    process = Mock(pid=4321)
    monkeypatch.setattr(manager, "_recorded_process", Mock(return_value=None))
    monkeypatch.setattr(manager, "_verified_listener_process", Mock(return_value=process))
    force_tree = Mock()
    monkeypatch.setattr(manager, "_force_stop_recorded_tree", force_tree)
    manager._is_online = AsyncMock(return_value=False)

    await manager._force_stop()

    force_tree.assert_called_once_with(process)


def test_force_stop_ui_reuses_existing_red_close_button_and_has_strong_confirmation():
    assert 'button.dataset.v046ForceStop = "true"' in FORCE_STOP_JS
    assert 'button.textContent = "强制关闭"' in FORCE_STOP_JS
    assert 'control.verified_process_alive' in FORCE_STOP_JS
    assert 'control.managed_process_alive' in FORCE_STOP_JS
    assert 'control.operation === "force_stop"' in FORCE_STOP_JS
    assert '/api/comfyui/control/force_stop' in FORCE_STOP_JS
    assert '正在监听当前 ComfyUI 端口的唯一进程及其子进程' in FORCE_STOP_JS
    assert 'v046_force_stop_ui.js?v=0.4.6.2' in FRONTEND
