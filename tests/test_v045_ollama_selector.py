from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "comfyui_remote_panel" / "static"
JS = (STATIC / "v045_ollama_ui.js").read_text(encoding="utf-8")
CONTROLLER = (STATIC / "h3_advanced_controller.js").read_text(encoding="utf-8")
REF2VA = (STATIC / "v048_ref2va_ui.js").read_text(encoding="utf-8")


def test_ollama_ui_is_a_fetch_cache_service_only():
    assert 'fetch("/api/ollama/models"' in JS
    assert 'let modelsPromise = null' in JS
    assert 'modelsPromise = null' in JS
    assert 'window.H3OllamaModelService = {' in JS
    assert 'getModels: fetchModels' in JS
    assert 'document.createElement' not in JS
    assert 'MutationObserver' not in JS


def test_shared_controller_owns_the_final_ollama_select_for_both_families():
    assert 'function ensureOllamaField' in CONTROLLER
    assert 'document.createElement("select")' in CONTROLLER
    assert 'field.hidden = state.promptBackend !== "ollama"' in CONTROLLER
    assert 'H3OllamaModelService?.getModels?.()' in CONTROLLER
    assert 'comfy-remote.ref2va.ollama-model' in REF2VA


def test_generation_summary_remains_independent_of_ollama_dom_ownership():
    patch = (STATIC / "v042_patch.js").read_text(encoding="utf-8")
    assert 'function syncGenerationSettingsSummary()' in patch
    assert '#settings-chips' in patch
    assert 'new MutationObserver' not in patch
