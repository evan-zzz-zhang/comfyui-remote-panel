import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import psutil
import pytest

from comfyui_remote_panel.comfy import ComfyClient, ComfyError
from comfyui_remote_panel.config import Config
from comfyui_remote_panel.lifecycle import ComfyLifecycle, LifecycleError
from comfyui_remote_panel.metrics import MetricsService


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


def test_unresponsive_snapshot_only_offers_force_restart(tmp_path):
    manager = lifecycle(tmp_path)
    snapshot = manager.snapshot(False, unresponsive=True, managed_process_alive=True)

    assert snapshot["state"] == "unresponsive"
    assert snapshot["can_start"] is False
    assert snapshot["can_stop"] is False
    assert snapshot["can_restart"] is False
    assert snapshot["can_force_restart"] is True


@pytest.mark.asyncio
async def test_force_restart_refuses_without_verified_recorded_process(tmp_path, monkeypatch):
    manager = lifecycle(tmp_path)
    manager._is_online = AsyncMock(return_value=False)
    monkeypatch.setattr(manager, "managed_process_alive", Mock(return_value=False))

    with pytest.raises(LifecycleError, match="安全确认"):
        await manager.trigger("force_restart")


@pytest.mark.asyncio
async def test_force_restart_runs_force_stop_before_start(tmp_path):
    manager = lifecycle(tmp_path)
    calls = []

    async def force_stop():
        calls.append("force_stop")

    async def start():
        calls.append("start")

    manager._force_stop = force_stop
    manager._start = start
    await manager._run("force_restart")

    assert calls == ["force_stop", "start"]


def test_force_stop_only_targets_captured_process_tree(tmp_path, monkeypatch):
    manager = lifecycle(tmp_path)
    main = Mock(pid=100)
    child = Mock(pid=101)
    main.create_time.return_value = 10.0
    child.create_time.return_value = 11.0
    main.is_running.return_value = True
    child.is_running.return_value = True
    main.children.return_value = [child]
    monkeypatch.setattr(psutil, "wait_procs", Mock(return_value=([child, main], [])))

    manager._force_stop_recorded_tree(main)

    child.terminate.assert_called_once_with()
    main.terminate.assert_called_once_with()
    child.kill.assert_not_called()
    main.kill.assert_not_called()


def test_force_stop_skips_descendant_if_process_instance_changed(tmp_path, monkeypatch):
    manager = lifecycle(tmp_path)
    main = Mock(pid=100)
    child = Mock(pid=101)
    main.create_time.return_value = 10.0
    main.is_running.return_value = True
    child.create_time.side_effect = [11.0, 12.0]
    child.is_running.return_value = True
    main.children.return_value = [child]
    monkeypatch.setattr(psutil, "wait_procs", Mock(return_value=([main], [])))

    manager._force_stop_recorded_tree(main)

    child.terminate.assert_not_called()
    child.kill.assert_not_called()
    main.terminate.assert_called_once_with()


class _FakeDb:
    async def tracked_size(self):
        return 0


class _FailingComfy:
    async def system_stats(self):
        raise ComfyError("offline")

    async def queue(self):
        raise ComfyError("offline")

    async def validate_presets(self, *_args, **_kwargs):
        raise AssertionError("offline ComfyUI must not validate presets")


class _OnlineComfy:
    async def system_stats(self):
        return {"system": {"comfyui_version": "0.30.0"}, "devices": []}

    async def queue(self):
        return {"queue_running": [], "queue_pending": []}

    async def validate_presets(self, *_args, **_kwargs):
        return None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("managed_alive", "expected_state"),
    [(False, "offline"), (True, "unresponsive")],
)
async def test_metrics_distinguishes_offline_from_verified_unresponsive_process(
    tmp_path, managed_alive, expected_state
):
    lifecycle_mock = Mock()
    lifecycle_mock.managed_process_alive.return_value = managed_alive
    lifecycle_mock.snapshot.side_effect = lambda online, **kwargs: {
        "enabled": True,
        "state": "online" if online else ("unresponsive" if kwargs["managed_process_alive"] else "offline"),
        "managed_process_alive": kwargs["managed_process_alive"],
    }
    service = MetricsService(
        _FakeDb(), _FailingComfy(), {}, Mock(), tmp_path, 3, 1, lifecycle_mock
    )
    service._nvidia_gpus = AsyncMock(return_value=[])

    snapshot = await service.collect()

    assert snapshot["comfyui"]["state"] == expected_state
    lifecycle_mock.snapshot.assert_called_once()
    assert lifecycle_mock.snapshot.call_args.kwargs["managed_process_alive"] is managed_alive


@pytest.mark.asyncio
async def test_online_api_wins_even_when_managed_process_record_exists(tmp_path):
    lifecycle_mock = Mock()
    lifecycle_mock.managed_process_alive.return_value = True
    lifecycle_mock.snapshot.side_effect = lambda online, **kwargs: {
        "enabled": True,
        "state": "online" if online else "unresponsive",
        "managed_process_alive": kwargs["managed_process_alive"],
    }
    service = MetricsService(
        _FakeDb(), _OnlineComfy(), {}, Mock(), tmp_path, 3, 1, lifecycle_mock
    )
    service._nvidia_gpus = AsyncMock(return_value=[])

    snapshot = await service.collect()

    assert snapshot["comfyui"]["state"] == "online"
    assert snapshot["comfyui"]["online"] is True
