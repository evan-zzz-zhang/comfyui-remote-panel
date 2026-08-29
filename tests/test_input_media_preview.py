from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from comfyui_remote_panel.app import create_app
from comfyui_remote_panel.config import Config


ROOT = Path(__file__).resolve().parents[1]
LOGIN = {"Tailscale-User-Login": "owner@example.com"}


def _config(tmp_path: Path) -> Config:
    return Config(
        host="127.0.0.1",
        port=8190,
        public_origin="https://device.example.ts.net",
        allowed_logins=("owner@example.com",),
        comfyui_base_url="http://127.0.0.1:1",
        comfyui_input_dir=tmp_path / "input",
        comfyui_output_dir=tmp_path / "output",
        minimum_comfyui_version="0.0.0",
        data_dir=tmp_path / "data",
        workflow_dir=ROOT / "workflows",
        monitoring_interval=60,
        nvidia_smi_timeout=.1,
        auth_provider="tailscale",
    )


def _record(job_id: str) -> dict:
    return {
        "id": job_id,
        "preset_id": "workflow",
        "status": "succeeded",
        "mode": "test",
        "prompt": "",
        "duration_seconds": 5,
        "aspect_ratio": "1:1",
        "megapixels": 1.0,
        "seed": 0,
        "scheduler": "normal",
        "sampler": "euler",
        "steps": 8,
    }


@pytest.mark.asyncio
async def test_input_media_preview_requires_auth_and_enforces_ownership(tmp_path, aiohttp_client):
    client = await aiohttp_client(create_app(_config(tmp_path)))
    input_root = client.app["files"].input_root
    source = input_root / "rp_source_image_0.png"
    Image.new("RGB", (32, 20), "white").save(source)
    await client.app["db"].create_job(
        _record("source"),
        [{"role": "image_0", "path": source, "size_bytes": source.stat().st_size}],
    )
    await client.app["db"].create_job(_record("other"), [])
    artifact = next(
        item for item in await client.app["db"].list_artifacts("source")
        if item["direction"] == "input"
    )
    url = f"/api/jobs/source/inputs/{artifact['id']}"

    assert (await client.get(url)).status == 403

    response = await client.get(url, headers=LOGIN)
    assert response.status == 200
    assert response.headers["Cache-Control"] == "private, no-cache"
    assert response.headers["Content-Type"].startswith("image/png")
    assert response.headers.get("ETag")
    etag = response.headers["ETag"]
    body = await response.read()
    assert body == source.read_bytes()

    cached = await client.get(url, headers={**LOGIN, "If-None-Match": etag})
    assert cached.status == 304

    wrong_job = await client.get(
        f"/api/jobs/other/inputs/{artifact['id']}", headers=LOGIN
    )
    assert wrong_job.status == 404


@pytest.mark.asyncio
async def test_input_media_preview_rejects_outputs_missing_files_and_unmanaged_paths(tmp_path, aiohttp_client):
    client = await aiohttp_client(create_app(_config(tmp_path)))
    input_root = client.app["files"].input_root
    output_root = client.app["files"].output_root

    source = input_root / "rp_source_image_0.png"
    Image.new("RGB", (24, 24), "white").save(source)
    await client.app["db"].create_job(
        _record("source"),
        [{"role": "image_0", "path": source, "size_bytes": source.stat().st_size}],
    )
    input_artifact = next(
        item for item in await client.app["db"].list_artifacts("source")
        if item["direction"] == "input"
    )

    output = output_root / "rp_source_output.png"
    Image.new("RGB", (12, 12), "white").save(output)
    output_id = await client.app["db"].add_artifact(
        "source", "output", "primary", 0, output, "image", "image/png", "result.png", output.stat().st_size
    )
    assert (
        await client.get(f"/api/jobs/source/inputs/{output_id}", headers=LOGIN)
    ).status == 404

    source.unlink()
    missing = await client.get(
        f"/api/jobs/source/inputs/{input_artifact['id']}", headers=LOGIN
    )
    assert missing.status == 404
    assert str(input_root) not in await missing.text()

    outside = tmp_path / "outside.png"
    Image.new("RGB", (16, 16), "white").save(outside)
    await client.app["db"].create_job(
        _record("unmanaged"),
        [{"role": "image_0", "path": outside, "size_bytes": outside.stat().st_size}],
    )
    unmanaged_artifact = next(
        item for item in await client.app["db"].list_artifacts("unmanaged")
        if item["direction"] == "input"
    )
    unmanaged = await client.get(
        f"/api/jobs/unmanaged/inputs/{unmanaged_artifact['id']}", headers=LOGIN
    )
    assert unmanaged.status == 404
    assert str(outside) not in await unmanaged.text()


@pytest.mark.asyncio
async def test_input_media_preview_rejects_invalid_artifact_id(tmp_path, aiohttp_client):
    client = await aiohttp_client(create_app(_config(tmp_path)))
    response = await client.get("/api/jobs/source/inputs/not-an-id", headers=LOGIN)
    assert response.status == 404
    assert "path" not in (await response.text()).lower()
