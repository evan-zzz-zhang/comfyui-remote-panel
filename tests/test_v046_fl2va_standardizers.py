from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from aiohttp import FormData, web

from comfyui_remote_panel.app import create_app
from comfyui_remote_panel.config import Config
from comfyui_remote_panel.preset import load_presets


ROOT = Path(__file__).resolve().parents[1]
LOGIN = {"Tailscale-User-Login": "owner@example.com"}

OLD_PRESETS = {
    "original": "h3-fl2va",
    "lightx2v": "h3-fl2va-lightx2v",
    "v4_600step": "h3-fl2va-v4step600",
}
QWEN_PRESETS = {
    "original": "h3-fl2va-qwen35-4b",
    "lightx2v": "h3-fl2va-lightx2v-qwen35-4b",
    "v4_600step": "h3-fl2va-v4step600-qwen35-4b",
}


@pytest.fixture
async def comfy_server_v046(aiohttp_server):
    app = web.Application()
    app["submitted"] = []
    app["history"] = {}

    async def stats(_):
        return web.json_response({"system": {"comfyui_version": "0.30.0"}, "devices": []})

    async def queue(_):
        return web.json_response({"queue_running": [], "queue_pending": []})

    async def object_info(request):
        node = request.match_info["node"]
        return web.json_response({node: {"input": {}}})

    model_values = {
        "diffusion_models": [r"MiniMax-H3\minimax_h3_fl2va_pruned_int8_convrot.safetensors"],
        "text_encoders": [
            r"MiniMax-H3\qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
            "qwen3.5_4b_bf16.safetensors",
        ],
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

    async def history(request):
        job_id = request.match_info["job_id"]
        entry = app["history"].get(job_id)
        return web.json_response({job_id: entry} if entry is not None else {})

    async def cancel(_):
        return web.json_response({"cancelled": False})

    app.router.add_get("/system_stats", stats)
    app.router.add_get("/queue", queue)
    app.router.add_get("/object_info/{node}", object_info)
    app.router.add_get("/models/{category}", models)
    app.router.add_post("/prompt", submit)
    app.router.add_get("/history/{job_id}", history)
    app.router.add_post("/api/jobs/{job_id}/cancel", cancel)
    return await aiohttp_server(app)


@pytest.fixture
async def panel_client_v046(tmp_path, comfy_server_v046, aiohttp_client):
    config = Config(
        host="127.0.0.1",
        port=8190,
        public_origin="https://device.example.ts.net",
        allowed_logins=("owner@example.com",),
        comfyui_base_url=str(comfy_server_v046.make_url("/")).rstrip("/"),
        comfyui_input_dir=tmp_path / "comfy-input",
        comfyui_output_dir=tmp_path / "comfy-output",
        minimum_comfyui_version="0.26.0",
        data_dir=tmp_path / "data",
        workflow_dir=ROOT / "workflows",
        monitoring_interval=60,
        nvidia_smi_timeout=.1,
    )
    return await aiohttp_client(create_app(config))


def _form(
    mode: str,
    standardization: str,
    *,
    ollama_model: str = "gemma4:e4b",
    inference_profile: str = "auto",
    preset_id: str = "h3-fl2va-group",
) -> FormData:
    form = FormData(default_to_multipart=True)
    form.add_field("preset_id", preset_id)
    form.add_field("prompt", f"测试 {mode} {standardization}")
    form.add_field("values_json", json.dumps({
        "generation_mode": mode,
        "prompt_standardization_mode": standardization,
        "ollama_model": ollama_model,
        "inference_profile": inference_profile,
    }))
    return form


@pytest.mark.asyncio
async def test_fl2va_creation_and_management_apis_keep_physical_assets_separate(
    panel_client_v046,
):
    presets_response = await panel_client_v046.get("/api/presets", headers=LOGIN)
    assert presets_response.status == 200
    public_presets = (await presets_response.json())["items"]
    assert not any(item.get("family") == "fl2va" for item in public_presets)

    workflows_response = await panel_client_v046.get("/api/workflows", headers=LOGIN)
    assert workflows_response.status == 200
    workflows = (await workflows_response.json())["items"]
    physical_ids = {
        "fl2va_original_raw", "fl2va_original_ollama", "fl2va_original_qwen35",
        "fl2va_v4step600_raw", "fl2va_v4step600_ollama", "fl2va_v4step600_qwen35",
        "fl2va_lightx2v_raw", "fl2va_lightx2v_ollama", "fl2va_lightx2v_qwen35",
    }
    by_id = {item["id"]: item for item in workflows}
    assert physical_ids <= by_id.keys()
    assert all(by_id[item_id]["status"] == "enabled" for item_id in physical_ids)
    assert all(by_id[item_id]["manifest"]["family"] == "fl2va" for item_id in physical_ids)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["original", "lightx2v", "v4_600step"])
