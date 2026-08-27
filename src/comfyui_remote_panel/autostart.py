from __future__ import annotations

from dataclasses import dataclass
import locale
import os
from pathlib import Path
import shutil
import subprocess
import sys


class AutostartError(RuntimeError):
    pass


@dataclass(frozen=True)
class AutostartResult:
    action: str
    output: str


_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_VALUE = "ComfyUI Remote Panel"


def _powershell() -> str:
    executable = shutil.which("powershell.exe") or shutil.which("powershell") or shutil.which("pwsh")
    if not executable:
        raise AutostartError("PowerShell was not found")
    return executable


def _project_root(config_path: Path) -> Path:
    current = config_path.parent.resolve()
    for candidate in (current, *list(current.parents)[:3]):
        script = candidate / "scripts" / "windows" / "Register-RemotePanelTask.ps1"
        if script.is_file():
            return candidate
    raise AutostartError(
        "Windows helper scripts were not found; run this command from a source checkout"
    )


def _relative_to_root(path: Path, root: Path) -> str:
    try:
        return str(path.resolve().relative_to(root.resolve()))
    except ValueError:
        return str(path.resolve())


def _run_script(script: Path, *arguments: str) -> str:
    command = [
        _powershell(),
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        *arguments,
    ]
    try:
        result = subprocess.run(
            command,
            cwd=script.parents[2],
            capture_output=True,
            text=True,
            encoding=locale.getpreferredencoding(False),
            errors="replace",
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise AutostartError(str(exc)) from exc
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "PowerShell command failed").strip()
        raise AutostartError(message)
    return (result.stdout or "").strip()


def _require_windows() -> None:
    if os.name != "nt":
        raise AutostartError("Windows autostart is only supported on Windows")


def _task_access_denied(error: AutostartError) -> bool:
    message = str(error).lower()
    return any(
        marker in message
        for marker in (
            "0x80070005",
            "access is denied",
            "permissiondenied",
            "permission denied",
            "拒绝访问",
            "拒絕存取",
        )
    )


def _registry_command(config: Path) -> str:
    python = Path(sys.executable).resolve()
    pythonw = python.with_name("pythonw.exe")
    executable = pythonw if pythonw.is_file() else python
    return subprocess.list2cmdline(
        [
            str(executable),
            "-m",
            "comfyui_remote_panel",
            "start",
            "--config",
            str(config),
        ]
    )


def _install_registry_fallback(config: Path) -> str:
    try:
        import winreg

        with winreg.CreateKeyEx(
            winreg.HKEY_CURRENT_USER,
            _RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.SetValueEx(key, _RUN_VALUE, 0, winreg.REG_SZ, _registry_command(config))
    except (OSError, ImportError) as exc:
        raise AutostartError(f"current-user autostart fallback failed: {exc}") from exc
    return "✓ 已安装 Windows 登录自启动（当前用户模式，无需管理员权限）"


def _registry_status() -> str | None:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _RUN_KEY,
            0,
            winreg.KEY_QUERY_VALUE,
        ) as key:
            value, _ = winreg.QueryValueEx(key, _RUN_VALUE)
            return str(value) if value else None
    except (FileNotFoundError, OSError, ImportError):
        return None


def _remove_registry_fallback() -> bool:
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            _RUN_KEY,
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            winreg.DeleteValue(key, _RUN_VALUE)
        return True
    except FileNotFoundError:
        return False
    except (OSError, ImportError) as exc:
        raise AutostartError(f"failed to remove current-user autostart: {exc}") from exc


def install_autostart(config_path: str | Path = "config.toml") -> AutostartResult:
    _require_windows()
    config = Path(config_path).expanduser().resolve()
    if not config.is_file():
        raise AutostartError(f"config file not found: {config}")
    root = _project_root(config)
    script = root / "scripts" / "windows" / "Register-RemotePanelTask.ps1"
    python_path = Path(sys.executable).resolve()
    try:
        output = _run_script(
            script,
            "-ProjectRoot",
            str(root),
            "-ConfigPath",
            _relative_to_root(config, root),
            "-PythonPath",
            _relative_to_root(python_path, root),
        )
        return AutostartResult("install", output)
    except AutostartError as exc:
        if not _task_access_denied(exc):
            raise
        return AutostartResult("install", _install_registry_fallback(config))


def status_autostart(config_path: str | Path = "config.toml") -> AutostartResult:
    _require_windows()
    config = Path(config_path).expanduser().resolve()
    root = _project_root(config)
    script = root / "scripts" / "windows" / "Get-RemotePanelTaskStatus.ps1"
    try:
        task_output = _run_script(script)
    except AutostartError as exc:
        if not _task_access_denied(exc):
            raise
        task_output = "not-registered"
    if task_output.strip() != "not-registered":
        return AutostartResult("status", task_output)
    if _registry_status():
        return AutostartResult("status", "registered (current-user startup)")
    return AutostartResult("status", "not-registered")


def remove_autostart(config_path: str | Path = "config.toml") -> AutostartResult:
    _require_windows()
    config = Path(config_path).expanduser().resolve()
    root = _project_root(config)
    script = root / "scripts" / "windows" / "Unregister-RemotePanelTask.ps1"
    task_output = "not-registered"
    try:
        task_output = _run_script(script)
    except AutostartError as exc:
        if not _task_access_denied(exc):
            raise
    registry_removed = _remove_registry_fallback()
    if registry_removed:
        return AutostartResult("remove", "unregistered (current-user startup)")
    return AutostartResult("remove", task_output)
