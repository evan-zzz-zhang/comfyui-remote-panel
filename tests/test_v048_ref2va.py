from pathlib import Path

from comfyui_remote_panel.inference_profile import resolve_inference_profile
from comfyui_remote_panel.preset import load_presets
from comfyui_remote_panel.workflow_registry import (
    CANONICAL_REF2VA_ASSET_IDS,
    resolve_ref2va_asset,
)


ROOT = Path(__file__).resolve().parents[1]


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