@pytest.mark.parametrize("standardization", ["off", "ollama", "comfyui"])
async def test_all_nine_fl2va_routes_select_the_expected_physical_workflow(
    panel_client_v046, comfy_server_v046, mode, standardization
):
    response = await panel_client_v046.post(
        "/api/jobs",
        data=_form(mode, standardization, ollama_model="qwen3:8b"),
        headers=LOGIN,
    )
    assert response.status == 201, await response.text()
    job = await response.json()
    expected_preset = (
        f"fl2va_{'v4step600' if mode == 'v4_600step' else mode}_qwen35"
        if standardization == "comfyui"
        else f"fl2va_{'v4step600' if mode == 'v4_600step' else mode}_{'raw' if standardization == 'off' else 'ollama'}"
    )
    assert job["preset_id"] == expected_preset
    assert job["generation_mode"] == mode
    expected_mode = "off" if standardization == "off" else "qwen35" if standardization == "comfyui" else "ollama"
    assert job["prompt_standardization_mode"] == expected_mode
    assert job["inference_profile"] == "auto"
    assert job["effective_inference_profile"] == "int8"
    assert "inference_profile" not in job["input_values"]

    graph = comfy_server_v046.app["submitted"][-1]["prompt"]
    classes = {node["class_type"] for node in graph.values()}
    if standardization == "comfyui":
        assert "H3OfficialSkillPromptWriterQwen" in classes
        assert "H3PromptStandardizer" not in classes
        assert graph["168"]["inputs"]["clip_name"] == "qwen3.5_4b_bf16.safetensors"
        assert graph["176"]["inputs"]["enable_standardization"] is True
        assert graph["92"]["class_type"] == "H3SaveVideoWithPromptMetadata"
        assert graph["174"]["class_type"] == "H3OptionalLoadImageV4"
        assert graph["175"]["class_type"] == "H3OptionalLoadImageV4"
        assert "ollama_model" not in job["input_values"]
    else:
        standardizer = "124" if mode == "original" else "152"
        switch = "126" if mode == "original" else "154"
        if standardization == "off":
            assert "H3PromptStandardizer" not in classes
            return
        assert "H3PromptStandardizer" in classes
        assert graph[switch]["inputs"]["switch"] is (standardization == "ollama")
        if standardization == "ollama":
            assert graph[standardizer]["inputs"]["ollama_model"] == "qwen3:8b"


@pytest.mark.asyncio
@pytest.mark.parametrize("preset_id", [
    "fl2va_original_raw",
    "h3-fl2va-qwen35-4b",
])
async def test_physical_and_legacy_qwen_routes_strip_inference_profile_before_validation(
    panel_client_v046, comfy_server_v046, preset_id
):
    response = await panel_client_v046.post(
        "/api/jobs",
        data=_form("original", "off", preset_id=preset_id, inference_profile="int8"),
        headers=LOGIN,
    )
    assert response.status == 201, await response.text()
    job = await response.json()
    assert job["inference_profile"] == "int8"
    assert job["effective_inference_profile"] == "int8"
    assert "inference_profile" not in job["input_values"]


@pytest.mark.asyncio
async def test_unavailable_inference_profile_is_reported_as_model_error_not_unknown_field(
    panel_client_v046,
):
    response = await panel_client_v046.post(
        "/api/jobs",
        data=_form("original", "off", inference_profile="fp16_bf16"),
        headers=LOGIN,
    )
    assert response.status == 400
    message = (await response.json())["error"]["message"]
    assert "模型配置 fp16_bf16 当前不可用" in message
    assert "不支持的字段：inference_profile" not in message


