from pathlib import Path

from comfyui_remote_panel import panel_control
from comfyui_remote_panel.panel_control import PanelController


def _write_config(tmp_path: Path) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(
        f"""
[server]
host = "127.0.0.1"
port = 8190
public_origin = "http://127.0.0.1:8190"
[auth]
provider = "local"
allowed_logins = []
[comfyui]
base_url = "http://127.0.0.1:8188"
input_dir = "{(tmp_path / 'input').as_posix()}"
output_dir = "{(tmp_path / 'output').as_posix()}"
[storage]
data_dir = "{(tmp_path / 'data').as_posix()}"
workflow_dir = "{(tmp_path / 'workflows').as_posix()}"
[monitoring]
interval_seconds = 3
nvidia_smi_timeout_seconds = 2
""",
        encoding="utf-8",
    )
    return path


def test_stale_runtime_is_cleared_when_panel_is_not_listening(tmp_path: Path, monkeypatch):
    controller = PanelController(_write_config(tmp_path))
    controller._write_runtime(999999)
    monkeypatch.setattr(controller, "_listener_pid", lambda: None)
    monkeypatch.setattr("comfyui_remote_panel.panel_control.psutil.pid_exists", lambda pid: False)

    status = controller.status()

    assert status.running is False
    assert status.reason == "stopped"
    assert not controller.runtime_path.exists()
    assert not controller.pid_path.exists()


def test_unknown_listener_is_never_adopted_or_stopped(tmp_path: Path, monkeypatch):
    controller = PanelController(_write_config(tmp_path))
    monkeypatch.setattr(controller, "_listener_pid", lambda: 12345)

    class FakeProcess:
        pass

    monkeypatch.setattr("comfyui_remote_panel.panel_control.psutil.Process", lambda pid: FakeProcess())
    monkeypatch.setattr(controller, "_command_signature", lambda process: False)

    status = controller.status()
    assert status.running is False
    assert status.reason == "port-occupied"


def test_windows_background_flags_hide_console(monkeypatch):
    monkeypatch.setattr(panel_control.os, "name", "nt")
    monkeypatch.setattr(panel_control.subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200, raising=False)
    monkeypatch.setattr(panel_control.subprocess, "CREATE_NO_WINDOW", 0x08000000, raising=False)
    monkeypatch.setattr(panel_control.subprocess, "DETACHED_PROCESS", 0x00000008, raising=False)

    flags = panel_control._background_creationflags()

    assert flags & panel_control.subprocess.CREATE_NO_WINDOW
    assert flags & panel_control.subprocess.CREATE_NEW_PROCESS_GROUP
    assert not flags & panel_control.subprocess.DETACHED_PROCESS
