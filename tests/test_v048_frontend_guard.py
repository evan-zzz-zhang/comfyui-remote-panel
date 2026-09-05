from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "comfyui_remote_panel" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_ref2va_uses_one_shared_advanced_owner():
    js = read("h3_ref2va_adapter.js")
    controller = read("h3_advanced_controller.js")
    assert 'family: "ref2va"' in js
    assert 'window.ComfyRemoteH3AdvancedSettings?.registerAdapter?.' in js
    assert 'modeLabels: ["原版", "LightX2V", "v4_600step"]' in js
    assert 'modelLabels: ["pruned_int8", "pruned_bf16"]' in js
    assert "new MutationObserver" not in js
    assert "ensureOllamaField" not in js
    assert "applyPreset = function" not in js
    assert "uploadForm = function" not in js
    assert "seedPolicy" in controller
    assert "referenceResolution" in controller


def test_ref2va_availability_and_routing_are_adapter_contracts():
    js = read("h3_ref2va_adapter.js")
    assert 'const item = state.workflowItems?.get?.(id);' in js
    assert 'item?.status === "enabled"' in js
    assert 'state.metrics?.presets?.[id]?.available === true' in js
    assert "function augmentFormData(formData, ui = {})" in js
    assert 'if (backend === "ollama") values.ollama_model' in js
    assert 'else delete values.ollama_model' in js


def test_ref2va_mode_and_storage_contract_is_family_specific():
    js = read("h3_ref2va_adapter.js")
    for contract in (
        'original: { scheduler: "simple", sampler: "res_multistep", steps: 20 }',
        'lightx2v: { scheduler: "simple", sampler: "euler", steps: 4 }',
        'v4step600: { scheduler: "beta", sampler: "euler", steps: 8 }',
    ):
        assert contract in js
    for key in (
        "comfy-remote.ref2va.generation-mode", "comfy-remote.ref2va.prompt-backend",
        "comfy-remote.ref2va.inference-profile", "comfy-remote.ref2va.ollama-model",
        "comfy-remote.ref2va.seed-policy",
    ):
        assert key in js


def test_shared_controller_contains_the_user_visible_labels():
    controller = read("h3_advanced_controller.js")
    assert "Ollama 标准化模型" in controller
    assert '["原始提示词", "Ollama 标准化", "Qwen3.5 标准化"]' in controller


def test_ci_checks_production_flow_and_controller_syntax():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "node tests/frontend_contract_smoke.js" in ci
    assert "node --check src/comfyui_remote_panel/static/h3_ref2va_adapter.js" in ci
