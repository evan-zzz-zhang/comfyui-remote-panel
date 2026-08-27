from pathlib import Path

from comfyui_remote_panel.launch_discovery import discover_portable_start_options


def test_discovers_portable_batch_launch_flags_without_wrapping_cmd(tmp_path: Path):
    root = tmp_path / "ComfyUI_H3_Portable"
    python = root / "python_embeded" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"")

    (root / "启动ComfyUI.bat").write_text(
        "@echo off\n"
        "cd /d \"%~dp0\"\n"
        "python_embeded\\python.exe -s ComfyUI\\main.py --windows-standalone-build --enable-manager\n",
        encoding="utf-8",
    )
    (root / "启动ComfyUI_SageAttention.bat").write_text(
        "@echo off\n"
        "cd /d \"%~dp0\"\n"
        "python_embeded\\python.exe -s ComfyUI\\main.py --windows-standalone-build --enable-manager --use-sage-attention\n",
        encoding="utf-8",
    )

    options = discover_portable_start_options(root, python)
    by_name = {option.label: option.command for option in options}

    normal = by_name["启动ComfyUI.bat"]
    sage = by_name["启动ComfyUI_SageAttention.bat"]
    assert normal[0] == str(python)
    assert normal[1:] == (
        "-s",
        "ComfyUI/main.py",
        "--windows-standalone-build",
        "--enable-manager",
    )
    assert sage[0] == str(python)
    assert sage[-2:] == ("--enable-manager", "--use-sage-attention")
    assert all("cmd.exe" not in token.lower() for command in by_name.values() for token in command)


def test_ignores_dynamic_batch_invocations_instead_of_guessing(tmp_path: Path):
    root = tmp_path / "portable"
    python = root / "python_embeded" / "python.exe"
    python.parent.mkdir(parents=True)
    python.write_bytes(b"")
    (root / "dynamic.bat").write_text(
        "python_embeded\\python.exe -s ComfyUI\\main.py %EXTRA_ARGS%\n",
        encoding="utf-8",
    )

    assert discover_portable_start_options(root, python) == []
