from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "comfyui_remote_panel" / "static"
JS = (STATIC / "v046_fl2va_ui.js").read_text(encoding="utf-8")
CONTROLLER = (STATIC / "h3_advanced_controller.js").read_text(encoding="utf-8")
V042 = (STATIC / "v042_ui.js").read_text(encoding="utf-8")
V045 = (STATIC / "v045_ollama_ui.js").read_text(encoding="utf-8")
V048 = (STATIC / "v048_ref2va_ui.js").read_text(encoding="utf-8")
RUNTIME = (STATIC / "v046_job_runtime_ui.js").read_text(encoding="utf-8")


def test_fl2va_registers_the_shared_adapter_contract():
    assert 'family: "fl2va"' in JS
    assert 'modeValues: ["original", "lightx2v", "v4_600step"]' in JS
    assert 'modeLabels: ["原版", "LightX2V", "v4_600step"]' in JS
    assert 'modelLabels: ["pruned_int8", "pruned_bf16"]' in JS
    assert 'onRender: syncMainModelAvailability' in JS
    assert 'window.ComfyRemoteH3AdvancedSettings?.registerAdapter?.' in JS


def test_fl2va_has_no_second_advanced_dom_owner_or_advanced_observer():
    for stale in (
        "ensureStandardizationSelector", "ensureInferenceProfileSelector", "ensureInferenceProfileSelector",
        "normalizeLegacyStandardizerControls", "installLegacyGuardStyle", "advancedGrid",
        "data-v046-prompt-standardization-mode", "data-v047-inference-profile-field",
        "data-v045-ollama-model-field", "new MutationObserver",
    ):
        assert stale not in JS
    assert 'const baseApplyPreset = applyPreset;' in JS
    assert 'queueMicrotask(() => {' in JS
    assert 'removePhysicalCreationChoices();' in JS


def test_fl2va_keeps_aspect_compatibility_and_canonical_routing():
    assert 'function ensureFl2vaReferenceAspectOption()' in JS
    assert 'reference.value = "reference"' in JS
    assert 'const DEFAULT_ASPECT = "9:16"' in JS
    assert 'function addStandardizationMode(formData)' in JS
    assert 'values.prompt_backend = backend' in JS
    assert 'values.prompt_standardization_mode = backend === "raw" ? "off" : backend === "qwen35" ? "comfyui" : "ollama"' in JS
    assert 'values.inference_profile = ui.mainModel' in JS
    assert 'values.ollama_model = ollamaModel' in V042


def test_fl2va_preserves_mode_tuning_and_retry_priority():
    for contract in (
        'original: { scheduler: "simple", sampler: "res_multistep", steps: 20 }',
        'lightx2v: { scheduler: "simple", sampler: "euler", steps: 8 }',
        'v4_600step: { scheduler: "beta", sampler: "euler", steps: 8 }',
    ):
        assert contract in JS
    assert 'const hasExplicitTuning' not in JS
    assert 'const previous = activeState?.family === adapter.family' in CONTROLLER
    assert 'const explicitBackendValue' in CONTROLLER
    assert 'candidate(overrides, "seed_value", "seed")' in CONTROLLER


def test_ollama_is_a_service_and_shared_controller_consumes_it():
    assert 'fetch("/api/ollama/models"' in V045
    assert 'window.H3OllamaModelService = {' in V045
    assert 'getModels: fetchModels' in V045
    assert 'document.createElement("select")' not in V045
    assert 'H3OllamaModelService?.getModels?.()' in CONTROLLER


def test_runtime_ui_still_keeps_generation_timing_contract():
    for fragment in (
        'job.queue_elapsed_seconds', 'job.execution_elapsed_seconds ?? job.elapsed_seconds',
        'job.generation_elapsed_seconds', '标准化提示词', '采样', '总生成',
    ):
        assert fragment in RUNTIME


def test_ref2va_is_also_registered_as_a_shared_adapter():
    assert 'family: "ref2va"' in V048
    assert 'modeValues: ["original", "lightx2v", "v4step600"]' in V048
    assert 'onRender: syncMainModelAvailability' in V048
    assert 'new MutationObserver' not in V048


def test_ci_checks_controller_and_production_flow():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "node --check src/comfyui_remote_panel/static/h3_advanced_controller.js" in ci
    assert "node tests/frontend_contract_smoke.js" in ci
