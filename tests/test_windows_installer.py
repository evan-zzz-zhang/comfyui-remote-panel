from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_windows_installer_rejects_python_prereleases():
    script = (ROOT / "scripts" / "windows" / "Install-ComfyRemote.ps1").read_text(encoding="utf-8")

    assert "sys.version_info >= (3, 11)" in script
    assert "sys.version_info.releaselevel == 'final'" in script
    assert "Pre-release alpha/beta/rc builds are not supported" in script


def test_windows_installer_checks_an_existing_venv_before_reusing_it():
    script = (ROOT / "scripts" / "windows" / "Install-ComfyRemote.ps1").read_text(encoding="utf-8")

    assert "Existing .venv uses an unsupported pre-release/old Python" in script
