from __future__ import annotations

import importlib.metadata
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def test_build_metadata_matches_runtime_version():
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    init = (ROOT / "src" / "comfyui_remote_panel" / "__init__.py").read_text(encoding="utf-8")
    assert 'version = "0.4.0"' in pyproject
    assert '__version__ = "0.4.0"' in init


def test_installed_distribution_exposes_console_script():
    entry_points = importlib.metadata.entry_points(group="console_scripts")
    matches = [item for item in entry_points if item.name == "comfyui-remote-panel"]
    assert len(matches) == 1
    assert matches[0].value == "comfyui_remote_panel.__main__:main"


def test_mobile_creation_shell_uses_comfy_remote_design_system():
    static = ROOT / "src" / "comfyui_remote_panel" / "static"
    html = (static / "index.html").read_text(encoding="utf-8")
    css = (static / "app.css").read_text(encoding="utf-8")
    ux = (static / "workflow_ux.js").read_text(encoding="utf-8")
    refinements = (static / "ux_refinements.js").read_text(encoding="utf-8")
    refinement_css = (static / "ux_refinements.css").read_text(encoding="utf-8")

    assert "Comfy Remote" in html
    assert "H3 生成台" not in html
    assert 'class="top-nav"' in html
    assert 'class="bottom-nav"' not in html
    assert all(f'id="nav-{name}"' in html for name in ("generate", "jobs", "device"))
    assert 'id="workflow-picker-button"' in html
    assert 'id="bottom-sheet"' in html
    assert 'name="duration_seconds" type="range" min="5" max="15" step="1"' in html
    assert all(f'data-megapixels="{value}"' in html for value in ("0.2", "0.4", "0.6", "0.8", "0.9", "1.0"))
    assert 'accept=".wav,.mp3,.flac,.ogg,.m4a"' in html
    # Static assets are no-store in v0.4 development builds, so this design
    # contract checks the resource itself rather than pinning a cache-bust tag.
    assert '/static/workflow_ux.js' in html
    assert '/static/ux_refinements.js' in html

    assert "--accent: #c8f36a" in css
    assert "body.prompt-focused" in css
    assert "normalizePresetUi" in ux
    assert "保存并启用" in ux
    assert "data-generic-ratio" in ux
    assert "再次生成" in ux

    assert 'const order = ["9:16", "16:9", "1:1", "3:4", "4:3", "21:9"]' in refinements
    assert '$("#nav-jobs")?.addEventListener("click", refreshJobsFromTab, true)' in refinements
    assert "enhanceTaskDetails" in refinements
    assert "detail-copy-button" in refinement_css
    assert "#view-generate > .page-heading" in refinement_css
    assert ".job-card .job-prompt" in refinement_css
    assert "generic-advanced[data-refined-order" in refinement_css


def test_built_wheel_contains_packaged_workflows(tmp_path):
    pytest.importorskip("build")
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--outdir", str(tmp_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    wheel = next(tmp_path.glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        assert "comfyui_remote_panel/static/index.html" in names
        source_files = sorted((ROOT / "src" / "comfyui_remote_panel" / "workflows").glob("*/*.json"))
        for source in source_files:
            relative = source.relative_to(ROOT / "src" / "comfyui_remote_panel")
            assert f"comfyui_remote_panel/{relative.as_posix()}" in names


def test_source_workflow_mirror_matches_packaged_workflows():
    packaged = ROOT / "src" / "comfyui_remote_panel" / "workflows"
    source_files = sorted((ROOT / "workflows").glob("*/*.json"))
    assert source_files
    for source in source_files:
        relative = source.relative_to(ROOT / "workflows")
        assert (packaged / relative).read_bytes() == source.read_bytes()