@pytest.mark.asyncio
async def test_top_level_inference_profile_remains_rejected_by_multipart_whitelist(
    panel_client_v046,
):
    form = _form("original", "off")
    form.add_field("inference_profile", "int8")
    response = await panel_client_v046.post("/api/jobs", data=form, headers=LOGIN)
    assert response.status == 400
    assert "不支持的字段：inference_profile" in (await response.json())["error"]["message"]


@pytest.mark.asyncio
async def test_qwen_standardized_prompt_uses_existing_public_field(
    panel_client_v046, comfy_server_v046
):
    response = await panel_client_v046.post(
        "/api/jobs", data=_form("v4_600step", "comfyui"), headers=LOGIN
    )
    assert response.status == 201, await response.text()
    created = await response.json()
    job_id = created["id"]

    comfy_server_v046.app["history"][job_id] = {
        "status": {"completed": True, "status_str": "success", "messages": []},
        "outputs": {
            "92": {
                "videos": [],
                "metadata": {"standardized_prompt": "Qwen3.5 标准化后的 H3 Prompt"},
            }
        },
    }
    await panel_client_v046.app["jobs"].reconcile_once()

    stored = await panel_client_v046.app["db"].get_job(job_id)
    public = panel_client_v046.app["jobs"].public_job(stored)
    assert public["prompt"].startswith("测试 v4_600step")
    assert public["standardized_prompt"] == "Qwen3.5 标准化后的 H3 Prompt"
    assert public["prompt_standardization_mode"] == "qwen35"


@pytest.mark.asyncio
async def test_qwen_prompt_recovery_backfills_delayed_preview_history(
    panel_client_v046, comfy_server_v046
):
    response = await panel_client_v046.post(
        "/api/jobs", data=_form("original", "comfyui"), headers=LOGIN
    )
    assert response.status == 201, await response.text()
    created = await response.json()
    job_id = created["id"]
    await panel_client_v046.app["db"].update_job(job_id, status="succeeded")
    output = panel_client_v046.app["files"].output_root / f"{job_id}.mp4"
    output.write_bytes(b"placeholder")
    await panel_client_v046.app["db"].add_file(job_id, "output", output, output.stat().st_size)
    comfy_server_v046.app["history"][job_id] = {
        "status": {"completed": True, "status_str": "success", "messages": []},
        "outputs": {"177": {"text": ["延迟写入的 Qwen3.5 Prompt"]}},
    }

    panel_client_v046.app["jobs"]._last_standardized_prompt_recovery = 0
    await panel_client_v046.app["jobs"]._recover_standardized_prompts_v046()

    stored = await panel_client_v046.app["db"].get_job(job_id)
    public = panel_client_v046.app["jobs"].public_job(stored)
    assert public["standardized_prompt"] == "延迟写入的 Qwen3.5 Prompt"
    assert public["prompt_backend"] == "qwen35"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("standardization", "expected"),
    [("off", "off"), ("ollama", "ollama"), ("comfyui", "comfyui")],
)
async def test_retry_restores_standardization_backend(
    panel_client_v046, standardization, expected
):
    response = await panel_client_v046.post(
        "/api/jobs", data=_form("lightx2v", standardization), headers=LOGIN
    )
    assert response.status == 201, await response.text()
    created = await response.json()
    await panel_client_v046.app["db"].update_job(created["id"], status="succeeded")

    draft = await panel_client_v046.app["jobs"].retry(created["id"])
    assert draft["preset_id"] == "h3-fl2va-group"
    assert draft["generation_mode"] == "lightx2v"
    assert draft["prompt_standardization_mode"] == expected
    assert draft["values"]["prompt_standardization_mode"] == expected


