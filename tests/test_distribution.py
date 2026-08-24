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
    assert len(workflow_files) == 12

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
    assert len(load_presets(config.workflow_dir)) == 6
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
