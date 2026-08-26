import json

import pytest

from comfyui_remote_panel.preset import PresetError, preset_from_definition
from comfyui_remote_panel.workflow_config import (
    build_definition,
    export_package,
    import_package,
    inspect_api_workflow,
    parse_json_bytes,
)


def save_image_workflow():
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "model.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "A cat", "clip": ["1", 1]}},
        "3": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512, "batch_size": 1}},
        "4": {"class_type": "KSampler", "inputs": {"seed": 1, "steps": 20, "cfg": 7.0, "model": ["1", 0], "positive": ["2", 0], "latent_image": ["3", 0]}},
        "5": {"class_type": "VAEDecode", "inputs": {"samples": ["4", 0], "vae": ["1", 2]}},
        "6": {"class_type": "SaveImage", "inputs": {"images": ["5", 0], "filename_prefix": "ComfyUI"}},
    }


def semantic_image_workflow():
    workflow = save_image_workflow()
    workflow["7"] = {"class_type": "CLIPTextEncode", "inputs": {"text": "low quality", "clip": ["1", 1]}}
    workflow["8"] = {"class_type": "LoadImage", "inputs": {"image": "reference.png"}}
    workflow["4"]["inputs"]["negative"] = ["7", 0]
    return workflow


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
    sampler = next(node for node in result["nodes"] if node["id"] == "4")
    positive = next(value for value in sampler["inputs"] if value["name"] == "positive")
    assert positive["connection"] == {"node": "2", "output": 0}


def test_inspection_suggests_only_basic_user_facing_inputs():
    result = inspect_api_workflow(semantic_image_workflow())
    basic = result["basic_bindings"]
    parameters = {item["semantic"]: item for item in basic["parameters"]}

    assert parameters["positive_prompt"]["node"] == "2"
    assert parameters["positive_prompt"]["input"] == "text"
    assert parameters["negative_prompt"]["node"] == "7"
    assert parameters["negative_prompt"]["input"] == "text"
    assert parameters["width"]["node"] == "3"
    assert parameters["height"]["node"] == "3"
    assert parameters["batch_size"]["node"] == "3"
    assert {item["semantic"] for item in basic["parameters"]} == {
        "positive_prompt", "negative_prompt", "width", "height", "batch_size"
    }
    assert basic["media"]["reference_image"] == [{
        "semantic": "reference_image", "node": "8", "input": "image", "label": "参考图",
        "kind": "image", "class_type": "LoadImage", "default": "reference.png",
    }]
    assert basic["outputs"][0]["node"] == "6"
    assert basic["warnings"] == []


def test_workflow_json_parser_accepts_bom_and_markdown_fence():
    payload = json.dumps(save_image_workflow(), ensure_ascii=False)
    assert parse_json_bytes(("\ufeff" + payload).encode("utf-8")) == save_image_workflow()
    assert parse_json_bytes(("```json\n" + payload + "\n```").encode()) == save_image_workflow()


def test_workflow_json_parser_rejects_trailing_text_with_helpful_message():
    with pytest.raises(PresetError, match="导出（API）"):
        parse_json_bytes(b'{} unexpected')


def test_remote_workflow_package_round_trip_and_rejects_paths():
    definition = build_definition(save_image_workflow(), remote_config())
    assert import_package(export_package(definition)) == definition
    unsafe = json.loads(json.dumps(definition))
    separator = chr(92)
    unsafe["manifest"]["description"] = "C:" + separator + separator.join(("Users", "owner", "secret.png"))
    with pytest.raises(PresetError, match="本地绝对路径"):
        export_package(unsafe)
