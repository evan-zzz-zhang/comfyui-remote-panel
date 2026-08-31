from pathlib import Path
from unittest.mock import Mock

from comfyui_remote_panel.metrics import MetricsService
from comfyui_remote_panel.v046_sage_attention_status import _listener_uses_sage_attention


ROOT = Path(__file__).resolve().parents[1]
SAGE_UI = (
    ROOT / "src" / "comfyui_remote_panel" / "static" / "v046_sage_attention_status.js"
).read_text(encoding="utf-8")
FRONTEND = (ROOT / "src" / "comfyui_remote_panel" / "v046_frontend.py").read_text(encoding="utf-8")


def listener(command_line):
    process = Mock()
    process.cmdline.return_value = command_line
    lifecycle = Mock()
    lifecycle._verified_listener_process.return_value = process
    return lifecycle


def test_sage_attention_status_uses_actual_listener_command_line():
    lifecycle = listener([
        "python.exe",
        "-s",
        "ComfyUI/main.py",
        "--windows-standalone-build",
        "--enable-manager",
        "--use-sage-attention",
    ])

    assert _listener_uses_sage_attention(lifecycle) is True


def test_sage_attention_status_does_not_follow_config_when_live_listener_lacks_flag():
    lifecycle = listener([
        "python.exe",
        "-s",
        "ComfyUI/main.py",
        "--windows-standalone-build",
        "--enable-manager",
    ])

    assert _listener_uses_sage_attention(lifecycle) is False


def test_sage_attention_status_is_false_without_verified_listener():
    lifecycle = Mock()
    lifecycle._verified_listener_process.return_value = None

    assert _listener_uses_sage_attention(lifecycle) is False


def test_sage_attention_status_is_false_for_unconfigured_mock_listener():
    lifecycle = Mock()

    assert _listener_uses_sage_attention(lifecycle) is False


def test_metrics_collector_has_sage_attention_runtime_patch_installed():
    assert getattr(MetricsService._collect_once, "_v046_sage_attention_status", False) is True


def test_sage_attention_device_chip_is_conditional_and_cache_busted():
    assert 'metrics?.comfyui?.sage_attention' in SAGE_UI
    assert 'dataset.v046SageAttention' in SAGE_UI
    assert 'SageAttention' in SAGE_UI
    assert 'overview.append(chip)' in SAGE_UI
    assert 'v046_sage_attention_status.js?v=0.4.6.1' in FRONTEND
