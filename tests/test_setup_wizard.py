from pathlib import Path
from types import SimpleNamespace

from comfyui_remote_panel import setup_wizard
from comfyui_remote_panel.config import load_config
from comfyui_remote_panel.setup_wizard import (
    _default_control_visible_window,
    inspect_comfyui_root,
    render_config,
)


def test_detects_windows_portable_root_from_bundle_or_nested_comfyui(tmp_path: Path):
    root = tmp_path / "ComfyUI_windows_portable"
    (root / "ComfyUI").mkdir(parents=True)
    (root / "ComfyUI" / "main.py").write_text("", encoding="utf-8")
    (root / "python_embeded").mkdir()
    (root / "python_embeded" / "python.exe").write_bytes(b"")

    bundle = inspect_comfyui_root(root)
    nested = inspect_comfyui_root(root / "ComfyUI")

    assert bundle is not None and bundle.portable is True
    assert nested is not None and nested.portable is True
    assert bundle.root == root.resolve()
    assert nested.root == root.resolve()
    assert bundle.input_dir == (root / "ComfyUI" / "input").resolve()


def test_fresh_windows_setup_defaults_comfyui_console_visible(monkeypatch):
    monkeypatch.setattr(setup_wizard.os, "name", "nt")
    assert _default_control_visible_window(None) is True


def test_existing_setup_preserves_comfyui_console_preference(monkeypatch):
    monkeypatch.setattr(setup_wizard.os, "name", "nt")
    assert _default_control_visible_window(SimpleNamespace(comfyui_visible_window=False)) is False
    assert _default_control_visible_window(SimpleNamespace(comfyui_visible_window=True)) is True


def test_rendered_local_config_round_trips_without_h3_environment(tmp_path: Path):
    comfy = tmp_path / "ComfyUI"
    comfy.mkdir()
    (comfy / "main.py").write_text("", encoding="utf-8")
    installation = inspect_comfyui_root(comfy)
    assert installation is not None

    config_path = tmp_path / "config.toml"
    config_path.write_text(
        render_config(
            base_url="http://127.0.0.1:8188",
            installation=installation,
            auth_provider="local",
            allowed_logins=[],
            public_origin="http://127.0.0.1:8190",
            control_enabled=False,
            data_dir=tmp_path / "data",
            workflow_dir=tmp_path / "workflows",
        ),
        encoding="utf-8",
    )
    config = load_config(config_path)
    assert config.auth_provider == "local"
    assert config.comfyui_input_dir == (comfy / "input").resolve()
    assert config.comfyui_output_dir == (comfy / "output").resolve()


def test_rendered_control_config_can_keep_comfyui_console_visible(tmp_path: Path):
    comfy = tmp_path / "ComfyUI"
    comfy.mkdir()
    (comfy / "main.py").write_text("", encoding="utf-8")
    installation = inspect_comfyui_root(comfy)
    assert installation is not None

    config_path = tmp_path / "config.toml"
    config_path.write_text(
        render_config(
            base_url="http://127.0.0.1:8188",
            installation=installation,
            auth_provider="local",
            allowed_logins=[],
            public_origin="http://127.0.0.1:8190",
            control_enabled=True,
            data_dir=tmp_path / "data",
            workflow_dir=tmp_path / "workflows",
            control_visible_window=True,
        ),
        encoding="utf-8",
    )
    assert load_config(config_path).comfyui_visible_window is True
