from pathlib import Path
import shutil
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "scripts" / "windows" / "Install-ComfyRemote.ps1"


def _source() -> str:
    return INSTALLER.read_text(encoding="utf-8")


def test_windows_installer_rejects_python_prereleases():
    script = _source()

    assert "sys.version_info >= (3, 11)" in script
    assert "sys.version_info.releaselevel == 'final'" in script
    assert "stable Python 3.11 or newer" in script


def test_installer_health_checks_existing_venv_runtime_and_pip():
    script = _source()

    assert "function Test-VenvPython" in script
    assert "import sys,re,json,ssl,pip" in script
    assert "Test-VenvPython -Path $venvPython" in script
    assert "Existing .venv health check: OK" in script


def test_installer_preserves_unhealthy_venv_before_rebuilding():
    script = _source()

    assert '".venv.broken-{0}"' in script
    assert "Move-Item -LiteralPath $venvDir -Destination $backupPath" in script
    assert "Backed up unhealthy .venv to:" in script
    assert "& $PythonPath -m venv $venvDir" in script


def test_installer_verifies_fresh_venv_and_installed_package():
    script = _source()

    assert "Fresh .venv failed its health check" in script
    assert "Fresh .venv health check: OK" in script
    assert 'import comfyui_remote_panel; print(comfyui_remote_panel.__version__)' in script
    assert "could not be imported from .venv" in script


def test_installer_accepts_rooted_config_path():
    script = _source()

    assert "[System.IO.Path]::IsPathRooted($ConfigPath)" in script
    assert "setup --config $config" in script


def test_installer_powershell_syntax_when_powershell_is_available():
    powershell = shutil.which("powershell") or shutil.which("powershell.exe") or shutil.which("pwsh")
    if powershell is None:
        pytest.skip("PowerShell is not available on this CI runner")

    literal_path = str(INSTALLER).replace("'", "''")
    command = (
        "$ErrorActionPreference = 'Stop'; "
        f"$null = [scriptblock]::Create((Get-Content -Raw -LiteralPath '{literal_path}'))"
    )
    result = subprocess.run(
        [powershell, "-NoProfile", "-NonInteractive", "-Command", command],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
