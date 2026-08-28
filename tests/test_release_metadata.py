from pathlib import Path
import tomllib

from comfyui_remote_panel import __version__


ROOT = Path(__file__).resolve().parents[1]


def test_package_and_pyproject_versions_match():
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert pyproject["project"]["version"] == __version__


def test_v040_release_metadata_is_not_marked_as_dev_build():
    assert __version__ == "0.4.0"
    assert "dev" not in __version__.lower()
