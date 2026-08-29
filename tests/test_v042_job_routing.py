from __future__ import annotations

import io
import json
from pathlib import Path

import pytest
from aiohttp import FormData, web
from PIL import Image

from comfyui_remote_panel.app import create_app
from comfyui_remote_panel.config import Config


ROOT = Path(__file__).resolve().parents[1]
LOGIN = {"Tailscale-User-Login": "owner@example.com"}


@pytest.fixture
async def comfy_server_v042(aiohttp_server):
    app = web.Application()
    app["submitted"] = []

    async def stats(_):
        return web.json_response({"system": {"comfyui_version": "0.30.0"}, "devices": []})

    async def queue(_):
        return web.json_response({"queue_running": [], "queue_pending": []})

    async def object_info(request):
        node = request.match_info["node"]
        return web.json_response({node: {"input": {}}})

    model_values = {
        "diffusion_models": [r"MiniMax-H3\minimax_h3_fl2va_pruned_int8_convrot.safetensors"],
        "text_encoders": [r"MiniMax-H3\qwen3vl_32b_minimax_h3_int8_convrot.safetensors"],
        "vae": ["minimax_h3_video_vae_fp16.safetensors", "minimax_h3_audio_vae_fp32.safetensors"],
        "loras": [
            "minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors",
            "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
        ],
    }

    async def models(request):
        return web.json_response(model_values.get(request.match_info["category"], []))

    async def submit(request):
        body = await request.json()
        app["submitted"].append(body)
        return web.json_response({"prompt_id": body["prompt_id"], "number": 1, "node_errors": {}})

    async def history(_):
        return web.json_response({})

    app.router.add_get("/system_stats", stats)
    app.router.add_get("/queue", queue)
    app.router.add_get("/object_info/{node}", object_info)
    app.router.add_get("/models/{category}", models)
    app.router.add_post("/prompt", submit)
    app.router.add_get("/history/{job_id}", history)
    return await aiohttp_server(app)


@pytest.fixture
async def panel_client_v042(tmp_path, comfy_server_v042, aiohttp_client):
    config = Config(
        host="127.0.0.1",
        port=8190,
        public_origin="https://device.example.ts.net",
        allowed_logins=("owner@example.com",),
        comfyui_base_url=str(comfy_server_v042.make_url("/")).rstrip("/"),
        comfyui_input_dir=tmp_path / "comfy-input",
        comfyui_output_dir=tmp_path / "comfy-output",
        minimum_comfyui_version="0.26.0",
        data_dir=tmp_path / "data",
        workflow_dir=ROOT / "workflows",
        monitoring_interval=60,
        nvidia_smi_timeout=.1,
    )
    return await aiohttp_client(create_app(config))


@pytest.mark.asyncio
async def test_virtual_fl2va_group_routes_lightx2v(panel_client_v042, comfy_server_v042):
    form = FormData(default_to_multipart=True)
    form.add_field("preset_id", "h3-fl2va-group")
    form.add_field("prompt", "测试 LightX2V")
    form.add_field("scheduler", "simple")
    form.add_field("sampler", "euler")
    form.add_field("steps", "8")
    form.add_field("values_json", json.dumps({
        "generation_mode": "lightx2v",
        "prompt_standardization": True,
    }))

    response = await panel_client_v042.post("/api/jobs", data=form, headers=LOGIN)
    assert response.status == 201, await response.text()
    job = await response.json()
    assert job["generation_mode"] == "lightx2v"
    graph = comfy_server_v042.app["submitted"][-1]["prompt"]
    assert graph["145"]["inputs"]["lora_name"] == "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"
    assert graph["124"]["inputs"]["scheduler"] == "simple"
    assert graph["149"]["inputs"]["sampler_name"] == "euler"
    assert graph["124"]["inputs"]["steps"] == 8


@pytest.mark.asyncio
async def test_disabled_generation_mode_is_rejected_by_backend(panel_client_v042, comfy_server_v042):
    status = await panel_client_v042.post(
        "/api/workflows/h3-fl2va-lightx2v/status",
        json={"status": "disabled"},
        headers=LOGIN,
    )
    assert status.status == 200

    form = FormData(default_to_multipart=True)
    form.add_field("preset_id", "h3-fl2va-group")
    form.add_field("prompt", "不应提交")
    form.add_field("values_json", json.dumps({"generation_mode": "lightx2v"}))
    response = await panel_client_v042.post("/api/jobs", data=form, headers=LOGIN)

    assert response.status == 400
    assert "已禁用" in (await response.json())["error"]["message"]
    assert not comfy_server_v042.app["submitted"]


@pytest.mark.asyncio
async def test_group_keeps_reference_image_resolution_override(panel_client_v042):
    image_data = io.BytesIO()
    Image.new("RGB", (2000, 1000), "red").save(image_data, format="PNG")
    form = FormData(default_to_multipart=True)
    form.add_field("preset_id", "h3-fl2va-group")
    form.add_field("prompt", "")
    form.add_field("first_frame", image_data.getvalue(), filename="first.png", content_type="image/png")
    form.add_field("values_json", json.dumps({
        "generation_mode": "v4_600step",
        "prompt_standardization": False,
        "media_resolution": {
            "first": {"policy": "auto", "target_megapixels": 0.5},
            "last": {"policy": "auto", "target_megapixels": 0.5},
        },
    }))

    response = await panel_client_v042.post("/api/jobs", data=form, headers=LOGIN)
    assert response.status == 201, await response.text()
    job = await response.json()
    stored = await panel_client_v042.app["db"].get_job(job["id"])
    first = next(item for item in stored["files"] if item["role"] == "first")
    with Image.open(first["path"]) as image:
        assert image.width * image.height <= 500_000
        assert image.width / image.height == pytest.approx(2.0, rel=0.01)
