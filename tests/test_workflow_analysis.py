from __future__ import annotations

from comfyui_remote_panel.workflow_config import inspect_api_workflow


def schema(required=None, optional=None, output=None):
    return {
        "input": {"required": required or {}, "optional": optional or {}},
        "output": output or [],
    }


def object_info():
    values = {
        "CheckpointLoaderSimple": schema({
            "ckpt_name": [["wai.safetensors", "other.safetensors"], {"default": "wai.safetensors"}],
        }, output=["MODEL", "CLIP", "VAE"]),
        "CLIPTextEncode": schema({
            "text": ["STRING", {"default": "", "multiline": True}],
            "clip": ["CLIP", {}],
        }, output=["CONDITIONING"]),
        "LoadImage": schema({
            "image": [["source.png"], {"default": "source.png", "image_upload": True}],
        }, output=["IMAGE", "MASK"]),
        "VAEEncode": schema({"pixels": ["IMAGE", {}], "vae": ["VAE", {}]}, output=["LATENT"]),
        "EmptyLatentImage": schema({
            "width": ["INT", {"default": 512, "min": 64, "max": 4096, "step": 8}],
            "height": ["INT", {"default": 512, "min": 64, "max": 4096, "step": 8}],
            "batch_size": ["INT", {"default": 1, "min": 1, "max": 64, "step": 1}],
        }, output=["LATENT"]),
        "KSampler": schema({
            "seed": ["INT", {"default": 0, "min": 0, "max": 2**63 - 1, "step": 1}],
            "steps": ["INT", {"default": 20, "min": 1, "max": 100, "step": 1}],
            "cfg": ["FLOAT", {"default": 7.0, "min": 0.0, "max": 30.0, "step": 0.1}],
            "sampler_name": [["euler", "dpmpp_2m"], {"default": "euler"}],
            "scheduler": [["normal", "karras"], {"default": "normal"}],
            "denoise": ["FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01}],
            "model": ["MODEL", {}],
            "positive": ["CONDITIONING", {}],
            "negative": ["CONDITIONING", {}],
            "latent_image": ["LATENT", {}],
        }, output=["LATENT"]),
        "VAEDecode": schema({"samples": ["LATENT", {}], "vae": ["VAE", {}]}, output=["IMAGE"]),
        "SaveImage": schema({
            "images": ["IMAGE", {}],
            "filename_prefix": ["STRING", {"default": "ComfyUI"}],
        }),
        "CustomScalarNode": schema({
            "choice": [["one", "two"], {"default": "one"}],
            "enabled": ["BOOLEAN", {"default": True}],
            "count": ["INT", {"default": 2, "min": 1, "max": 10, "step": 1}],
            "strength": ["FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.05}],
            "note": ["STRING", {"default": "hello", "multiline": True}],
        }, output=["IMAGE"]),
    }
    return {name: {name: value} for name, value in values.items()}


def wai_img2img_workflow():
    return {
        "1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "wai.safetensors"}},
        "2": {"class_type": "CLIPTextEncode", "inputs": {"text": "portrait", "clip": ["1", 1]}},
        "3": {"class_type": "CLIPTextEncode", "inputs": {"text": "low quality", "clip": ["1", 1]}},
        "4": {"class_type": "LoadImage", "inputs": {"image": "source.png", "upload": "image"}},
        "5": {"class_type": "VAEEncode", "inputs": {"pixels": ["4", 0], "vae": ["1", 2]}},
        "6": {"class_type": "KSampler", "inputs": {
            "seed": 123, "steps": 24, "cfg": 6.5, "sampler_name": "euler",
            "scheduler": "normal", "denoise": 0.62, "model": ["1", 0],
            "positive": ["2", 0], "negative": ["3", 0], "latent_image": ["5", 0],
        }},
        "7": {"class_type": "VAEDecode", "inputs": {"samples": ["6", 0], "vae": ["1", 2]}},
        "8": {"class_type": "SaveImage", "inputs": {"images": ["7", 0], "filename_prefix": "ComfyUI"}},
    }


def txt2img_workflow():
    graph = wai_img2img_workflow()
    graph.pop("4")
    graph.pop("5")
    graph["9"] = {"class_type": "EmptyLatentImage", "inputs": {"width": 768, "height": 1024, "batch_size": 2}}
    graph["6"]["inputs"]["latent_image"] = ["9", 0]
    return graph


def by_semantic(result):
    return {item["semantic"]: item for item in result["parameters"]}


def test_wai_img2img_profile_uses_graph_and_schema_without_dimensions():
    result = inspect_api_workflow(wai_img2img_workflow(), object_info())
    params = by_semantic(result)
    caps = result["capabilities"]

    assert caps["generation_mode"] == "img2img"
    assert caps["output_type"] == "image"
    assert caps["size_strategy"] == "inherit_input"
    assert caps["batch_strategy"] == "workflow_fixed"
    assert "width" not in params and "height" not in params and "batch_size" not in params
    assert params["positive_prompt"]["confidence"] == "HIGH"
    assert params["negative_prompt"]["confidence"] == "HIGH"
    assert params["sampler"]["type"] == "enum"
    assert params["scheduler"]["type"] == "enum"
    assert params["steps"]["type"] == "integer"
    assert params["cfg"]["type"] == "number"
    assert params["denoise"]["type"] == "number"
    assert params["checkpoint"]["type"] == "enum"
    assert params["checkpoint"]["advanced"] is True
    source = next(item for item in result["media_inputs"] if item["semantic"] == "source_image")
    assert source["required"] is True
    assert source["confidence"] == "HIGH"
    assert result["preflight"]["nodes"]["status"] == "PASS"
    assert result["preflight"]["outputs"]["status"] == "PASS"
    assert result["preflight"]["parameters"]["status"] == "PASS"
    assert any(item["code"] == "frontend_helper_input" and item["severity"] == "WARN" for item in result["diagnostics"])
    assert not any(item["code"] == "frontend_helper_input" and item["severity"] == "FAIL" for item in result["diagnostics"])


def test_txt2img_detects_width_height_batch_from_empty_latent_graph():
    result = inspect_api_workflow(txt2img_workflow(), object_info())
    params = by_semantic(result)
    assert result["capabilities"]["generation_mode"] == "txt2img"
    assert result["capabilities"]["size_strategy"] == "configurable"
    assert result["capabilities"]["batch_strategy"] == "configurable"
    assert params["width"]["default"] == 768
    assert params["height"]["default"] == 1024
    assert params["batch_size"]["default"] == 2
    assert params["width"]["confidence"] == "HIGH"
    assert params["height"]["confidence"] == "HIGH"


def test_schema_drives_custom_scalar_controls():
    workflow = {
        "1": {"class_type": "CustomScalarNode", "inputs": {
            "choice": "one", "enabled": True, "count": 2, "strength": 0.5, "note": "hello",
        }},
        "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0], "filename_prefix": "ComfyUI"}},
    }
    result = inspect_api_workflow(workflow, object_info())
    params = {item["input"]: item for item in result["parameters"]}
    assert params["choice"]["type"] == "enum" and params["choice"]["control"] == "select"
    assert params["enabled"]["type"] == "boolean" and params["enabled"]["control"] == "switch"
    assert params["count"]["type"] == "integer"
    assert params["strength"]["type"] == "number"
    assert params["note"]["type"] == "string" and params["note"]["control"] == "textarea"
    assert all(params[name]["confidence"] == "MEDIUM" for name in params)


def test_missing_node_is_a_nodes_fail():
    schemas = object_info()
    schemas.pop("VAEEncode")
    result = inspect_api_workflow(wai_img2img_workflow(), schemas)
    assert result["preflight"]["nodes"]["status"] == "FAIL"
    assert any(item["code"] == "missing_node" and item["node"] == "5" for item in result["diagnostics"])


def test_connected_schema_mismatch_fails_but_literal_unknown_only_warns():
    schemas = object_info()
    ksampler = schemas["KSampler"]["KSampler"]
    ksampler["input"]["required"].pop("positive")
    graph = wai_img2img_workflow()
    graph["6"]["inputs"]["legacy_hint"] = "keep-me"
    result = inspect_api_workflow(graph, schemas)
    assert any(item["code"] == "unknown_connected_input" and item["severity"] == "FAIL" for item in result["diagnostics"])
    assert any(item["code"] == "legacy_or_unknown_input" and item["severity"] == "WARN" for item in result["diagnostics"])


def test_unrecognized_scalar_stays_low_confidence_manual_candidate():
    workflow = {
        "1": {"class_type": "MysteryTransform", "inputs": {"strength": 0.42}},
        "2": {"class_type": "SaveImage", "inputs": {"images": ["1", 0], "filename_prefix": "ComfyUI"}},
    }
    result = inspect_api_workflow(workflow)
    candidate = next(item for item in result["parameters"] if item["input"] == "strength")
    assert candidate["semantic"] == "denoise"
    assert candidate["confidence"] == "LOW"
    assert candidate["source"] == "heuristic"
    assert result["preflight"]["parameters"]["status"] == "WARN"
    assert any(item["code"] == "manual_mapping_required" for item in result["diagnostics"])
