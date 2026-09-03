from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "comfyui_remote_panel" / "static"
JS = (STATIC / "v048_ref2va_ui.js").read_text(encoding="utf-8")
CONTROLLER = (STATIC / "h3_advanced_controller.js").read_text(encoding="utf-8")
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def test_ref2va_uses_one_shared_advanced_owner():
    assert 'family: "ref2va"' in JS
    assert 'window.ComfyRemoteH3AdvancedSettings?.registerAdapter?.' in JS
    assert 'modeLabels: ["原版", "LightX2V", "v4_600step"]' in JS
    assert 'modelLabels: ["pruned_int8", "pruned_bf16"]' in JS
    for stale in (
        "ensureRef2vaFields", "removeRef2vaFields", "ensureOllamaField", "applyModeDefaults",
        "data-v048-ref2va-generation-mode-field", "data-v048-ref2va-prompt-backend-field",
        "data-v048-ref2va-ollama-model-field", "data-v048-ref2va-inference-profile-field",
        "new MutationObserver",
    ):
        assert stale not in JS
    assert 'const baseApply = applyPreset;' in JS


def test_ref2va_availability_keeps_the_same_runtime_contract_for_all_backends():
    assert 'const target = state.workflowItems?.get?.(targetId(mode, backend));' in JS
    assert 'target.status === "enabled"' in JS
    assert 'state.metrics?.presets?.[target.id]?.available === true' in JS
    assert 'const available = Boolean(' in JS


def test_ref2va_routing_omits_ollama_model_except_for_ollama_backend():
    assert 'const { mode, backend, profile, ollamaModel } = currentRef2vaValues();' in JS
    assert 'addRouting: addRef2vaRouting' in JS
    assert 'if (backend === "ollama") values.ollama_model = ollamaModel;' in JS
    assert 'else delete values.ollama_model;' in JS
    assert 'window.ComfyRemoteH3AdvancedSettings?.getState?.()' in JS


def test_ref2va_mode_tuning_and_retry_values_are_shared():
    for contract in (
        'original: { scheduler: "simple", sampler: "res_multistep", steps: 20 }',
        'lightx2v: { scheduler: "simple", sampler: "euler", steps: 4 }',
        'v4step600: { scheduler: "beta", sampler: "euler", steps: 8 }',
    ):
        assert contract in JS
    assert 'modeTuning: mode => MODE_TUNING[canonicalMode(mode)]' in JS
    assert 'const hasExplicitTuning' not in JS
    assert '...MODE_TUNING[mode]' not in JS
    assert 'seedPolicy' in CONTROLLER
    assert 'referenceResolution' in CONTROLLER


def test_ref2va_storage_keys_and_labels_are_family_specific_but_ui_contract_is_shared():
    for key in (
        'comfy-remote.ref2va.generation-mode', 'comfy-remote.ref2va.prompt-backend',
        'comfy-remote.ref2va.inference-profile', 'comfy-remote.ref2va.ollama-model',
        'comfy-remote.ref2va.seed-policy',
    ):
        assert key in JS
    assert 'Ollama 标准化模型' in CONTROLLER
    assert '["原始提示词", "Ollama 标准化", "Qwen3.5 标准化"]' in CONTROLLER


def test_ci_checks_production_flow_and_controller_syntax():
    assert "node --check src/comfyui_remote_panel/static/h3_advanced_controller.js" in CI
    assert "node tests/frontend_contract_smoke.js" in CI
