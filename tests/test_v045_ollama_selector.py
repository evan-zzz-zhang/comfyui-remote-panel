from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "comfyui_remote_panel" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_ollama_service_is_fetch_cache_only():
    service = read("h3_ollama_service.js")
    assert 'fetch("/api/ollama/models"' in service
    assert "modelsPromise = null" in service
    assert "window.H3OllamaModelService" in service
    assert "document.createElement" not in service
    assert "MutationObserver" not in service


def test_legacy_ollama_asset_has_no_second_service_or_dom_owner():
    legacy = read("v045_ollama_ui.js")
    assert "fetch(" not in legacy
    assert "MutationObserver" not in legacy
    assert "document.createElement" not in legacy


def test_shared_controller_owns_the_final_ollama_select_for_both_families():
    controller = read("h3_advanced_controller.js")
    ref2va = read("h3_ref2va_adapter.js")
    assert "function ensureOllamaField" in controller
    assert 'document.createElement("select")' in controller
    assert 'field.hidden = state.promptBackend !== "ollama"' in controller
    assert "H3OllamaModelService?.getModels?.()" in controller
    assert "comfy-remote.ref2va.ollama-model" in ref2va


def test_generation_summary_remains_independent_of_ollama_dom_ownership():
    patch = read("v042_patch.js")
    assert "syncGenerationSettingsSummary" in patch
    assert "#settings-chips" in patch
    assert "new MutationObserver" not in patch
