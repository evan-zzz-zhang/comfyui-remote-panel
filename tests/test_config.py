from pathlib import Path

import pytest

from comfyui_remote_panel.config import ConfigError, load_config


def write_config(
    tmp_path: Path, host: str = "127.0.0.1", port: int = 8190,
    provider: str = "tailscale", public_origin: str = "https://device.example.ts.net",
) -> Path:
    path = tmp_path / "config.toml"
    path.write_text(
        f"""
[server]
host = "{host}"
port = {port}
public_origin = "{public_origin}"
[auth]
provider = "{provider}"
allowed_logins = ["owner@example.com"]
[comfyui]
base_url = "http://127.0.0.1:8188"
input_dir = "input"
output_dir = "output"
[storage]
data_dir = "data"
workflow_dir = "workflows"
[monitoring]
interval_seconds = 3
nvidia_smi_timeout_seconds = 2
""",
        encoding="utf-8",
    )
    return path


def test_config_resolves_relative_paths(tmp_path):
    config = load_config(write_config(tmp_path))
    assert config.host == "127.0.0.1"
    assert config.data_dir == (tmp_path / "data").resolve()
    assert config.allowed_logins == ("owner@example.com",)


def test_config_rejects_non_loopback_bind(tmp_path):
    with pytest.raises(ConfigError, match="127.0.0.1"):
        load_config(write_config(tmp_path, "0.0.0.0"))


def test_config_rejects_other_port(tmp_path):
    with pytest.raises(ConfigError, match="8190"):
        load_config(write_config(tmp_path, port=9000))


def test_config_loads_comfyui_control(tmp_path):
    path = write_config(tmp_path)
    text = path.read_text(encoding="utf-8").replace(
        '[storage]',
        '''[comfyui.control]
enabled = true
working_dir = "comfy-portable"
start_command = ["python.exe", "ComfyUI/main.py"]
visible_window = true
startup_timeout_seconds = 90
shutdown_timeout_seconds = 20
[storage]''',
    )
    path.write_text(text, encoding="utf-8")
    config = load_config(path)
    assert config.comfyui_control_enabled is True
    assert config.comfyui_start_command == ("python.exe", "ComfyUI/main.py")
    assert config.comfyui_working_dir == (tmp_path / "comfy-portable").resolve()
    assert config.comfyui_visible_window is True
    assert config.comfyui_startup_timeout == 90


def test_enabled_control_requires_command(tmp_path):
    path = write_config(tmp_path)
    text = path.read_text(encoding="utf-8").replace(
        '[storage]',
        '''[comfyui.control]
enabled = true
working_dir = "comfy-portable"
[storage]''',
    )
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match="start_command"):
        load_config(path)


def test_local_auth_accepts_only_loopback_http_origin(tmp_path):
    config = load_config(write_config(
        tmp_path, provider="local", public_origin="http://127.0.0.1:8190"
    ))
    assert config.auth_provider == "local"

    with pytest.raises(ConfigError, match="local HTTP"):
        load_config(write_config(
            tmp_path, provider="local", public_origin="http://192.168.1.10:8190"
        ))


def test_rejects_unknown_auth_provider(tmp_path):
    with pytest.raises(ConfigError, match="tailscale or local"):
        load_config(write_config(tmp_path, provider="lan"))
