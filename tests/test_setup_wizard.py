from pathlib import Path

from comfyui_remote_panel.config import load_config
from comfyui_remote_panel.setup_wizard import inspect_comfyui_root, render_config


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
