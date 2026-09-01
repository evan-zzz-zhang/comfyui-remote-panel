from pathlib import Path

import pytest

from comfyui_remote_panel import autostart
from comfyui_remote_panel.autostart import AutostartError


def test_task_access_denied_recognizes_windows_permission_errors():
    assert autostart._task_access_denied(AutostartError("HRESULT 0x80070005"))
    assert autostart._task_access_denied(AutostartError("PermissionDenied"))
    assert autostart._task_access_denied(AutostartError("Access is denied"))
    assert not autostart._task_access_denied(AutostartError("script not found"))


def test_registry_autostart_uses_hidden_cli_start_launcher(tmp_path: Path, monkeypatch):
    scripts = tmp_path / "Scripts"
    scripts.mkdir()
    python = scripts / "python.exe"
    pythonw = scripts / "pythonw.exe"
    python.write_bytes(b"")
    pythonw.write_bytes(b"")
    config = tmp_path / "config.toml"

    monkeypatch.setattr(autostart.sys, "executable", str(python))
    command = autostart._registry_command(config)

    assert "pythonw.exe" in command
    assert "comfyui_remote_panel" in command
    assert " start " in f" {command} "
    assert "--config" in command
    assert str(config) in command


def test_install_falls_back_to_current_user_startup_when_task_scheduler_denies_access(
    tmp_path: Path, monkeypatch
):
    config = tmp_path / "config.toml"
    config.write_text("# test", encoding="utf-8")
    script = tmp_path / "scripts" / "windows" / "Register-RemotePanelTask.ps1"
    script.parent.mkdir(parents=True)
    script.write_text("", encoding="utf-8")

    monkeypatch.setattr(autostart, "_require_windows", lambda: None)
    monkeypatch.setattr(autostart, "_project_root", lambda _: tmp_path)
    monkeypatch.setattr(
        autostart,
        "_run_script",
        lambda *args: (_ for _ in ()).throw(AutostartError("Register-ScheduledTask HRESULT 0x80070005")),
    )
    monkeypatch.setattr(
        autostart,
        "_install_registry_fallback",
        lambda path: "fallback-installed",
    )

    result = autostart.install_autostart(config)

    assert result.action == "install"
    assert result.output == "fallback-installed"


def test_install_does_not_hide_unrelated_task_scheduler_errors(tmp_path: Path, monkeypatch):
    config = tmp_path / "config.toml"
    config.write_text("# test", encoding="utf-8")
    monkeypatch.setattr(autostart, "_require_windows", lambda: None)
    monkeypatch.setattr(autostart, "_project_root", lambda _: tmp_path)
    monkeypatch.setattr(
        autostart,
        "_run_script",
        lambda *args: (_ for _ in ()).throw(AutostartError("PowerShell command failed")),
    )

    with pytest.raises(AutostartError, match="PowerShell command failed"):
        autostart.install_autostart(config)


def test_install_passes_external_python_as_absolute_path(tmp_path: Path, monkeypatch):
    root = tmp_path / "project"
    config = root / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text("# test", encoding="utf-8")
    script = root / "scripts" / "windows" / "Register-RemotePanelTask.ps1"
    script.parent.mkdir(parents=True)
    script.write_text("", encoding="utf-8")
    external_python = tmp_path / "Python312" / "python.exe"

    captured: tuple[str, ...] = ()

    def fake_run_script(_script: Path, *args: str) -> str:
        nonlocal captured
        captured = args
        return "registered"

    monkeypatch.setattr(autostart, "_require_windows", lambda: None)
    monkeypatch.setattr(autostart, "_project_root", lambda _: root)
    monkeypatch.setattr(autostart.sys, "executable", str(external_python))
    monkeypatch.setattr(autostart, "_run_script", fake_run_script)

    result = autostart.install_autostart(config)

    assert result.output == "registered"
    python_index = captured.index("-PythonPath") + 1
    assert captured[python_index] == str(external_python.resolve())


def test_register_task_script_quotes_config_without_escaped_backslashes():
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "windows"
        / "Register-RemotePanelTask.ps1"
    )
    source = script.read_text(encoding="utf-8")

    # A literal \" inside the single-quoted PowerShell string reaches Task
    # Scheduler verbatim, so the CLI receives a config path still wrapped in real
    # quote characters and exits with code 2 instead of starting the panel.
    assert '\\"{0}\\"' not in source
    assert '-m comfyui_remote_panel start --config "{0}"' in source


def test_register_task_script_handles_rooted_python_and_config_paths():
    script = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "windows"
        / "Register-RemotePanelTask.ps1"
    )
    source = script.read_text(encoding="utf-8")

    assert "[System.IO.Path]::IsPathRooted($PythonPath)" in source
    assert "[System.IO.Path]::IsPathRooted($ConfigPath)" in source
    assert "Resolve-Path -LiteralPath $pythonCandidate" in source
    assert "Resolve-Path -LiteralPath $configCandidate" in source
