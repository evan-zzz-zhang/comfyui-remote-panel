from __future__ import annotations

import pytest

from comfyui_remote_panel.preset import PresetError, preset_from_definition
from comfyui_remote_panel.workflow_config import build_definition, inspect_api_workflow
from test_workflow_analysis import object_info, wai_img2img_workflow


def wai_config():
    analysis = inspect_api_workflow(wai_img2img_workflow(), object_info())
    parameters = [item for item in analysis["parameters"] if item["confidence"] != "LOW"]
    source = next(item for item in analysis["media_inputs"] if item["semantic"] == "source_image")
    output = analysis["outputs"][0]
    return analysis, {
        "id": "wai-img2img",
        "name": "WAI img2img",
        "parameters": parameters,
        "media": {"type": "slots", "slots": {
            source["id"]: {
                "node": source["node"], "input": source["input"], "kind": "image",
                "required": True, "ui": {"label": "源图", "optional": False},
            }
        }},
        "outputs": [{"id": "primary", "node": output["node"], "kind": output["kind"], "primary": True}],
        "analysis": {
            "capabilities": analysis["capabilities"],
            "confidence": analysis["confidence"],
            "preflight": analysis["preflight"],
        },
    }


def test_required_source_image_is_rejected_before_prompt_build():
    analysis, config = wai_config()
    preset = preset_from_definition(build_definition(wai_img2img_workflow(), config, analysis))
    with pytest.raises(PresetError, match="缺少必需素材.*源图"):
        preset.build_prompt({item["id"]: item["default"] for item in analysis["parameters"] if item["confidence"] != "LOW"}, "123e4567-e89b-42d3-a456-426614174000", {})


def test_uploaded_source_image_replaces_original_loadimage_literal():
    analysis, config = wai_config()
    preset = preset_from_definition(build_definition(wai_img2img_workflow(), config, analysis))
    values = {item["id"]: item["default"] for item in analysis["parameters"] if item["confidence"] != "LOW"}
    prompt = preset.build_prompt(values, "123e4567-e89b-42d3-a456-426614174000", {"image_0": "h3_remote/source.png"})
    assert prompt["4"]["inputs"]["image"] == "h3_remote/source.png"
    assert prompt["6"]["inputs"]["steps"] == 24
    assert prompt["6"]["inputs"]["denoise"] == pytest.approx(0.62)


def test_generic_number_honors_schema_step_precision_and_rejects_misalignment():
    analysis, config = wai_config()
    preset = preset_from_definition(build_definition(wai_img2img_workflow(), config, analysis))
    values = {item["id"]: item["default"] for item in analysis["parameters"] if item["confidence"] != "LOW"}
    values["denoise"] = 0.55
    normalized = preset.validate_parameters(values)
    assert normalized["denoise"] == pytest.approx(0.55)

    values["denoise"] = 0.555
    with pytest.raises(PresetError, match="denoise 步进不合法"):
        preset.validate_parameters(values)


def test_generic_random_seed_respects_schema_range():
    analysis, config = wai_config()
    preset = preset_from_definition(build_definition(wai_img2img_workflow(), config, analysis))
    values = {item["id"]: item["default"] for item in analysis["parameters"] if item["confidence"] != "LOW"}
    values["seed"] = None
    seed = int(preset.validate_parameters(values)["seed"])
    spec = preset.manifest["parameters"]["seed"]
    assert spec["minimum"] <= seed <= spec["maximum"]


def test_capability_profile_is_public_without_workflow_json():
    analysis, config = wai_config()
    preset = preset_from_definition(build_definition(wai_img2img_workflow(), config, analysis))
    public = preset.public_metadata()
    assert public["capability_profile"]["generation_mode"] == "img2img"
    assert public["capability_profile"]["size_strategy"] == "inherit_input"
    assert public["preflight"]["outputs"]["status"] == "PASS"
    assert "workflow" not in public