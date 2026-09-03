from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "src" / "comfyui_remote_panel" / "static" / "v048_ref2va_ui.js").read_text(encoding="utf-8")
CREATION_JS = (ROOT / "src" / "comfyui_remote_panel" / "static" / "configurator_v2_runtime.js").read_text(encoding="utf-8")
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")


def test_ref2va_availability_uses_the_same_runtime_contract_for_all_backends():
    assert "const target = state.workflowItems?.get?.(targetId(mode, backend));" in JS
    assert "target.status === \"enabled\"" in JS
    assert "state.metrics?.presets?.[target.id]?.available === true" in JS
    assert "const available = Boolean(" in JS
    assert "const unavailable = backend === \"qwen35\"" not in JS


def test_ref2va_availability_restores_base_submit_state_after_qwen_to_raw_switch():
    assert "const baseUpdateSubmitAvailability = updateSubmitAvailability;" in JS
    assert "updateSubmitAvailability = function(...args)" in JS
    assert "submit.dataset.v048Ref2vaAvailability = \"unavailable\"" in JS
    assert "submit.disabled = baseDisabled;" in JS
    assert "baseUpdateSubmitAvailability(...args);" in JS
    assert "isSubmitting and other workflow guards keep" in JS


def test_ref2va_dom_fields_are_removed_when_leaving_virtual_entry():
    assert "function removeRef2vaFields()" in JS
    assert "[data-v048-ref2va-generation-mode-field]" in JS
    assert "[data-v048-ref2va-prompt-backend-field]" in JS
    assert "[data-v048-ref2va-inference-profile-field]" in JS
    assert "[data-v048-ref2va-ollama-model-field]" in JS
    assert ".forEach(field => field.remove());" in JS
    assert "if (!selectedRef2va()) {" in JS
    assert "removeRef2vaFields();" in JS
    assert '"[data-v047-inference-profile-field]"' not in JS
    assert '.observe(grid, { childList: true })' in JS
    assert 'new MutationObserver(() => queueMicrotask(() => ensureRef2vaFields()))' in JS
    assert 'window.ComfyRemoteCreationControls?.normalize?.(grid)' in JS
    assert '.observe(grid, { childList: true, subtree: true })' not in JS


def test_ref2va_explicit_retry_mode_precedes_local_storage_and_recreates_fields():
    assert "const normalizedExplicit = normalize(explicit);" in JS
    assert "valid(normalizedExplicit, values)" in JS
    assert "valid(live, values)" in JS
    assert ": remembered(storageKey, values, fallback);" in JS
    assert 'ensureRef2vaFields(overrides);' in JS
    assert 'applyPreset = function(presetId, overrides = {})' in JS
    assert 'selectedPreset()?.id === ENTRY_ID' in JS
    assert 'const STORAGE_MODE = "comfy-remote.ref2va.generation-mode"' in JS
    assert 'const STORAGE_BACKEND = "comfy-remote.ref2va.prompt-backend"' in JS
    assert 'const STORAGE_PROFILE = "comfy-remote.ref2va.inference-profile"' in JS


def test_ref2va_uses_consistent_chinese_labels_two_model_choices_and_field_order():
    assert '"生成模式"' in JS
    assert '["v4_600step", "LightX2V", "原版"]' in JS
    assert '"标准化提示词"' in JS
    assert '["原始提示词", "Ollama 标准化", "Qwen3.5 标准化"]' in JS
    assert '"主模型"' in JS
    assert 'const PROFILES = ["int8", "fp16_bf16"]' in JS
    assert '["pruned_int8", "pruned_bf16"]' in JS
    assert 'const DEFAULT_PROFILE = "int8"' in JS
    assert 'return profile === "auto" ? "int8" : profile' in JS
    assert 'window.ComfyRemoteCreationControls?.normalize?.(grid)' in JS
    assert 'CreationControls.normalize = normalizeH3AdvancedLayout' in CREATION_JS
    assert '"generation-mode", "prompt-backend", "main-model", "ollama-model"' in CREATION_JS
    for stale in ('"Generation Mode"', '"Prompt Backend"', '"Model Configuration"'):
        assert stale not in JS


def test_ref2va_mode_defaults_and_retry_tuning_priority_are_explicit():
    for contract in (
        'original: { scheduler: "simple", sampler: "res_multistep", steps: 20 }',
        'lightx2v: { scheduler: "simple", sampler: "euler", steps: 4 }',
        'v4step600: { scheduler: "beta", sampler: "euler", steps: 8 }',
    ):
        assert contract in JS
    assert 'const hasExplicitTuning = ["scheduler", "sampler", "steps"].some(' in JS
    assert 'presetId === ENTRY_ID && !hasExplicitTuning' in JS
    assert 'applyModeDefaults(mode.value);' in JS


def test_ref2va_ollama_model_is_scoped_visible_and_submitted_only_for_ollama():
    assert 'const STORAGE_OLLAMA_MODEL = "comfy-remote.ref2va.ollama-model"' in JS
    assert 'data-v048-ref2va-ollama-model-field' in JS
    assert 'field.dataset.ollamaStorageKey = STORAGE_OLLAMA_MODEL' in JS
    assert 'field.hidden = backend !== "ollama"' in JS
    assert 'candidate(overrides, "ollama_model", null)' in JS
    assert 'if (backend === "ollama") values.ollama_model = ollamaModel' in JS
    assert 'else delete values.ollama_model' in JS
    assert 'data-v045-ollama-model>' in JS
    assert 'name="ollama_model"' not in JS


def test_ref2va_routing_reads_ollama_model_and_exposes_executable_hook():
    assert 'const {mode, backend, profile, ollamaModel} = currentRef2vaValues();' in JS
    assert 'addRouting: addRef2vaRouting' in JS


def test_ref2va_seed_policy_reuses_shared_contract_with_family_isolation_and_retry_priority():
    assert 'window.ComfyRemoteCreationControls?.install?.(group(), overrides)' in JS
    assert 'comfy-remote.ref2va.seed-policy' in CREATION_JS
    assert 'comfy-remote.fl2va.seed-policy' in CREATION_JS
    assert 'const explicit = overrides?.seed_policy ?? overrides?.values?.seed_policy' in CREATION_JS
    assert 'if (validSeedPolicy(explicit)) return explicit' in CREATION_JS
    assert 'if (validSeedPolicy(live)) return live' in CREATION_JS
    assert 'return rememberedSeedPolicy(preset) || preset?.seed_policy?.default || "randomize"' in CREATION_JS
    assert '<select data-v04-seed-policy>' in CREATION_JS
    assert 'name="seed_policy"' not in CREATION_JS


def test_ci_checks_v048_frontend_syntax_in_addition_to_existing_checks():
    assert "node --check src/comfyui_remote_panel/static/v048_ref2va_ui.js" in CI
    assert "node --check src/comfyui_remote_panel/static/i18n.js" in CI
    assert "node --check src/comfyui_remote_panel/static/v046_fl2va_ui.js" in CI
    assert "node tests/frontend_contract_smoke.js" in CI
