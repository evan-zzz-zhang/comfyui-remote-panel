from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "comfyui_remote_panel" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_h3_creation_ownership_is_moved_out_of_legacy_v042_asset():
    legacy = read("v042_ui.js")
    assert "applyPreset" not in legacy
    assert "MutationObserver" not in legacy
    assert "h3_creation_runtime.js" in legacy
    assert "h3_fl2va_adapter.js" in legacy


def test_fl2va_group_and_routing_live_in_the_dedicated_adapter():
    adapter = read("h3_fl2va_adapter.js")
    assert 'family: "fl2va"' in adapter
    assert 'name: "MiniMax H3 FL2VA"' in adapter
    assert 'function buildGroupPreset()' in adapter
    assert 'function augmentFormData(formData, ui = {})' in adapter
    assert "prompt_standardization_mode" in adapter
    assert 'values.ollama_model' in adapter


def test_shared_controller_is_the_single_h3_advanced_owner():
    controller = read("h3_advanced_controller.js")
    index = read("index.html")
    assert 'h3_advanced_controller.js' in index
    assert 'const ORDER = [' in controller
    for role in ("generation-mode", "prompt-backend", "main-model", "ollama-model", "scheduler", "sampler", "steps", "seed-policy", "seed-value", "reference-resolution"):
        assert f'"{role}"' in controller
    assert 'mount,' in controller
    assert 'unmount,' in controller


def test_legacy_task_detail_patch_has_no_creation_owner():
    patch = read("v042_patch.js")
    assert "addStandardizedPromptToTaskDetails" in patch
    assert "new MutationObserver" not in patch
