import subprocess
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_wheel_contains_and_loads_all_workflow_resources(tmp_path):
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(tmp_path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    [wheel] = tmp_path.glob("*.whl")
    with zipfile.ZipFile(wheel) as archive:
        workflow_files = [
            name for name in archive.namelist()
            if "/workflows/" in name and name.endswith(".json")
        ]
        static_files = [name for name in archive.namelist() if "/static/" in name]
    assert len(workflow_files) == 54
    assert any(name.endswith("/static/workflow_ux.js") for name in static_files)
    assert any(name.endswith("/static/ux_refinements.js") for name in static_files)
    assert any(name.endswith("/static/ux_refinements.css") for name in static_files)

    install_dir = tmp_path / "installed"
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "--no-deps", "--target", str(install_dir), str(wheel)],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    code = f"""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, {str(install_dir)!r})
from aiohttp import ClientSession, web
from comfyui_remote_panel.app import create_app
from comfyui_remote_panel.config import Config
from comfyui_remote_panel.preset import load_presets

async def smoke():
    root = Path({str(tmp_path)!r}) / "runtime"
    config = Config(
        host="127.0.0.1", port=8190, public_origin="https://device.example.ts.net",
        allowed_logins=("owner@example.com",), comfyui_base_url="http://127.0.0.1:1",
        comfyui_input_dir=root / "input", comfyui_output_dir=root / "output",
        minimum_comfyui_version="0.26.0", data_dir=root / "data",
        workflow_dir=root / "missing-workflows", monitoring_interval=60,
        nvidia_smi_timeout=.1,
    )
    assert len(load_presets(config.workflow_dir)) == 27
    runner = web.AppRunner(create_app(config))
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    async with ClientSession() as session:
        async with session.get(f"http://127.0.0.1:{{port}}/healthz") as response:
            assert response.status == 200
            assert await response.json() == {{"status": "ok"}}
    await runner.cleanup()

asyncio.run(smoke())
"""
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )


def test_packaged_workflows_match_repository_sources():
    packaged = ROOT / "src" / "comfyui_remote_panel" / "workflows"
    source_files = sorted((ROOT / "workflows").glob("*/*.json"))
    assert len(source_files) == 12
    for source in source_files:
        relative = source.relative_to(ROOT / "workflows")
        assert (packaged / relative).read_bytes() == source.read_bytes()


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
    # v0.4 serves static assets with no-store, so the design contract checks
    # the resource path rather than pinning an arbitrary cache-bust query.
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
