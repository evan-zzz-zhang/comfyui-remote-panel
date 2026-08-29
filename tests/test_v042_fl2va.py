from __future__ import annotations

import pytest

from comfyui_remote_panel import v042
from comfyui_remote_panel.preset import PresetError, load_presets


def _values(preset, *, prompt: str = "测试镜头", aspect: str = "9:16", standardize: bool = True):
    values = {
        name: spec.get("default")
        for name, spec in preset.manifest["parameters"].items()
    }
    values.update(
        prompt=prompt,
        aspect_ratio=aspect,
        prompt_standardization=standardize,
        seed="1",
    )
    return values


def test_three_fl2va_workflows_load_with_new_contract():
    presets = load_presets()
    expected = {
        "h3-fl2va": ("128", "127", "124"),
        "h3-fl2va-lightx2v": ("156", "155", "152"),
        "h3-fl2va-v4step600": ("156", "155", "152"),
    }
    for preset_id, (frames, router, standardizer) in expected.items():
        preset = presets[preset_id]
        assert preset.media_binding["target_node"] == frames
        assert preset.manifest["h3_aspect_router"]["node"] == router
        assert preset.manifest["h3_prompt_standardizer"]["node"] == standardizer
        assert preset.manifest["parameters"]["prompt_standardization"]["default"] is True


def test_unified_fl2va_exposes_v4_as_default_generation_mode():
    preset = load_presets()["h3-fl2va"]
    metadata = preset.public_metadata()
    assert metadata["generation_modes"]["default"] == "v4_600step"
    assert metadata["generation_modes"]["values"] == {
        "v4_600step": {
            "label": "v4_600step",
            "preset_id": "h3-fl2va-v4step600",
        },
        "lightx2v": {
            "label": "LightX2V",
            "preset_id": "h3-fl2va-lightx2v",
        },
        "original": {
            "label": "原版",
            "preset_id": "h3-fl2va",
        },
    }


def test_standardizer_requires_prompt_even_when_frame_exists():
    preset = load_presets()["h3-fl2va-v4step600"]
    with pytest.raises(PresetError, match="提示词不能为空"):
        preset.validate_parameters(
            _values(preset, prompt="", standardize=True),
            allow_empty_prompt=True,
        )

    normalized = preset.validate_parameters(
        _values(preset, prompt="", standardize=False),
        allow_empty_prompt=True,
    )
    assert normalized["prompt"] == ""
    assert normalized["prompt_standardization"] is False


@pytest.mark.parametrize(
    ("preset_id", "frame_node", "router_node", "standardizer_node"),
    [
        ("h3-fl2va", "128", "127", "124"),
        ("h3-fl2va-lightx2v", "156", "155", "152"),
        ("h3-fl2va-v4step600", "156", "155", "152"),
    ],
)
def test_reference_aspect_uses_h3_router_without_legacy_size_nodes(
    monkeypatch, preset_id, frame_node, router_node, standardizer_node
):
    preset = load_presets()[preset_id]
    monkeypatch.setattr(v042.secrets, "randbelow", lambda _: 987654321)

    prompt = preset.build_prompt(
        _values(preset, aspect="reference"),
        "test-job",
        {"first": "first.png", "last": "last.png"},
    )

    assert prompt[frame_node]["inputs"]["first_frame"] == ["9001", 0]
    assert prompt[frame_node]["inputs"]["last_frame"] == ["9002", 0]
    assert prompt[router_node]["inputs"]["aspect_source"] == "auto"
    assert prompt[standardizer_node]["inputs"]["seed"] == 987654321
    assert "9003" not in prompt
    assert "9004" not in prompt


def test_fixed_aspect_keeps_output_router_and_randomizes_standardizer_seed(monkeypatch):
    preset = load_presets()["h3-fl2va-v4step600"]
    monkeypatch.setattr(v042.secrets, "randbelow", lambda _: 123456789)

    prompt = preset.build_prompt(
        _values(preset, aspect="16:9"),
        "test-job",
        {"first": "first.png"},
    )

    assert prompt["155"]["inputs"]["aspect_source"] == "output"
    assert prompt["115"]["inputs"]["aspect_ratio"] == "16:9 (Widescreen)"
    assert prompt["152"]["inputs"]["seed"] == 123456789


def test_generation_mode_mapping_keeps_three_underlying_presets():
    assert v042.DEFAULT_GENERATION_MODE == "v4_600step"
    assert v042.GENERATION_MODES == {
        "original": "h3-fl2va",
        "lightx2v": "h3-fl2va-lightx2v",
        "v4_600step": "h3-fl2va-v4step600",
    }
