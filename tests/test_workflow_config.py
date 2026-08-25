import json

import pytest

from comfyui_remote_panel.preset import PresetError, preset_from_definition
from comfyui_remote_panel.workflow_config import build_definition, export_package, import_package, inspect_api_workflow


def save_image_workflow():
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "A cat", "clip": ["1", 1]}},
        "3": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
        "4": {"class_type": "KSampler", "inputs": {"seed": 1, "steps": 20, "cfg": 7.0, "model": ["1", 0], "positive": ["2", 0], "latent_image": ["3", 0]}},
        "5": {"class_type": "VAEDecode", "inputs": {"samples": ["4", 0], "vae": ["1", 2]}},
        "6": {"class_type": "SaveImage", "inputs": {"images": ["5", 0], "filename_prefix": "ComfyUI"}},
    }


def remote_config():
    return {
        "id": "standard-save-image", "name": "Standard SaveImage",
        "parameters": [
            {"id": "positive_prompt", "node": "2", "input": "text", "type": "string", "default": "A cat", "ui": {"label": "提示词"}},
            {"id": "steps", "node": "4", "input": "steps", "type": "integer", "default": 20, "minimum": 1, "maximum": 100},
        ],
        "media": {"type": "none"},
        "outputs": [{"id": "primary", "node": "6", "kind": "image", "history_keys": ["images"], "primary": True}],
    }


def test_standard_saveimage_builds_without_h3_code_changes():
    definition = build_definition(save_image_workflow(), remote_config())
    preset = preset_from_definition(definition)
    prompt = preset.build_prompt({"positive_prompt": "A dog", "steps": 12}, "123e4567-e89b-42d3-a456-426614174000", {})
    assert prompt["2"]["inputs"]["text"] == "A dog"
    assert prompt["4"]["inputs"]["steps"] == 12
    assert prompt["6"]["inputs"]["filename_prefix"].startswith("h3_remote/rp_")


def test_inspection_never_suggests_connected_inputs():
    result = inspect_api_workflow(save_image_workflow())
    clip = next(node for node in result["nodes"] if node["id"] == "2")
    assert next(value for value in clip["inputs"] if value["name"] == "clip")["suggested_control"] is None


def test_remote_workflow_package_round_trip_and_rejects_paths():
    definition = build_definition(save_image_workflow(), remote_config())
    assert import_package(export_package(definition)) == definition
    unsafe = json.loads(json.dumps(definition))
    separator = chr(92)
    unsafe["manifest"]["description"] = "C:" + separator + separator.join(("Users", "owner", "secret.png"))
    with pytest.raises(PresetError, match="本地绝对路径"):
        export_package(unsafe)
