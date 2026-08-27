from __future__ import annotations

import pytest

from comfyui_remote_panel.preset import BUILTIN_WORKFLOW_DIR, load_presets


H3_IDS = {
    "h3-fl2va",
    "h3-fl2va-lightx2v",
    "h3-fl2va-v4step600",
    "h3-ref2va",
    "h3-ref2va-lightx2v",
    "h3-ref2va-v4step600",
}


@pytest.fixture(scope="module")
def h3_presets():
    presets = load_presets(BUILTIN_WORKFLOW_DIR)
    assert H3_IDS <= set(presets)
    return {preset_id: presets[preset_id] for preset_id in H3_IDS}


def defaults_for(preset):
    values = {}
    for name, spec in preset.manifest["parameters"].items():
        if "default" in spec:
            values[name] = spec["default"]
        elif name == "prompt":
            values[name] = "H3 v0.3 regression"
        elif name == "seed":
            values[name] = 123
    return values


@pytest.mark.parametrize("preset_id", sorted(H3_IDS))
def test_h3_manifest_and_parameters_remain_loadable(h3_presets, preset_id):
    preset = h3_presets[preset_id]
    assert preset.manifest["family"] in {"fl2va", "ref2va"}
    assert preset.media_binding["type"] in {"frame_pair", "collection"}
    assert preset.output_node
    assert preset.manifest["output_bindings"][0]["kind"] == "video"
    normalized = preset.validate_parameters(defaults_for(preset))
    assert normalized["prompt"] == "H3 v0.3 regression"
    assert "seed" in normalized


@pytest.mark.parametrize("preset_id", [value for value in sorted(H3_IDS) if "fl2va" in value])
def test_h3_fl2va_media_rules_are_unchanged(h3_presets, preset_id):
    preset = h3_presets[preset_id]
    mode, has_media = preset.validate_media_roles(set())
    assert mode == "纯文字"
    assert has_media is False
    mode, has_media = preset.validate_media_roles({"first"})
    assert has_media is True
    assert mode
    mode, has_media = preset.validate_media_roles({"first", "last"})
    assert has_media is True
    assert mode


@pytest.mark.parametrize("preset_id", [value for value in sorted(H3_IDS) if "ref2va" in value])
def test_h3_ref2va_collection_rules_are_unchanged(h3_presets, preset_id):
    preset = h3_presets[preset_id]
    mode, has_media = preset.validate_media_roles(set())
    assert mode == "纯文字"
    assert has_media is False
    mode, has_media = preset.validate_media_roles({"image_0", "video_0", "audio_0"})
    assert "1图" in mode and "1视频" in mode and "1音频" in mode
    assert has_media is False


def test_configurator_runtime_patch_does_not_mark_h3_as_generic(h3_presets):
    for preset in h3_presets.values():
        public = preset.public_metadata()
        assert public["family"] in {"fl2va", "ref2va"}
        assert public["capability_profile"] == {}
        assert public["preflight"] == {}
