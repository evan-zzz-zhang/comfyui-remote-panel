import json
import asyncio
import time
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import psutil
import pytest

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


def test_control_snapshot_exposes_normalized_device_states(tmp_path):
    manager = lifecycle(tmp_path)
    assert manager.snapshot(True)["state"] == "online"
    assert manager.snapshot(False)["state"] == "offline"
    assert manager.snapshot(False, unresponsive=True)["state"] == "unresponsive"

    manager.phase = "starting"
    assert manager.snapshot(False)["state"] == "starting"
    manager.phase = None
    manager.last_error_action = "start"
    manager.last_error = "boom"
    failed = manager.snapshot(False)
    assert failed["state"] == "start_failed"
    assert failed["summary"] == "boom"


def test_recorded_process_requires_all_four_identity_fields(tmp_path, monkeypatch):
    manager = lifecycle(tmp_path)
    executable = str(tmp_path / "python.exe")
    command_line = [executable, "-s", "ComfyUI/main.py"]
    payload = {
        "pid": 1234,
        "create_time": 100.0,
        "executable": executable,
        "command_line": command_line,
    }
    manager.record_path.parent.mkdir(parents=True)

    process = Mock(pid=1234)
    process.create_time.return_value = 100.0
    process.exe.return_value = executable
    process.cmdline.return_value = command_line
    monkeypatch.setattr(psutil, "Process", Mock(return_value=process))

    manager.record_path.write_text(json.dumps(payload), encoding="utf-8")
    assert manager._recorded_process() is process

    for field, unsafe_value in (
        ("create_time", 101.0),
        ("executable", str(tmp_path / "other.exe")),
        ("command_line", [executable, "other.py"]),
    ):
        unsafe_payload = {**payload, field: unsafe_value}
        manager.record_path.write_text(json.dumps(unsafe_payload), encoding="utf-8")
        assert manager._recorded_process() is None


@pytest.mark.asyncio
async def test_stop_never_terminates_recorded_descendants(tmp_path, monkeypatch, caplog):
    manager = lifecycle(tmp_path)
    manager._is_online = AsyncMock(return_value=False)

    process = Mock(pid=1234)
    child = Mock(pid=5678)
    child.create_time.return_value = 200.0
    child.is_running.return_value = True
    process.children.return_value = [child]
    monkeypatch.setattr(manager, "_recorded_process", Mock(return_value=process))
    monkeypatch.setattr(psutil, "wait_procs", Mock(return_value=([process], [])))

    manager.record_path.parent.mkdir(parents=True)
    manager.record_path.write_text("{}", encoding="utf-8")
    await manager._stop()

    process.terminate.assert_called_once_with()
    process.kill.assert_not_called()
    child.terminate.assert_not_called()
    child.kill.assert_not_called()
    assert "descendant processes remain" in caplog.text


@pytest.mark.asyncio
async def test_stop_refuses_listener_fallback_without_a_record(tmp_path, monkeypatch):
    manager = lifecycle(tmp_path)
    monkeypatch.setattr(manager, "_recorded_process", Mock(return_value=None))

    with pytest.raises(Exception, match="进程记录"):
        await manager._stop()


@pytest.mark.asyncio
async def test_slow_process_wait_does_not_block_event_loop(tmp_path, monkeypatch):
    manager = lifecycle(tmp_path)
    process = Mock(pid=1234)
    monkeypatch.setattr(manager, "_recorded_process", Mock(return_value=process))
    manager._is_online = AsyncMock(return_value=False)

    def slow_stop(_process):
        time.sleep(0.15)
        return []

    monkeypatch.setattr(manager, "_stop_recorded_process", slow_stop)
    stop_task = asyncio.create_task(manager._stop())
    started = time.perf_counter()
    await asyncio.wait_for(asyncio.sleep(0.01), timeout=0.05)
    assert time.perf_counter() - started < 0.05
    await stop_task
