import json
from pathlib import Path

import pytest

from comfyui_remote_panel.preset import BUILTIN_WORKFLOW_DIR, PresetError, load_presets


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def preset():
    return load_presets(ROOT / "workflows")["h3-fl2va-v4step600"]


def values():
    return {"prompt": "镜头推进", "duration_seconds": 5, "aspect_ratio": "9:16", "megapixels": 0.4, "seed": 42}


@pytest.mark.parametrize(
    ("frames", "expected_inputs"),
    [
        ({}, set()),
        ({"first": "h3_remote/a/first.png"}, {"first_frame"}),
        ({"last": "h3_remote/a/last.webp"}, {"last_frame"}),
        ({"first": "h3_remote/a/first.png", "last": "h3_remote/a/last.jpg"}, {"first_frame", "last_frame"}),
    ],
)
def test_builds_all_frame_modes_without_placeholder_links(preset, frames, expected_inputs):
    graph = preset.build_prompt(values(), "00000000-0000-0000-0000-000000000001", frames)
    target = graph["136"]["inputs"]
    assert {name for name in ("first_frame", "last_frame") if name in target} == expected_inputs
    assert ("9001" in graph) == ("first" in frames)
    assert ("9002" in graph) == ("last" in frames)


def test_mutates_declared_sampling_parameters_and_keeps_model_locked(preset):
    graph = preset.build_prompt({"prompt": "test", "duration_seconds": 15, "aspect_ratio": "21:9", "megapixels": 1.0, "seed": 2**64 - 1, "scheduler": "karras", "sampler": "dpmpp_2m", "steps": 12}, "id", {})
    assert graph["124"]["inputs"] == {"model": ["147", 0], "scheduler": "karras", "steps": 12, "denoise": 1.0}
    assert graph["149"]["inputs"]["sampler_name"] == "dpmpp_2m"
    assert graph["145"]["inputs"]["lora_name"] == "minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors"
    assert graph["115"]["inputs"]["aspect_ratio"] == "21:9 (Ultrawide)"
    assert graph["92"]["inputs"]["filename_prefix"] == "h3_remote/id"


@pytest.mark.parametrize("field,value", [("duration_seconds", 4), ("duration_seconds", 16), ("megapixels", 0.1), ("megapixels", 0.3), ("megapixels", 1.1), ("seed", -1), ("seed", 2**64)])
def test_parameter_boundaries(preset, field, value):
    data = values()
    data[field] = value
    with pytest.raises(PresetError):
        preset.validate_parameters(data)


def test_all_eight_aspect_ratios(preset):
    for ratio in ("1:1", "2:3", "3:2", "3:4", "4:3", "9:16", "16:9", "21:9"):
        data = values()
        data["aspect_ratio"] = ratio
        assert preset.validate_parameters(data)["aspect_ratio"] == ratio


@pytest.mark.parametrize(
    ("frames", "source_node"),
    [
        ({"first": "h3_remote/a/first.png"}, "9001"),
        ({"last": "h3_remote/a/last.png"}, "9002"),
        ({"first": "h3_remote/a/first.png", "last": "h3_remote/a/last.png"}, "9001"),
    ],
)
def test_reference_aspect_uses_first_then_falls_back_to_last(preset, frames, source_node):
    data = values()
    data["aspect_ratio"] = "reference"
    data["megapixels"] = 0.8
    graph = preset.build_prompt(data, "job", frames)
    assert graph["9003"] == {
        "class_type": "ImageScaleToTotalPixels",
        "inputs": {
            "image": [source_node, 0],
            "upscale_method": "nearest-exact",
            "megapixels": 0.8,
            "resolution_steps": 32,
        },
    }
    assert graph["9004"] == {"class_type": "GetImageSize", "inputs": {"image": ["9003", 0]}}
    assert graph["136"]["inputs"]["width"] == ["9004", 0]
    assert graph["136"]["inputs"]["height"] == ["9004", 1]


def test_reference_aspect_rejects_missing_reference_image(preset):
    data = values()
    data["aspect_ratio"] = "reference"
    with pytest.raises(PresetError, match="参考图"):
        preset.build_prompt(data, "job", {})


