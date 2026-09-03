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
from comfyui_remote_panel.v048_ref2va import _canonical_key, _virtual_metadata


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


def test_ref2va_virtual_entry_defaults_and_labels_match_v4step600_contract():
    metadata = _virtual_metadata(load_presets(ROOT / "workflows"))
    assert metadata is not None
    assert metadata["name"] == "MiniMax H3 Ref2VA"
    assert metadata["generation_modes"]["default"] == "v4step600"
    assert metadata["generation_modes"]["values"]["original"]["label"] == "原版"
    assert metadata["generation_modes"]["values"]["v4step600"]["label"] == "v4_600step"
    assert metadata["prompt_backends"]["values"] == {
        "raw": {"label": "原始提示词"},
        "ollama": {"label": "Ollama 标准化"},
        "qwen35": {"label": "Qwen3.5 标准化"},
    }
    assert metadata["inference_profiles"] == ["int8", "fp16_bf16"]
    assert metadata["parameters"]["scheduler"]["default"] == "beta"
    assert metadata["parameters"]["sampler"]["default"] == "euler"
    assert metadata["parameters"]["steps"]["default"] == 8


@pytest.mark.asyncio
async def test_virtual_preset_api_exposes_consistent_fl2va_and_ref2va_names(panel_client_v048):
    response = await panel_client_v048.get("/api/presets", headers=LOGIN)
    assert response.status == 200
    items = {item["id"]: item for item in (await response.json())["items"]}
    assert items["h3-fl2va-group"]["name"] == "MiniMax H3 FL2VA"
    assert items["h3-ref2va-group"]["name"] == "MiniMax H3 Ref2VA"


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


@pytest.mark.parametrize("mode", ["original", "lightx2v", "v4step600"])
def test_ref2va_ollama_uses_native_reference_conditioning_contract(mode):
    preset = load_presets(ROOT / "workflows")[f"ref2va_{mode}_ollama"]
    graph = preset.build_prompt(values(), f"{mode}-ollama", {"image_0": "image.png"})
    assert graph["136"]["class_type"] == "H3Ref2VAOllamaConditioning"
    assert graph["136"]["inputs"]["ollama_model"] == "gemma4:e4b"
    assert graph["136"]["inputs"]["ref_images.ref_image_0"] == ["9100", 0]
    assert graph["136"]["inputs"]["creative_brief"] == ["138", 0]
    assert graph["136"]["inputs"]["duration_seconds"] == ["132", 0]
    assert "length" not in graph["136"]["inputs"]
    assert graph["136"]["inputs"]["prompt_seed"] == 42
    assert graph["136"]["inputs"]["unload_after"] is True
    assert graph["153"]["inputs"]["source"] == ["136", 5]
    assert "H3PromptStandardizer" not in {node["class_type"] for node in graph.values()}


@pytest.mark.parametrize("mode", ["original", "lightx2v", "v4step600"])
def test_ref2va_ollama_manifest_binds_model_to_native_conditioning(mode):
    preset = load_presets(ROOT / "workflows")[f"ref2va_{mode}_ollama"]
    spec = preset.manifest["parameters"]["ollama_model"]
    assert spec == {
        "type": "string",
        "default": "gemma4:e4b",
        "node": "136",
        "input": "ollama_model",
        "ui": {"label": "Ollama 标准化模型", "semantic": "advanced"},
    }
    graph = preset.build_prompt(values(ollama_model="qwen3:8b"), f"{mode}-custom", {})
    assert graph["136"]["inputs"]["ollama_model"] == "qwen3:8b"


@pytest.mark.parametrize("backend", ["raw", "qwen35"])
def test_non_ollama_ref2va_manifests_do_not_accept_ollama_model(backend):
    presets = load_presets(ROOT / "workflows")
    for mode in ("original", "lightx2v", "v4step600"):
        assert "ollama_model" not in presets[f"ref2va_{mode}_{backend}"].manifest["parameters"]


@pytest.mark.parametrize("mode", ["original", "lightx2v", "v4step600"])
def test_ref2va_ollama_progress_metadata_tracks_native_standardizer(mode):
    manifest = load_presets(ROOT / "workflows")[f"ref2va_{mode}_ollama"].manifest
    assert "152" not in manifest["stages"]
    assert "152" not in manifest["progress_phase"]
    assert manifest["stages"]["136"] == "标准化提示词"
    assert manifest["progress_phase"]["136"] == "standardize"


def test_ref2va_representative_visual_prefers_image_then_video_first_frame():
    presets = load_presets(ROOT / "workflows")
    image = presets["ref2va_original_ollama"].build_prompt(values(), "image", {"image_0": "image.png", "video_0": "clip.mp4"})
    assert image["136"]["inputs"]["ref_images.ref_image_0"] == ["9100", 0]
    assert "first_frame" not in image["136"]["inputs"]

    video = presets["ref2va_original_ollama"].build_prompt(values(), "video", {"video_0": "clip.mp4"})
    assert video["136"]["inputs"]["ref_videos.ref_video_0"] == ["9300", 0]
    assert video["9300"] == {"class_type": "GetVideoComponents", "inputs": {"video": ["9200", 0]}}

    text = presets["ref2va_original_ollama"].build_prompt(values(), "text", {})
    assert "ref_images.ref_image_0" not in text["136"]["inputs"]

    raw = presets["ref2va_original_raw"].build_prompt(values(), "raw", {"image_0": "image.png"})
    assert "first_frame" not in raw["136"]["inputs"]


