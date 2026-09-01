from pathlib import Path

import pytest

from comfyui_remote_panel.inference_profile import (
    InferenceProfileError,
    resolve_inference_profile,
)
from comfyui_remote_panel.preset import load_presets
from comfyui_remote_panel.workflow_registry import (
    CANONICAL_FL2VA_ASSET_IDS,
    list_fl2va_assets,
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


def test_unavailable_explicit_profile_is_rejected_instead_of_falling_back():
    preset = load_presets(ROOT / "workflows")["fl2va_original_raw"]
    with pytest.raises(InferenceProfileError, match="未声明可用"):
        resolve_inference_profile(preset, "fp16_bf16")
