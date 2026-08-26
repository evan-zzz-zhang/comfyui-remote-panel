from __future__ import annotations

from dataclasses import dataclass
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
            encoding="utf-8",
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


def install_autostart(config_path: str | Path = "config.toml") -> AutostartResult:
    _require_windows()
    config = Path(config_path).expanduser().resolve()
    if not config.is_file():
        raise AutostartError(f"config file not found: {config}")
    root = _project_root(config)
    script = root / "scripts" / "windows" / "Register-RemotePanelTask.ps1"
    python_path = Path(sys.executable).resolve()
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


def status_autostart(config_path: str | Path = "config.toml") -> AutostartResult:
    _require_windows()
    config = Path(config_path).expanduser().resolve()
    root = _project_root(config)
    script = root / "scripts" / "windows" / "Get-RemotePanelTaskStatus.ps1"
    return AutostartResult("status", _run_script(script))


def remove_autostart(config_path: str | Path = "config.toml") -> AutostartResult:
    _require_windows()
    config = Path(config_path).expanduser().resolve()
    root = _project_root(config)
    script = root / "scripts" / "windows" / "Unregister-RemotePanelTask.ps1"
    return AutostartResult("remove", _run_script(script))
