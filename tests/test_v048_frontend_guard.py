from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JS = (ROOT / "src" / "comfyui_remote_panel" / "static" / "v048_ref2va_ui.js").read_text(encoding="utf-8")
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
    assert ".forEach(field => field.remove());" in JS
    assert "if (!selectedRef2va()) {" in JS
    assert "removeRef2vaFields();" in JS
    assert '"[data-v047-inference-profile-field]"' not in JS
    assert '.observe(grid, { childList: true })' in JS
    assert '.observe(grid, { childList: true, subtree: true })' not in JS


def test_ref2va_explicit_retry_mode_precedes_local_storage_and_recreates_fields():
    assert 'const next = valid(explicit, values) ? String(explicit).toLowerCase() : remembered(storageKey, values, fallback);' in JS
    assert 'ensureRef2vaFields(overrides);' in JS
    assert 'applyPreset = function(presetId, overrides = {})' in JS
    assert 'selectedPreset()?.id === ENTRY_ID' in JS
    assert 'const STORAGE_MODE = "comfy-remote.ref2va.generation-mode"' in JS
    assert 'const STORAGE_BACKEND = "comfy-remote.ref2va.prompt-backend"' in JS
    assert 'const STORAGE_PROFILE = "comfy-remote.ref2va.inference-profile"' in JS


def test_ci_checks_v048_frontend_syntax_in_addition_to_existing_checks():
    assert "node --check src/comfyui_remote_panel/static/v048_ref2va_ui.js" in CI
    assert "node --check src/comfyui_remote_panel/static/i18n.js" in CI
    assert "node --check src/comfyui_remote_panel/static/v046_fl2va_ui.js" in CI
