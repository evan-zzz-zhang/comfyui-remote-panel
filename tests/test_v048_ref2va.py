from pathlib import Path
import io
import json

import pytest
from aiohttp import FormData, web
from PIL import Image

from comfyui_remote_panel.app import create_app
from comfyui_remote_panel.config import Config
from comfyui_remote_panel.inference_profile import resolve_inference_profile
from comfyui_remote_panel.preset import load_presets
from comfyui_remote_panel.workflow_registry import (
    CANONICAL_REF2VA_ASSET_IDS,
    WorkflowAssetKey,
    ref2va_asset_key,
    resolve_ref2va_asset,
)
from comfyui_remote_panel.v048_ref2va import _canonical_key


ROOT = Path(__file__).resolve().parents[1]
LOGIN = {"Tailscale-User-Login": "owner@example.com"}


@pytest.fixture
async def comfy_server_v048(aiohttp_server):
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
        "diffusion_models": [
            r"MiniMax-H3\minimax_h3_ref2va_pruned_int8_convrot.safetensors",
            r"MiniMax-H3\minimax_h3_ref2va_pruned_bf16.safetensors",
        ],
        "text_encoders": [
            r"MiniMax-H3\qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
            "qwen3.5_4b_bf16.safetensors",
        ],
        "vae": ["minimax_h3_video_vae_fp16.safetensors", "minimax_h3_audio_vae_fp32.safetensors"],
        "loras": [
            "minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors",
            "minimax_h3_ref2v_turbo_4step_v0.1_comfyui_bf16.safetensors",
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
async def panel_client_v048(tmp_path, comfy_server_v048, aiohttp_client):
    config = Config(
        host="127.0.0.1",
        port=8190,
        public_origin="https://device.example.ts.net",
        allowed_logins=("owner@example.com",),
        comfyui_base_url=str(comfy_server_v048.make_url("/")).rstrip("/"),
        comfyui_input_dir=tmp_path / "comfy-input",
        comfyui_output_dir=tmp_path / "comfy-output",
        minimum_comfyui_version="0.26.0",
        data_dir=tmp_path / "data",
        workflow_dir=ROOT / "workflows",
        monitoring_interval=60,
        nvidia_smi_timeout=.1,
    )
    return await aiohttp_client(create_app(config))


def values(**overrides):
    return {
        "prompt": "镜头缓慢推进，参考素材中的主体保持连贯运动",
        "duration_seconds": 5,
        "aspect_ratio": "9:16",
        "megapixels": 0.4,
        "seed": 42,
        **overrides,
    }


def test_ref2va_registry_resolves_all_nine_assets():
    presets = load_presets(ROOT / "workflows")
    assert {preset.id for preset in presets.values() if preset.manifest.get("family") == "ref2va" and preset.manifest.get("asset_role") == "canonical"} == set(CANONICAL_REF2VA_ASSET_IDS)
    for mode in ("original", "lightx2v", "v4step600"):
        for backend in ("raw", "ollama", "qwen35"):
            assert resolve_ref2va_asset(
                presets, family="ref2va", generation_mode=mode, prompt_backend=backend
            ).id == f"ref2va_{mode}_{backend}"


def test_ref2va_generation_modes_keep_their_legacy_sampling_contract():
    presets = load_presets(ROOT / "workflows")
    expected = {
        "original": ("simple", "res_multistep", 20),
        "lightx2v": ("simple", "euler", 4),
        "v4step600": ("beta", "euler", 8),
    }
    for mode, sampling in expected.items():
        normalized = presets[f"ref2va_{mode}_raw"].validate_parameters(values())
        assert (normalized["scheduler"], normalized["sampler"], normalized["steps"]) == sampling


def test_ref2va_collection_media_is_preserved_for_prompt_backends():
    presets = load_presets(ROOT / "workflows")
    media = {"image_0": "image.png", "image_1": "image2.png", "video_0": "clip.mp4", "audio_0": "voice.wav"}
    for backend in ("raw", "ollama", "qwen35"):
        graph = presets[f"ref2va_original_{backend}"].build_prompt(values(), "job", media)
        target = graph["136"]["inputs"]
        assert target["ref_images.ref_image_0"] == ["9100", 0]
        assert target["ref_images.ref_image_1"] == ["9101", 0]
        assert target["ref_videos.ref_video_0"] == ["9300", 0]
        assert target["ref_video_audios.ref_video_audio_0"] == ["9300", 1]
        assert target["ref_audios.ref_audio_0"] == ["9400", 0]


def test_ref2va_representative_visual_prefers_image_then_video_first_frame():
    presets = load_presets(ROOT / "workflows")
    image = presets["ref2va_original_ollama"].build_prompt(values(), "image", {"image_0": "image.png", "video_0": "clip.mp4"})
    assert image["152"]["inputs"]["first_frame"] == ["9100", 0]
    assert "last_frame" not in image["152"]["inputs"]

    video = presets["ref2va_original_ollama"].build_prompt(values(), "video", {"video_0": "clip.mp4"})
    assert video["152"]["inputs"]["first_frame"] == ["9500", 0]
    assert video["9500"] == {"class_type": "ImageFromBatch", "inputs": {"images": ["9300", 0], "batch_index": 0, "length": 1}}

    text = presets["ref2va_original_ollama"].build_prompt(values(), "text", {})
    assert "first_frame" not in text["152"]["inputs"]


def test_ref2va_qwen_keeps_h3_encoder_separate_and_captures_metadata():
    preset = load_presets(ROOT / "workflows")["ref2va_v4step600_qwen35"]
    graph = preset.build_prompt(values(scheduler="beta", sampler="euler", steps=8), "qwen", {})
    assert graph["128"]["inputs"]["clip_name"].endswith("qwen3vl_32b_minimax_h3_int8_convrot.safetensors")
    assert graph["168"]["inputs"]["clip_name"] == "qwen3.5_4b_bf16.safetensors"
    assert graph["136"]["inputs"]["prompt"] == ["176", 0]
    assert graph["92"]["class_type"] == "H3SaveVideoWithPromptMetadata"
    assert graph["92"]["inputs"]["run_metadata"] == ["183", 0]


def test_ref2va_profile_supports_auto_int8_and_bf16_variant():
    preset = load_presets(ROOT / "workflows")["ref2va_original_raw"]
    assert resolve_inference_profile(preset, "auto") == ("auto", "int8")
    assert resolve_inference_profile(preset, "int8") == ("int8", "int8")
    assert resolve_inference_profile(preset, "fp16_bf16") == ("fp16_bf16", "fp16_bf16")


@pytest.mark.parametrize("requested, effective", [("auto", "int8"), ("int8", "int8")])
def test_ref2va_final_graph_keeps_int8_selector_for_auto_and_int8(requested, effective):
    preset = load_presets(ROOT / "workflows")["ref2va_original_raw"]
    values_for_graph = values(
        _v048_effective_inference_profile=effective,
        _v048_variant_model_overrides={},
    )
    graph = preset.build_prompt(values_for_graph, f"{requested}-job", {})
    assert graph["127"]["inputs"]["unet_name"] == preset.template["127"]["inputs"]["unet_name"]


def test_ref2va_final_graph_uses_exact_runtime_bf16_selector_and_preserves_fixed_nodes():
    preset = load_presets(ROOT / "workflows")["ref2va_v4step600_raw"]
    runtime_selector = r"MiniMax-H3\minimax_h3_ref2va_pruned_bf16.safetensors"
    graph = preset.build_prompt(
        values(
            _v048_effective_inference_profile="fp16_bf16",
        ),
        "bf16-job",
        {},
        {"127": {"unet_name": runtime_selector}},
    )
    assert graph["127"]["inputs"]["unet_name"] == runtime_selector
    for node_id in ("128", "119", "120", "145", "147"):
        assert graph[node_id]["inputs"] == preset.template[node_id]["inputs"]


def test_ref2va_manifests_keep_exact_uint64_seed_maximum():
    expected = '"maximum": 18446744073709551615'
    for manifest_path in (ROOT / "src/comfyui_remote_panel/workflows/ref2va").rglob("manifest.json"):
        text = manifest_path.read_text(encoding="utf-8")
        assert expected in text
        assert "18446744073709552000" not in text


@pytest.mark.asyncio
async def test_full_runtime_stack_persists_virtual_ref2va_routing_and_builds_bf16_graph(
    panel_client_v048, comfy_server_v048
):
    form = FormData(default_to_multipart=True)
    form.add_field("preset_id", "h3-ref2va-group")
    form.add_field("values_json", json.dumps({
        "generation_mode": "original",
        "prompt_backend": "raw",
        "inference_profile": "fp16_bf16",
    }))
    form.add_field("prompt", "运行时 Ref2VA")
    response = await panel_client_v048.post("/api/jobs", data=form, headers=LOGIN)
    assert response.status == 201, await response.text()
    created = await response.json()
    stored = await panel_client_v048.app["db"].get_job(created["id"])
    values_json = stored["input_values"]
    assert stored["preset_id"] == "ref2va_original_raw"
    assert values_json["_v048_generation_mode"] == "original"
    assert values_json["_v048_prompt_backend"] == "raw"
    assert values_json["_v048_inference_profile"] == "fp16_bf16"
    assert values_json["_v048_effective_inference_profile"] == "fp16_bf16"
    assert values_json["_v048_variant_model_overrides"] == {
        "127": {"unet_name": r"MiniMax-H3\minimax_h3_ref2va_pruned_bf16.safetensors"}
    }
    graph = comfy_server_v048.app["submitted"][-1]["prompt"]
    assert graph["127"]["inputs"]["unet_name"] == r"MiniMax-H3\minimax_h3_ref2va_pruned_bf16.safetensors"
    public = panel_client_v048.app["jobs"].public_job(stored)
    assert public["generation_mode"] == "original"
    assert public["prompt_backend"] == "raw"
    assert public["inference_profile"] == "fp16_bf16"
    assert public["effective_inference_profile"] == "fp16_bf16"
    assert all(not key.startswith("_v048") for key in public["input_values"])


@pytest.mark.asyncio
async def test_direct_canonical_ref2va_create_has_no_key_contract_attribute_error(panel_client_v048):
    form = FormData(default_to_multipart=True)
    form.add_field("preset_id", "ref2va_original_raw")
    form.add_field("prompt", "direct canonical")
    response = await panel_client_v048.post("/api/jobs", data=form, headers=LOGIN)
    assert response.status == 201, await response.text()
    job = await response.json()
    assert job["generation_mode"] == "original"
    assert _canonical_key(panel_client_v048.app["presets"]["ref2va_original_raw"]) == WorkflowAssetKey(
        "ref2va", "original", "raw"
    )


@pytest.mark.asyncio
async def test_new_canonical_ref2va_retry_restores_virtual_routing_and_media(
    panel_client_v048, comfy_server_v048
):
    image_data = io.BytesIO()
    Image.new("RGB", (24, 12), "purple").save(image_data, format="PNG")
    form = FormData(default_to_multipart=True)
    form.add_field("preset_id", "h3-ref2va-group")
    form.add_field("values_json", json.dumps({
        "generation_mode": "lightx2v",
        "prompt_backend": "raw",
        "inference_profile": "int8",
    }))
    form.add_field("prompt", "retry canonical")
    form.add_field("ref_images", image_data.getvalue(), filename="reference.png", content_type="image/png")
    response = await panel_client_v048.post("/api/jobs", data=form, headers=LOGIN)
    assert response.status == 201, await response.text()
    created = await response.json()
    await panel_client_v048.app["db"].update_job(created["id"], status="failed")

    retry_response = await panel_client_v048.post(f"/api/jobs/{created['id']}/retry", headers=LOGIN)
    assert retry_response.status == 200, await retry_response.text()
    draft = await retry_response.json()
    assert draft["preset_id"] == "h3-ref2va-group"
    assert draft["generation_mode"] == "lightx2v"
    assert draft["prompt_backend"] == "raw"
    assert draft["inference_profile"] == "int8"
    assert draft["retained_media"]
    assert draft["retained_media"][0]["role"] == "image_0"


@pytest.mark.asyncio
@pytest.mark.parametrize("preset_id", ["h3-ref2va-v4step600", "ref2va_v4step600_raw"])
async def test_ref2va_v4step600_retry_exposes_public_mode_contract(
    panel_client_v048, preset_id
):
    image_data = io.BytesIO()
    Image.new("RGB", (24, 12), "orange").save(image_data, format="PNG")
    form = FormData(default_to_multipart=True)
    form.add_field("preset_id", preset_id)
    form.add_field("prompt", "v4step600 retry")
    form.add_field(
        "ref_images", image_data.getvalue(), filename="reference.png", content_type="image/png"
    )
    response = await panel_client_v048.post("/api/jobs", data=form, headers=LOGIN)
    assert response.status == 201, await response.text()
    created = await response.json()
    await panel_client_v048.app["db"].update_job(created["id"], status="failed")

    retry_response = await panel_client_v048.post(
        f"/api/jobs/{created['id']}/retry", headers=LOGIN
    )
    assert retry_response.status == 200, await retry_response.text()
    draft = await retry_response.json()
    assert draft["preset_id"] == "h3-ref2va-group"
    assert draft["generation_mode"] == "v4step600"
