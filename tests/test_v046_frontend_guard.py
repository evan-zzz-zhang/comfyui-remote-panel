from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "src" / "comfyui_remote_panel" / "static"


def read(name: str) -> str:
    return (STATIC / name).read_text(encoding="utf-8")


def test_fl2va_adapter_registers_the_shared_contract():
    js = read("h3_fl2va_adapter.js")
    assert 'family: "fl2va"' in js
    assert 'modeValues: ["original", "lightx2v", "v4_600step"]' in js
    assert 'modeLabels: ["原版", "LightX2V", "v4_600step"]' in js
    assert 'modelLabels: ["pruned_int8", "pruned_bf16"]' in js
    assert 'window.ComfyRemoteH3AdvancedSettings?.registerAdapter?.' in js
    assert 'window.H3CreationRuntime?.registerAdapter?.' in js


def test_fl2va_adapter_has_no_advanced_dom_owner_or_observer():
    js = read("h3_fl2va_adapter.js")
    assert "new MutationObserver" not in js
    assert "ensureStandardizationSelector" not in js
    assert "data-v047-inference-profile-field" not in js
    assert "applyPreset = function" not in js
    assert "uploadForm = function" not in js


def test_fl2va_keeps_mode_tuning_and_routing_in_adapter():
    js = read("h3_fl2va_adapter.js")
    for contract in (
        'original: { scheduler: "simple", sampler: "res_multistep", steps: 20 }',
        'lightx2v: { scheduler: "simple", sampler: "euler", steps: 8 }',
        'v4_600step: { scheduler: "beta", sampler: "euler", steps: 8 }',
    ):
        assert contract in js
    assert "prompt_standardization_mode" in js


def test_ollama_is_a_service_consumed_by_shared_controller():
    service = read("h3_ollama_service.js")
    controller = read("h3_advanced_controller.js")
    assert 'fetch("/api/ollama/models"' in service
    assert 'window.H3OllamaModelService' in service
    assert 'H3OllamaModelService?.getModels?.()' in controller


def test_runtime_ui_timing_contract_remains_loaded_separately():
    runtime = read("v046_job_runtime_ui.js")
    for fragment in ('job.queue_elapsed_seconds', 'job.execution_elapsed_seconds ?? job.elapsed_seconds', 'job.generation_elapsed_seconds', '标准化提示词', '采样', '总生成'):
        assert fragment in runtime


def test_ref2va_is_registered_by_its_dedicated_adapter():
    js = read("h3_ref2va_adapter.js")
    assert 'family: "ref2va"' in js
    assert 'modeValues: ["original", "lightx2v", "v4step600"]' in js
    assert 'modeLabels: ["原版", "LightX2V", "v4_600step"]' in js
    assert "new MutationObserver" not in js


def test_ci_checks_all_h3_production_modules():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    for name in ("h3_advanced_controller.js", "h3_ollama_service.js", "h3_creation_runtime.js", "h3_fl2va_adapter.js", "h3_ref2va_adapter.js"):
        assert f"node --check src/comfyui_remote_panel/static/{name}" in ci
