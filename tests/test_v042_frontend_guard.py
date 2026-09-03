from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "comfyui_remote_panel" / "static"
JS = (STATIC / "v042_ui.js").read_text(encoding="utf-8")
CONTROLLER = (STATIC / "h3_advanced_controller.js").read_text(encoding="utf-8")
PATCH = (STATIC / "v042_patch.js").read_text(encoding="utf-8")
INDEX = (STATIC / "index.html").read_text(encoding="utf-8")


def test_fl2va_compatibility_wrapper_does_not_own_advanced_dom():
    assert 'const ENTRY_ID = "h3-fl2va-group"' in JS
    assert 'const DEFAULT_MODE = "v4_600step"' in JS
    assert 'comfy-remote.fl2va.generation-mode' in JS
    assert 'applyPreset = function(presetId, overrides = {})' in JS
    for stale in ("ensureControls", "removeControls", "installToggleStyle", "data-v042-mode-field", "data-v042-standardizer-field"):
        assert stale not in JS


def test_shared_controller_is_the_single_h3_advanced_owner():
    assert 'h3_advanced_controller.js' in INDEX
    assert 'const ORDER = [' in CONTROLLER
    for role in ("generation-mode", "prompt-backend", "main-model", "ollama-model", "scheduler", "sampler", "steps", "seed-policy", "seed-value", "reference-resolution"):
        assert f'"{role}"' in CONTROLLER
    assert 'window.ComfyRemoteH3AdvancedSettings = {' in CONTROLLER
    assert 'registerAdapter: register' in CONTROLLER
    assert 'window.syncH3CreationUI = syncH3CreationUI' in CONTROLLER
    assert 'getState,' in CONTROLLER


def test_fl2va_mode_tuning_and_backend_routing_remain_explicit():
    fl2va = (STATIC / "v046_fl2va_ui.js").read_text(encoding="utf-8")
    for contract in (
        'original: { scheduler: "simple", sampler: "res_multistep", steps: 20 }',
        'lightx2v: { scheduler: "simple", sampler: "euler", steps: 8 }',
        'v4_600step: { scheduler: "beta", sampler: "euler", steps: 8 }',
    ):
        assert contract in fl2va
    assert 'values.prompt_standardization_mode = backend === "raw" ? "off" : backend === "qwen35" ? "comfyui" : "ollama"' in fl2va
    assert 'values.ollama_model = ollamaModel' in JS


def test_standardized_prompt_patch_only_keeps_task_detail_behavior():
    assert 'job?.standardized_prompt' in PATCH
    assert 'addStandardizedPromptToTaskDetails' in PATCH
    assert 'data-task-details' in PATCH
    assert 'new MutationObserver' not in PATCH
    assert 'data-v042-standardizer-field' not in PATCH


def test_v042_keeps_physical_workflow_compatibility_without_advanced_observer():
    assert 'function hidePhysicalWorkflowChoices()' in JS
    assert 'physicalPresetIds()' in JS
    assert '.observe(sheet, { childList: true })' in JS
    assert '.observe(advanced' not in JS


def test_retry_and_upload_paths_use_shared_state():
    assert 'const ui = window.ComfyRemoteH3AdvancedSettings?.getState?.() || {}' in JS
    assert 'values.generation_mode = mode' in JS
    assert 'values.prompt_standardization = standardize' in JS
    assert 'formData.set("values_json", JSON.stringify(values))' in JS


def test_ci_runs_production_flow_and_controller_syntax_checks():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "node --check src/comfyui_remote_panel/static/h3_advanced_controller.js" in ci
    assert "node tests/frontend_contract_smoke.js" in ci