@pytest.mark.parametrize(
    "media, expected_source, expected_image_node",
    [
        ({"image_0": "image.png", "video_0": "clip.mp4"}, ["9100", 0], None),
        ({"video_0": "clip.mp4"}, ["9500", 0], "9500"),
        ({}, None, None),
    ],
)
def test_ref2va_qwen_writer_keeps_representative_visual_contract(
    media, expected_source, expected_image_node
):
    preset = load_presets(ROOT / "workflows")["ref2va_v4step600_qwen35"]
    graph = preset.build_prompt(values(), "qwen-visual", media)
    inputs = graph["176"]["inputs"]
    assert inputs.get("first_frame") == expected_source
    assert "last_frame" not in inputs
    assert graph["136"]["inputs"].get("ref_images.ref_image_0") == (
        ["9100", 0] if "image_0" in media else None
    )
    if expected_image_node:
        assert graph[expected_image_node] == {
            "class_type": "ImageFromBatch",
            "inputs": {"images": ["9300", 0], "batch_index": 0, "length": 1},
        }
    else:
        assert not any(node.get("class_type") == "ImageFromBatch" for node in graph.values())


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
async def test_full_runtime_stack_binds_and_retries_selected_ref2va_ollama_model(
    panel_client_v048, comfy_server_v048
):
    form = FormData(default_to_multipart=True)
    form.add_field("preset_id", "h3-ref2va-group")
    form.add_field("prompt", "custom ollama model")
    form.add_field("values_json", json.dumps({
        "generation_mode": "v4step600",
        "prompt_backend": "ollama",
        "inference_profile": "int8",
        "ollama_model": "qwen3:8b",
    }))

    response = await panel_client_v048.post("/api/jobs", data=form, headers=LOGIN)
    assert response.status == 201, await response.text()
    created = await response.json()
    assert comfy_server_v048.app["submitted"][-1]["prompt"]["136"]["inputs"]["ollama_model"] == "qwen3:8b"
    stored = await panel_client_v048.app["db"].get_job(created["id"])
    assert stored["input_values"]["ollama_model"] == "qwen3:8b"

    await panel_client_v048.app["db"].update_job(created["id"], status="failed")
    retry = await panel_client_v048.post(f"/api/jobs/{created['id']}/retry", headers=LOGIN)
    assert retry.status == 200
    draft = await retry.json()
    assert draft["prompt_backend"] == "ollama"
    assert draft["values"]["ollama_model"] == "qwen3:8b"


@pytest.mark.asyncio
async def test_ref2va_seed_policies_drive_actual_graph_seed(panel_client_v048, comfy_server_v048, monkeypatch):
    from comfyui_remote_panel import v04

    monkeypatch.setattr(v04.secrets, "randbelow", lambda _: 321)

    async def submit(policy, seed=None):
        form = FormData(default_to_multipart=True)
        form.add_field("preset_id", "h3-ref2va-group")
        form.add_field("prompt", f"{policy} seed")
        values_json = {
            "generation_mode": "original",
            "prompt_backend": "raw",
            "inference_profile": "int8",
            "seed_policy": policy,
        }
        if seed is not None:
            values_json["seed_value"] = str(seed)
            form.add_field("seed", str(seed))
        form.add_field("values_json", json.dumps(values_json))
        response = await panel_client_v048.post("/api/jobs", data=form, headers=LOGIN)
        assert response.status == 201, await response.text()
        return await response.json(), comfy_server_v048.app["submitted"][-1]["prompt"]

    randomized, random_graph = await submit("randomize")
    fixed, fixed_graph = await submit("fixed", 700)
    incremented_1, increment_graph_1 = await submit("increment", 800)
    incremented_2, increment_graph_2 = await submit("increment", 800)

    assert randomized["seed_policy"] == "randomize"
    assert randomized["actual_seed"] == "321"
    assert random_graph["129"]["inputs"]["noise_seed"] == 321
    assert fixed["seed_policy"] == "fixed"
    assert fixed["actual_seed"] == "700"
    assert fixed_graph["129"]["inputs"]["noise_seed"] == 700
    assert incremented_1["actual_seed"] == "800"
    assert incremented_2["actual_seed"] == "801"
    assert increment_graph_1["129"]["inputs"]["noise_seed"] == 800
    assert increment_graph_2["129"]["inputs"]["noise_seed"] == 801


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
        "seed_policy": "fixed",
        "media_resolution": {
            "image_0": {"policy": "auto", "target_megapixels": 0.5},
        },
    }))
    form.add_field("prompt", "retry canonical")
    form.add_field("scheduler", "simple")
    form.add_field("sampler", "euler")
    form.add_field("steps", "4")
    form.add_field("seed", "314159")
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
    assert draft["scheduler"] == "simple"
    assert draft["sampler"] == "euler"
    assert draft["steps"] == 4
    assert draft["seed"] == "314159"
    assert draft["seed_policy"] == "fixed"
    assert draft["media_resolution"]["image_0"] == {
        "policy": "auto", "target_megapixels": 0.5,
    }
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