@pytest.mark.asyncio
async def test_retry_restores_inference_profile_and_can_submit_again(
    panel_client_v046, comfy_server_v046
):
    response = await panel_client_v046.post(
        "/api/jobs",
        data=_form("lightx2v", "off", inference_profile="int8"),
        headers=LOGIN,
    )
    assert response.status == 201, await response.text()
    created = await response.json()
    await panel_client_v046.app["db"].update_job(created["id"], status="succeeded")

    draft = await panel_client_v046.app["jobs"].retry(created["id"])
    assert draft["inference_profile"] == "int8"
    assert draft["values"]["inference_profile"] == "int8"

    retry_form = _form(
        draft["generation_mode"],
        draft["prompt_standardization_mode"],
        inference_profile=draft["inference_profile"],
    )
    retry_form.add_field("retry_source_id", draft["retry_source_id"])
    retry_form.add_field("retry_keep_roles", json.dumps(draft["retry_keep_roles"]))
    retried = await panel_client_v046.post("/api/jobs", data=retry_form, headers=LOGIN)
    assert retried.status == 201, await retried.text()
    retried_job = await retried.json()
    assert retried_job["inference_profile"] == "int8"
    assert "inference_profile" not in retried_job["input_values"]


@pytest.mark.asyncio
async def test_qwen_prompt_recovery_is_bounded_to_three_attempts(
    panel_client_v046, comfy_server_v046
):
    response = await panel_client_v046.post(
        "/api/jobs", data=_form("original", "comfyui"), headers=LOGIN
    )
    assert response.status == 201, await response.text()
    created = await response.json()
    await panel_client_v046.app["db"].update_job(created["id"], status="succeeded")
    output = panel_client_v046.app["files"].output_root / f"{created['id']}.mp4"
    output.write_bytes(b"placeholder")
    await panel_client_v046.app["db"].add_file(created["id"], "output", output, output.stat().st_size)

    history = AsyncMock(return_value={})
    panel_client_v046.app["comfy"].history = history
    jobs = panel_client_v046.app["jobs"]
    for _ in range(4):
        jobs._last_standardized_prompt_recovery = 0
        await jobs._recover_standardized_prompts_v046()

    assert history.await_count == 3


@pytest.mark.asyncio
async def test_disabling_qwen_route_does_not_disable_same_generation_mode_off_route(
    panel_client_v046, comfy_server_v046
):
    status = await panel_client_v046.post(
        "/api/workflows/fl2va_lightx2v_qwen35/status",
        json={"status": "disabled"},
        headers=LOGIN,
    )
    assert status.status == 200

    blocked = await panel_client_v046.post(
        "/api/jobs", data=_form("lightx2v", "comfyui"), headers=LOGIN
    )
    assert blocked.status == 400
    assert "Qwen3.5 标准化" in (await blocked.json())["error"]["message"]

    allowed = await panel_client_v046.post(
        "/api/jobs", data=_form("lightx2v", "off"), headers=LOGIN
    )
    assert allowed.status == 201, await allowed.text()
    assert (await allowed.json())["preset_id"] == "fl2va_lightx2v_raw"
    assert len(comfy_server_v046.app["submitted"]) == 1


def test_qwen_bundled_manifests_keep_generation_tuning_and_qwen_dependency():
    presets = load_presets()
    expected = {
        "h3-fl2va-qwen35-4b": ("simple", "res_multistep", 20, None),
        "h3-fl2va-lightx2v-qwen35-4b": ("simple", "euler", 8, "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors"),
        "h3-fl2va-v4step600-qwen35-4b": ("beta", "euler", 8, "minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors"),
    }
    for preset_id, (scheduler, sampler, steps, lora) in expected.items():
        preset = presets[preset_id]
        assert preset.manifest["parameters"]["scheduler"]["default"] == scheduler
        assert preset.manifest["parameters"]["sampler"]["default"] == sampler
        assert preset.manifest["parameters"]["steps"]["default"] == steps
        assert preset.manifest["prompt_standardizer"] == {
            "backend": "comfyui",
            "model": "qwen3.5-4b",
            "node": "176",
            "history_node": "92",
            "history_field": "standardized_prompt",
        }
        assert preset.manifest["workflow_variant"] == "qwen35-v4.4"
        assert any(
            item["category"] == "text_encoders"
            and item["name"] == "qwen3.5_4b_bf16.safetensors"
            for item in preset.manifest["dependencies"]
        )
        lora_nodes = [
            node for node in preset.template.values() if node["class_type"] == "LoraLoader"
        ]
        if lora is None:
            assert not lora_nodes
        else:
            assert lora_nodes[0]["inputs"]["lora_name"] == lora
