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


def test_ci_checks_v048_frontend_syntax_in_addition_to_existing_checks():
    assert "node --check src/comfyui_remote_panel/static/v048_ref2va_ui.js" in CI
    assert "node --check src/comfyui_remote_panel/static/i18n.js" in CI
    assert "node --check src/comfyui_remote_panel/static/v046_fl2va_ui.js" in CI
