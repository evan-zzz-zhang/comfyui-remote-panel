from pathlib import Path

import pytest

from comfyui_remote_panel.inference_profile import resolve_inference_profile
from comfyui_remote_panel.preset import load_presets
from comfyui_remote_panel.workflow_registry import (
    CANONICAL_FL2VA_ASSET_IDS,
    CANONICAL_REF2VA_ASSET_IDS,
    WorkflowAssetKey,
    asset_key,
    list_fl2va_assets,
    ref2va_asset_key,
    resolve_fl2va_asset,
)


ROOT = Path(__file__).resolve().parents[1]


def test_registry_contains_exactly_nine_canonical_fl2va_assets():
    presets = load_presets(ROOT / "workflows")
    assets = list_fl2va_assets(presets)
    assert {asset.id for asset in assets} == CANONICAL_FL2VA_ASSET_IDS
    assert len(assets) == 9
    assert all(asset.manifest["family"] == "fl2va" for asset in assets)
    assert all(asset.manifest["output_node"] == "92" for asset in assets)
    assert all(asset.manifest["input_bindings"]["media"]["type"] in {"frame_pair", "slots"} for asset in assets)
    assert all(
        asset.manifest["prompt_capture"].get("available") is False
        if asset.manifest["prompt_backend"] == "raw"
        else asset.manifest["prompt_capture"].get("history_node")
        for asset in assets
    )


@pytest.mark.parametrize("generation_mode", ["original", "v4step600", "lightx2v"])
@pytest.mark.parametrize("prompt_backend", ["raw", "ollama", "qwen35"])
def test_registry_resolves_every_family_combination(generation_mode, prompt_backend):
    presets = load_presets(ROOT / "workflows")
    asset = resolve_fl2va_asset(
        presets,
        family="FL2VA",
        generation_mode=generation_mode,
        prompt_backend=prompt_backend,
    )
    assert asset.id == f"fl2va_{generation_mode}_{prompt_backend}"


def test_auto_profile_resolves_to_current_int8_without_changing_graph():
    preset = load_presets(ROOT / "workflows")["fl2va_original_raw"]
    assert resolve_inference_profile(preset, "auto") == ("auto", "int8")
    assert resolve_inference_profile(preset, "int8") == ("int8", "int8")
    assert preset.manifest["model_profile"]["main_model"]["variants"]["int8"]["dependencies"][0]["name"].endswith(
        "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
    )


def test_fl2va_bf16_is_declared_for_every_real_unet_loader():
    presets = load_presets(ROOT / "workflows")
    for preset_id in CANONICAL_FL2VA_ASSET_IDS:
        preset = presets[preset_id]
        assert resolve_inference_profile(preset, "fp16_bf16") == (
            "fp16_bf16", "fp16_bf16"
        )
        dependency = preset.manifest["model_profile"]["main_model"]["variants"][
            "fp16_bf16"
        ]["dependencies"][0]
        assert dependency["category"] == "diffusion_models"
        assert dependency["name"] == (
            "MiniMax-H3/minimax_h3_fl2va_pruned_bf16.safetensors"
        )
        assert dependency["input"] == "unet_name"
        assert preset.template[dependency["node"]]["class_type"] == "UNETLoader"


def test_fl2va_int8_stays_unchanged_and_bf16_keeps_exact_runtime_selector():
    preset = load_presets(ROOT / "workflows")["fl2va_original_raw"]
    values = {
        name: spec.get("default")
        for name, spec in preset.manifest["parameters"].items()
    }
    values.update({"prompt": "A test shot", "seed": "1"})
    int8 = preset.build_prompt(
        {**values, "_v047_effective_inference_profile": "int8"}, "int8-job", {}
    )
    assert int8["105:6"]["inputs"]["unet_name"] == (
        r"MiniMax-H3\minimax_h3_fl2va_pruned_int8_convrot.safetensors"
    )

    runtime_selector = r"MiniMax-H3\minimax_h3_fl2va_pruned_bf16.safetensors"
    bf16 = preset.build_prompt(
        {**values, "_v047_effective_inference_profile": "fp16_bf16"},
        "bf16-job",
        {},
        {"105:6": {"unet_name": runtime_selector}},
    )
    assert bf16["105:6"]["inputs"]["unet_name"] == runtime_selector


def test_declared_variant_changes_the_bound_model_node():
    """The graph binding path is covered independently of local model availability."""
    preset = load_presets(ROOT / "workflows")["fl2va_original_raw"]
    preset.manifest["model_profile"]["main_model"]["variants"]["fp16_bf16"] = {
        "available": True,
        "dependencies": [{
            "category": "diffusion_models",
            "name": "MiniMax-H3/test_fl2va_variant.safetensors",
            "node": "105:6",
            "input": "unet_name",
        }],
    }
    values = {
        name: spec.get("default")
        for name, spec in preset.manifest["parameters"].items()
    }
    values.update({
        "prompt": "A test shot",
        "seed": "1",
        "_v047_effective_inference_profile": "fp16_bf16",
    })
    graph = preset.build_prompt(values, "variant-job", {})
    assert graph["105:6"]["inputs"]["unet_name"] == "MiniMax-H3/test_fl2va_variant.safetensors"


def test_ref2va_asset_key_reads_all_nine_canonical_assets_without_changing_fl2va_key():
    presets = load_presets(ROOT / "workflows")
    ref2va_assets = {
        preset.id: ref2va_asset_key(preset)
        for preset in presets.values()
        if preset.id in CANONICAL_REF2VA_ASSET_IDS
    }
    assert len(ref2va_assets) == 9
    for preset_id, key in ref2va_assets.items():
        mode, backend = preset_id.removeprefix("ref2va_").split("_", 1)
        assert key == WorkflowAssetKey("ref2va", mode, backend)

    fl2va = presets["fl2va_original_raw"]
    assert asset_key(fl2va) == WorkflowAssetKey("fl2va", "original", "raw")
    assert asset_key(presets["h3-ref2va"]) is None
