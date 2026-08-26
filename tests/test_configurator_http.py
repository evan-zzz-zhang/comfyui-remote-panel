from __future__ import annotations

import io
import json

import pytest
from aiohttp import FormData
from PIL import Image
from unittest.mock import AsyncMock

from test_app import LOGIN, comfy_server, panel_client
from test_workflow_analysis import object_info, wai_img2img_workflow


@pytest.mark.asyncio
async def test_wai_img2img_inspect_save_enable_submit_and_artifact(panel_client, comfy_server):
    workflow = wai_img2img_workflow()
    schemas = object_info()
    panel_client.app["comfy"].object_info = AsyncMock(side_effect=lambda node_type: schemas[node_type])

    inspected_response = await panel_client.post(
        "/api/workflows/inspect",
        data=json.dumps(workflow).encode("utf-8"),
        headers={**LOGIN, "Content-Type": "application/json"},
    )
    assert inspected_response.status == 200, await inspected_response.text()
    inspected = await inspected_response.json()

    assert inspected["capabilities"]["generation_mode"] == "img2img"
    assert inspected["capabilities"]["size_strategy"] == "inherit_input"
    assert inspected["capabilities"]["batch_strategy"] == "workflow_fixed"
    assert inspected["preflight"]["nodes"]["status"] == "PASS"
    assert inspected["preflight"]["outputs"]["status"] == "PASS"

    params = {item["semantic"]: item for item in inspected["parameters"]}
    for semantic in (
        "positive_prompt", "negative_prompt", "seed", "steps", "cfg",
        "sampler", "scheduler", "denoise", "checkpoint",
    ):
        assert semantic in params
    assert "width" not in params
    assert "height" not in params
    assert "batch_size" not in params

    source = next(item for item in inspected["media_inputs"] if item["semantic"] == "source_image")
    assert source["required"] is True
    output = inspected["outputs"][0]
    config = {
        "id": "wai-img2img-http",
        "name": "WAI Img2Img HTTP",
        "parameters": [item for item in inspected["parameters"] if item["confidence"] != "LOW"],
        "media": {
            "type": "slots",
            "slots": {
                source["id"]: {
                    "node": source["node"],
                    "input": source["input"],
                    "kind": source["kind"],
                    "required": True,
                    "semantic": source["semantic"],
                    "confidence": source["confidence"],
                    "ui": {
                        "label": source["label"],
                        "optional": False,
                        "semantic": source["semantic"],
                        "confidence": source["confidence"],
                    },
                }
            },
        },
        "outputs": [{
            "id": "primary", "node": output["node"], "kind": output["kind"],
            "history_keys": ["images"], "primary": True,
        }],
        "analysis": {
            "capabilities": inspected["capabilities"],
            "confidence": inspected["confidence"],
            "preflight": inspected["preflight"],
        },
    }

    created = await panel_client.post(
        "/api/workflows",
        json={"workflow": workflow, "config": config},
        headers=LOGIN,
    )
    assert created.status == 201, await created.text()

    enabled = await panel_client.post(
        "/api/workflows/wai-img2img-http/status",
        json={"status": "enabled"},
        headers=LOGIN,
    )
    assert enabled.status == 200, await enabled.text()

    presets = await panel_client.get("/api/presets", headers=LOGIN)
    saved = next(item for item in (await presets.json())["items"] if item["id"] == "wai-img2img-http")
    assert saved["capability_profile"]["size_strategy"] == "inherit_input"
    assert saved["capability_profile"]["batch_strategy"] == "workflow_fixed"

    missing = FormData(default_to_multipart=True)
    missing.add_field("preset_id", "wai-img2img-http")
    missing.add_field("values_json", json.dumps({"positive_prompt": "new portrait"}))
    before = len(comfy_server.app["submitted"])
    missing_response = await panel_client.post("/api/jobs", data=missing, headers=LOGIN)
    assert missing_response.status == 400
    assert "缺少必需素材" in (await missing_response.json())["error"]["message"]
    assert len(comfy_server.app["submitted"]) == before

    image_data = io.BytesIO()
    Image.new("RGB", (32, 24), "blue").save(image_data, format="PNG")
    form = FormData(default_to_multipart=True)
    form.add_field("preset_id", "wai-img2img-http")
    form.add_field(
        "values_json",
        json.dumps({
            "positive_prompt": "new portrait",
            "negative_prompt": "bad hands",
            "steps": 17,
            "cfg": 5.2,
            "sampler": "dpmpp_2m",
            "scheduler": "karras",
            "denoise": 0.55,
            "checkpoint": "other.safetensors",
        }),
    )
    form.add_field(source["id"], image_data.getvalue(), filename="source.png", content_type="image/png")
    response = await panel_client.post("/api/jobs", data=form, headers=LOGIN)
    assert response.status == 201, await response.text()
    job = await response.json()
    graph = comfy_server.app["submitted"][-1]["prompt"]

    assert graph["2"]["inputs"]["text"] == "new portrait"
    assert graph["3"]["inputs"]["text"] == "bad hands"
    assert graph["6"]["inputs"]["steps"] == 17
    assert graph["6"]["inputs"]["cfg"] == 5.2
    assert graph["6"]["inputs"]["sampler_name"] == "dpmpp_2m"
    assert graph["6"]["inputs"]["scheduler"] == "karras"
    assert graph["6"]["inputs"]["denoise"] == 0.55
    assert graph["1"]["inputs"]["ckpt_name"] == "other.safetensors"
    assert graph["4"]["inputs"]["image"] != "source.png"
    assert "width" not in graph["4"]["inputs"] and "height" not in graph["4"]["inputs"]

    output_name = f"{panel_client.app['files'].storage_key(job['id'])}_00001_.png"
    output_path = panel_client.app["files"].output_root / output_name
    output_path.write_bytes(b"wai-png-result")
    captured = await panel_client.app["jobs"]._capture_output(job["id"], {
        "outputs": {"8": {"images": [{"filename": output_name, "subfolder": "h3_remote", "type": "output"}]}}
    })
    assert captured is True

    artifacts_response = await panel_client.get(f"/api/jobs/{job['id']}/artifacts", headers=LOGIN)
    assert artifacts_response.status == 200
    [artifact] = (await artifacts_response.json())["items"]
    assert artifact["kind"] == "image"
    download = await panel_client.get(f"/api/jobs/{job['id']}/artifacts/{artifact['id']}?download=1", headers=LOGIN)
    assert download.status == 200
    assert await download.read() == b"wai-png-result"
