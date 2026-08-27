from pathlib import Path
from types import SimpleNamespace

from comfyui_remote_panel import setup_wizard
from comfyui_remote_panel.config import load_config
from comfyui_remote_panel.launch_discovery import ComfyStartOption
from comfyui_remote_panel.setup_wizard import (
    _choose_discovered_start_command,
    _choose_existing_config_action,
    _choose_installation,
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


def test_existing_config_menu_has_no_ambiguous_default_suffix():
    prompts: list[str] = []
    messages: list[str] = []
    answers = iter(["", "4", "1"])

    choice = _choose_existing_config_action(
        input_fn=lambda prompt: prompts.append(prompt) or next(answers),
        output_fn=messages.append,
    )

    assert choice == "1"
    assert prompts == ["选择操作: ", "选择操作: ", "选择操作: "]
    assert all("[1]" not in prompt for prompt in prompts)
    assert "请输入 1、2 或 3。" in messages


def test_existing_preferred_comfyui_is_reused_without_confirmation(tmp_path: Path):
    comfy = tmp_path / "ComfyUI"
    comfy.mkdir()
    (comfy / "main.py").write_text("", encoding="utf-8")
    preferred = inspect_comfyui_root(comfy)
    assert preferred is not None

    selected = _choose_installation(
        [],
        input_fn=lambda prompt: (_ for _ in ()).throw(AssertionError(prompt)),
        output_fn=lambda message: None,
        preferred=preferred,
    )

    assert selected == preferred


def test_single_detected_comfyui_is_used_without_question(tmp_path: Path):
    comfy = tmp_path / "ComfyUI"
    comfy.mkdir()
    (comfy / "main.py").write_text("", encoding="utf-8")
    installation = inspect_comfyui_root(comfy)
    assert installation is not None

    selected = _choose_installation(
        [installation],
        input_fn=lambda prompt: (_ for _ in ()).throw(AssertionError(prompt)),
        output_fn=lambda message: None,
    )

    assert selected == installation


def test_multiple_start_scripts_require_plain_number_without_default_suffix(monkeypatch, tmp_path: Path):
    default = (str(tmp_path / "python.exe"), "-s", "ComfyUI/main.py", "--windows-standalone-build")
    normal = default + ("--enable-manager",)
    sage = normal + ("--use-sage-attention",)
    installation = SimpleNamespace(
        portable=True,
        root=tmp_path,
        python_executable=tmp_path / "python.exe",
        start_command=default,
    )
    monkeypatch.setattr(
        setup_wizard,
        "discover_portable_start_options",
        lambda root, python: [
            ComfyStartOption("启动ComfyUI.bat", normal),
            ComfyStartOption("启动ComfyUI_SageAttention.bat", sage),
        ],
    )
    prompts: list[str] = []

    command = _choose_discovered_start_command(
        installation,
        input_fn=lambda prompt: prompts.append(prompt) or "2",
        output_fn=lambda message: None,
    )

    assert command == sage
    assert prompts == ["选择启动方式: "]


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
