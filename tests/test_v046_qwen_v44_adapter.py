from __future__ import annotations

import pytest

from comfyui_remote_panel.preset import PresetError, load_presets


QWEN_PRESETS = (
    "h3-fl2va-qwen35-4b",
    "h3-fl2va-lightx2v-qwen35-4b",
    "h3-fl2va-v4step600-qwen35-4b",
)


def _values(preset, aspect_ratio: str = "9:16") -> dict[str, object]:
    parameters = preset.manifest["parameters"]
    return {
        "prompt": "测试 Qwen3.5 v4.4",
        "duration_seconds": 5,
        "aspect_ratio": aspect_ratio,
        "megapixels": 0.4,
        "seed": "123456",
        "scheduler": parameters["scheduler"]["default"],
        "sampler": parameters["sampler"]["default"],
        "steps": parameters["steps"]["default"],
    }


def test_qwen_v44_graphs_keep_the_upstream_loader_resolver_metadata_chain():
    presets = load_presets()
    for preset_id in QWEN_PRESETS:
        preset = presets[preset_id]
        graph = preset.template
        assert preset.manifest["workflow_variant"] == "qwen35-v4.4"
        assert graph["174"] == {
            "class_type": "H3OptionalLoadImageV4",
            "inputs": {"image": "[None]"},
        }
        assert graph["175"] == {
            "class_type": "H3OptionalLoadImageV4",
            "inputs": {"image": "[None]"},
        }
        assert graph["173"]["inputs"]["first_frame"] == ["174", 0]
        assert graph["173"]["inputs"]["last_frame"] == ["175", 0]
        assert graph["136"]["inputs"]["prompt"] == ["177", 0]
        assert graph["136"]["inputs"]["width"] == ["173", 2]
        assert graph["136"]["inputs"]["height"] == ["173", 3]
        assert graph["136"]["inputs"]["length"] == ["173", 4]
        assert graph["183"]["inputs"]["standardized_prompt"] == ["176", 3]
        assert graph["183"]["inputs"]["final_prompt_used"] == ["176", 0]
        assert graph["92"]["class_type"] == "H3SaveVideoWithPromptMetadata"
        assert graph["92"]["inputs"]["run_metadata"] == ["183", 0]
        classes = {node["class_type"] for node in graph.values()}
        assert "H3ReferenceFrames" not in classes
        assert "H3AspectRouter" not in classes


@pytest.mark.parametrize("preset_id", QWEN_PRESETS)
def test_qwen_v44_panel_injects_frames_into_existing_optional_loaders(preset_id):
    preset = load_presets()[preset_id]
    graph = preset.build_prompt(
        _values(preset, "16:9"),
        "11111111-1111-4111-8111-111111111111",
        {"first": "rp_first.png", "last": "rp_last.png"},
    )
    assert graph["174"]["inputs"]["image"] == "rp_first.png"
    assert graph["175"]["inputs"]["image"] == "rp_last.png"
    assert graph["115"]["inputs"]["aspect_ratio"] == "16:9 (Widescreen)"
    assert graph["173"]["inputs"]["use_reference_aspect"] is False
    assert "9001" not in graph
    assert "9002" not in graph
    assert "9003" not in graph
    assert "9004" not in graph


@pytest.mark.parametrize("preset_id", QWEN_PRESETS)
def test_qwen_v44_reference_aspect_is_delegated_to_input_resolver(preset_id):
    preset = load_presets()[preset_id]
    graph = preset.build_prompt(
        _values(preset, "reference"),
        "22222222-2222-4222-8222-222222222222",
        {"first": "rp_reference.png"},
    )
    assert graph["174"]["inputs"]["image"] == "rp_reference.png"
    assert graph["175"]["inputs"]["image"] == "[None]"
    assert graph["173"]["inputs"]["use_reference_aspect"] is True
    # The reference sentinel does not overwrite ResolutionSelector. The v4.4
    # resolver derives the actual output aspect from the supplied frame.
    assert graph["115"]["inputs"]["aspect_ratio"] == "9:16 (Portrait Widescreen)"


@pytest.mark.parametrize("preset_id", QWEN_PRESETS)
def test_qwen_v44_reference_aspect_still_requires_a_reference_frame(preset_id):
    preset = load_presets()[preset_id]
    with pytest.raises(PresetError, match="参考图比例需要至少上传一张参考图"):
        preset.build_prompt(
            _values(preset, "reference"),
            "33333333-3333-4333-8333-333333333333",
            {},
        )


def test_qwen_v44_generation_tuning_is_unchanged():
    presets = load_presets()
    expected = {
        "h3-fl2va-qwen35-4b": ("simple", "res_multistep", 20, None),
        "h3-fl2va-lightx2v-qwen35-4b": (
            "simple",
            "euler",
            8,
            "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors",
        ),
        "h3-fl2va-v4step600-qwen35-4b": (
            "beta",
            "euler",
            8,
            "minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors",
        ),
    }
    for preset_id, (scheduler, sampler, steps, lora) in expected.items():
        preset = presets[preset_id]
        assert preset.manifest["parameters"]["scheduler"]["default"] == scheduler
        assert preset.manifest["parameters"]["sampler"]["default"] == sampler
        assert preset.manifest["parameters"]["steps"]["default"] == steps
        lora_nodes = [node for node in preset.template.values() if node["class_type"] == "LoraLoader"]
        if lora is None:
            assert lora_nodes == []
        else:
            assert lora_nodes[0]["inputs"]["lora_name"] == lora