def test_all_six_presets_load_and_keep_their_real_defaults():
    presets = load_presets(ROOT / "workflows")
    assert set(presets) == {
        "h3-fl2va", "h3-fl2va-lightx2v", "h3-fl2va-v4step600",
        "h3-ref2va", "h3-ref2va-lightx2v", "h3-ref2va-v4step600",
    }
    expected = {
        "h3-fl2va": ("simple", "res_multistep", 20),
        "h3-fl2va-lightx2v": ("simple", "euler", 8),
        "h3-fl2va-v4step600": ("beta", "euler", 8),
        "h3-ref2va": ("simple", "res_multistep", 20),
        "h3-ref2va-lightx2v": ("simple", "euler", 4),
        "h3-ref2va-v4step600": ("beta", "euler", 8),
    }
    for preset_id, (scheduler, sampler, steps) in expected.items():
        normalized = presets[preset_id].validate_parameters(values())
        assert (normalized["scheduler"], normalized["sampler"], normalized["steps"]) == (scheduler, sampler, steps)


def test_packaged_presets_are_available_without_external_directory(tmp_path):
    presets = load_presets(tmp_path / "missing-workflows")
    assert len(presets) == 6
    assert BUILTIN_WORKFLOW_DIR.is_dir()


def test_external_workflow_overrides_packaged_preset(tmp_path):
    source = BUILTIN_WORKFLOW_DIR / "h3-fl2va-v4step600"
    override = tmp_path / "override"
    target = override / "h3-fl2va-v4step600"
    target.mkdir(parents=True)
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    manifest["name"] = "External override"
    (target / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (target / "workflow.json").write_text((source / "workflow.json").read_text(encoding="utf-8"), encoding="utf-8")

    assert load_presets(override)["h3-fl2va-v4step600"].manifest["name"] == "External override"


def test_ref2va_maps_two_uploaded_images_to_reference_slots():
    preset = load_presets(ROOT / "workflows")["h3-ref2va-lightx2v"]
    graph = preset.build_prompt(values(), "job", {"first": "a.png", "last": "b.png"})
    assert graph["136"]["inputs"]["ref_images.ref_image_0"] == ["9100", 0]
    assert graph["136"]["inputs"]["ref_images.ref_image_1"] == ["9101", 0]
    assert "first_frame" not in graph["136"]["inputs"]
    assert "last_frame" not in graph["136"]["inputs"]


def test_ref2va_builds_video_audio_and_multi_image_reference_graph():
    preset = load_presets(ROOT / "workflows")["h3-ref2va"]
    graph = preset.build_prompt(values(), "job", {
        "image_0": "a.png", "image_1": "b.webp", "video_0": "clip.mp4", "audio_0": "voice.wav",
    })
    target = graph["136"]["inputs"]
    assert graph["9200"] == {"class_type": "LoadVideo", "inputs": {"file": "clip.mp4"}}
    assert graph["9300"] == {"class_type": "GetVideoComponents", "inputs": {"video": ["9200", 0]}}
    assert target["ref_videos.ref_video_0"] == ["9300", 0]
    assert target["ref_video_audios.ref_video_audio_0"] == ["9300", 1]
    assert graph["9400"] == {"class_type": "LoadAudio", "inputs": {"audio": "voice.wav"}}
    assert target["ref_audios.ref_audio_0"] == ["9400", 0]


def test_ref2va_reference_aspect_can_use_image_or_video_one():
    preset = load_presets(ROOT / "workflows")["h3-ref2va"]
    image_graph = preset.build_prompt(values() | {"aspect_ratio": "reference_image"}, "image-job", {"image_0": "image.png"})
    assert image_graph["9003"]["inputs"]["image"] == ["9100", 0]
    assert image_graph["136"]["inputs"]["width"] == ["9004", 0]

    video_graph = preset.build_prompt(values() | {"aspect_ratio": "reference_video"}, "video-job", {"video_0": "clip.mp4"})
    assert video_graph["9003"]["inputs"]["image"] == ["9300", 0]
    assert video_graph["136"]["inputs"]["height"] == ["9004", 1]


def test_ref2va_legacy_reference_aspect_remains_image_based():
    preset = load_presets(ROOT / "workflows")["h3-ref2va"]
    graph = preset.build_prompt(values() | {"aspect_ratio": "reference"}, "legacy-job", {"image_0": "image.png"})
    assert graph["9003"]["inputs"]["image"] == ["9100", 0]
