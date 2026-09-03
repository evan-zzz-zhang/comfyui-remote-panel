from __future__ import annotations

from pathlib import Path

import pytest

from comfyui_remote_panel.app import create_app
from comfyui_remote_panel.config import Config


ROOT = Path(__file__).resolve().parents[1]
LOGIN = {"Tailscale-User-Login": "owner@example.com"}
JS = (ROOT / "src" / "comfyui_remote_panel" / "static" / "v046_fl2va_ui.js").read_text(encoding="utf-8")
RUNTIME_JS = (ROOT / "src" / "comfyui_remote_panel" / "static" / "v046_job_runtime_ui.js").read_text(encoding="utf-8")
V042_PATCH_JS = (ROOT / "src" / "comfyui_remote_panel" / "static" / "v042_patch.js").read_text(encoding="utf-8")


def _config(tmp_path: Path) -> Config:
    return Config(
        host="127.0.0.1",
        port=8190,
        public_origin="https://device.example.ts.net",
        allowed_logins=("owner@example.com",),
        comfyui_base_url="http://127.0.0.1:1",
        comfyui_input_dir=tmp_path / "comfy-input",
        comfyui_output_dir=tmp_path / "comfy-output",
        minimum_comfyui_version="0.26.0",
        data_dir=tmp_path / "data",
        workflow_dir=ROOT / "workflows",
        monitoring_interval=60,
        nvidia_smi_timeout=.1,
    )


@pytest.mark.asyncio
async def test_root_injects_v046_frontend_once(tmp_path, aiohttp_client):
    client = await aiohttp_client(create_app(_config(tmp_path)))
    response = await client.get("/", headers=LOGIN)
    assert response.status == 200
    html = await response.text()
    fl2va_tag = '<script src="/static/v046_fl2va_ui.js?v=0.4.8.2" defer></script>'
    runtime_tag = '<script src="/static/v046_job_runtime_ui.js?v=0.4.8.1" defer></script>'
    assert html.count(fl2va_tag) == 1
    assert html.count(runtime_tag) == 1
    assert html.index("v045_ollama_ui.js") < html.index("v046_fl2va_ui.js")
    assert html.index("v046_fl2va_ui.js") < html.index("v046_job_runtime_ui.js")
    assert callable(getattr(client.app["lifecycle"], "_v046_jobs_offline_callback", None))


def test_v046_frontend_replaces_visible_boolean_with_three_state_selector():
    assert 'data-v046-prompt-standardization-mode' in JS
    assert 'option("raw", "原始提示词")' in JS
    assert 'option("ollama", "Ollama 标准化")' in JS
    assert 'option("qwen35", "Qwen3.5 标准化")' in JS
    assert 'label.textContent = "标准化提示词"' in JS
    assert 'normalizeLegacyStandardizerControls' in JS
    assert 'advanced.querySelectorAll(".v042-switch").forEach(node => node.remove())' in JS
    assert 'advanced.querySelectorAll("[data-v042-standardizer-switch]").forEach(node => node.remove())' in JS
    assert 'for (const duplicate of fields.slice(1)) duplicate.remove()' in JS
    assert 'compatibility.hidden = true' in JS
    assert 'compatibility.style.setProperty("display", "none", "important")' in JS
    assert '#advanced-settings .v042-switch' in JS
    assert '#advanced-settings [data-v042-prompt-standardization]' in JS
    assert '#advanced-settings [data-v042-standardizer-switch]' in JS
    assert 'comfy-remote.fl2va.prompt-standardization-mode' in JS
    assert 'const DEFAULT_MODE = "ollama"' in JS


def test_inference_profile_uses_a_select_only_selector_and_hides_all_physical_assets():
    assert 'data-v047-inference-profile-field' in JS
    assert 'label.dataset.v047InferenceProfileField = "true"' in JS
    assert 'select.dataset.v047InferenceProfile = "true"' in JS
    assert 'select.name = "inference_profile"' not in JS
    assert 'values.inference_profile = profile' in JS
    assert 'function removeInferenceProfileSelector()' in JS
    assert 'removeInferenceProfileSelector();' in JS
    assert 'document.querySelector("select[data-v047-inference-profile]")' in JS
    assert 'const PROFILES = ["int8", "fp16_bf16"]' in JS
    assert 'option("int8", "pruned_int8")' in JS
    assert 'option("fp16_bf16", "pruned_bf16")' in JS
    assert 'option("auto", "自动")' not in JS
    assert 'label.innerHTML = "<span>主模型</span>"' in JS
    assert 'return profile === "auto" ? "int8" : profile' in JS
    assert 'const CANONICAL_FL2VA_PRESET_IDS = new Set([' in JS
    for preset_id in (
        "fl2va_original_raw", "fl2va_original_ollama", "fl2va_original_qwen35",
        "fl2va_v4step600_raw", "fl2va_v4step600_ollama", "fl2va_v4step600_qwen35",
        "fl2va_lightx2v_raw", "fl2va_lightx2v_ollama", "fl2va_lightx2v_qwen35",
    ):
        assert f'"{preset_id}"' in JS


def test_v046_retry_preserves_explicit_standardizer_mode_after_observer_sync():
    assert 'const candidate = modeFromOverrides(overrides)' in JS
    assert 'const existingMode = validMode(select?.value) ? String(select.value).toLowerCase() : null' in JS
    assert 'const mode = preferredMode(candidate ?? existingMode)' in JS
    assert 'later MutationObserver passes must preserve the live selector value' in JS
    assert 'PROFILES.includes(explicit) ? explicit : PROFILES.includes(live) ? live : ""' in JS


def test_v042_patch_does_not_recreate_toggle_after_v046_selector_exists():
    assert 'const V046_SELECTOR = "[data-v046-prompt-standardization-mode]"' in V042_PATCH_JS
    assert 'if (field.querySelector(V046_SELECTOR))' in V042_PATCH_JS
    assert 'field.querySelectorAll("[data-v042-standardizer-switch]").forEach(button => button.remove())' in V042_PATCH_JS


def test_v046_frontend_keeps_fl2va_reference_aspect_visible():
    assert 'function ensureFl2vaReferenceAspectOption()' in JS
    assert 'reference.id = "reference-aspect-image-option"' in JS
    assert 'reference.value = "reference"' in JS
    assert 'reference.hidden = false' in JS
    assert 'reference.disabled = false' in JS
    assert 'event.target.closest?.("#open-generation-settings")' in JS
    assert 'event.target?.matches?.("#first-frame, #last-frame")' in JS


def test_v046_frontend_defaults_unselected_fl2va_aspect_to_9_16():
    assert 'const DEFAULT_ASPECT = "9:16"' in JS
    assert 'function syncFl2vaAspectValue(candidate = null, previous = "", preservePrevious = false)' in JS
    assert 'if (!next || !available.has(next)) next = DEFAULT_ASPECT' in JS
    assert 'if (!select.value || !available.has(select.value)) select.value = DEFAULT_ASPECT' in JS
    assert 'const explicitAspect = aspectFromOverrides(overrides)' in JS
    assert 'syncFl2vaAspectValue(explicitAspect, previousAspect, preservePreviousAspect)' in JS
    assert 'select.dataset.v046AspectExplicit = "true"' in JS


def test_v046_frontend_keeps_ollama_selector_only_for_ollama_and_hides_physical_presets():
    assert 'field.style.display = canonicalMode(mode) === "ollama" ? "" : "none"' in JS
    assert 'h3-fl2va-qwen35-4b' in JS
    assert 'h3-fl2va-lightx2v-qwen35-4b' in JS
    assert 'h3-fl2va-v4step600-qwen35-4b' in JS
    assert 'removePhysicalCreationChoices' in JS
    assert 'PHYSICAL_FL2VA_PRESET_IDS.has(item.value)' in JS
    assert 'PHYSICAL_FL2VA_PRESET_IDS.has(button.dataset.pickWorkflow)' in JS


def test_fl2va_observers_are_scoped_away_from_reference_media_updates():
    v042 = (ROOT / "src" / "comfyui_remote_panel" / "static" / "v042_ui.js").read_text(encoding="utf-8")
    assert '.observe(sheet, { childList: true })' in v042
    assert '.observe(sheet, { childList: true, subtree: true })' not in v042
    assert '.observe(advancedGrid, { childList: true })' in JS
    assert '.observe(advanced, { childList: true, subtree: true })' not in JS
    assert '"#sheet-body [data-pick-workflow]"' in JS
    assert '"#sheet-body [data-pick-workflow]"' in v042


def test_v046_frontend_persists_backend_in_values_json_and_checks_qwen_route_availability():
    assert 'values.prompt_backend = backend' in JS
    assert 'values.prompt_standardization_mode = backend === "raw" ? "off" : backend === "qwen35" ? "comfyui" : "ollama"' in JS
    assert 'data-v047-inference-profile' in JS
    assert 'if (path === "/api/jobs") addStandardizationMode(formData)' in JS
    assert 'if (!item || item.status !== "enabled") return false' in JS
    assert 'state.metrics?.presets?.[targetId]?.available === true' in JS
    assert 'runtime ? Boolean(runtime.available) : target.available !== false' not in JS
    assert 'button.title = "当前 Qwen3.5 标准化工作流不可用"' in JS
    assert 'setInterval' not in JS


def test_v046_job_runtime_ui_shows_total_generation_time_and_sampling_detail():
    assert 'job.queue_elapsed_seconds' in RUNTIME_JS
    assert 'job.execution_elapsed_seconds ?? job.elapsed_seconds' in RUNTIME_JS
    assert 'job.generation_elapsed_seconds' in RUNTIME_JS
    assert 'return `等待 ${duration(job.queue_elapsed_seconds)}`' in RUNTIME_JS
    assert 'return `生成 ${duration(job.execution_elapsed_seconds ?? job.elapsed_seconds)}`' in RUNTIME_JS
    assert 'return `采样 ${duration(job.generation_elapsed_seconds)} · ${generationText(job)}`' in RUNTIME_JS
    assert 'progressMeta.textContent = progressTimingText(job)' in RUNTIME_JS
    assert '["排队等待", job.queue_elapsed_seconds]' in RUNTIME_JS
    assert '["标准化提示词", job.standardization_elapsed_seconds]' in RUNTIME_JS
    assert '["采样", job.generation_elapsed_seconds]' in RUNTIME_JS
    assert '["总生成", job.execution_elapsed_seconds ?? job.elapsed_seconds]' in RUNTIME_JS


def test_v046_job_runtime_ui_adds_compact_generation_and_standardizer_tags():
    assert 'job.generation_mode === "v4step600"' in RUNTIME_JS
    assert 'if (generationMode === "original") tags.push("原版")' in RUNTIME_JS
    assert 'if (generationMode === "lightx2v") tags.push("LightX2V")' in RUNTIME_JS
    assert 'if (generationMode === "v4_600step") tags.push("v4_600step")' in RUNTIME_JS
    assert 'const backend = job.prompt_backend || (' in RUNTIME_JS
    assert 'if (backend === "ollama") tags.push("Ollama")' in RUNTIME_JS
    assert 'if (backend === "qwen35") tags.push("Qwen3.5")' in RUNTIME_JS
    assert 'tag.dataset.v046RuntimeTag = "true"' in RUNTIME_JS
    assert 'appendRuntimeTags(card, job)' in RUNTIME_JS


def test_fl2va_profile_availability_uses_canonical_backend_target_and_field_order():
    assert 'const targetId = `fl2va_${canonicalGeneration}_${backend}`' in JS
    assert 'state.workflowItems?.get?.(targetId)?.manifest' in JS
    assert 'window.ComfyRemoteCreationControls?.normalize?.()' in JS
    creation = (ROOT / "src" / "comfyui_remote_panel" / "static" / "configurator_v2_runtime.js").read_text(encoding="utf-8")
    for selector in (
        '[data-v042-mode-field]', '[data-v042-standardizer-field]',
        '[data-v047-inference-profile-field]', '[data-v045-ollama-model-field]',
    ):
        assert selector in creation


def test_shared_h3_layout_normalizer_owns_the_golden_role_order():
    creation = (ROOT / "src" / "comfyui_remote_panel" / "static" / "configurator_v2_runtime.js").read_text(encoding="utf-8")
    assert "function normalizeH3AdvancedLayout" in creation
    assert '"generation-mode", "prompt-backend", "main-model", "ollama-model"' in creation
    assert '"scheduler", "sampler", "steps", "seed-policy", "seed-value"' in creation
    assert '"reference-resolution"' in creation
    assert 'function positionFl2vaFields' not in JS


def test_ci_runs_executable_shared_h3_frontend_contract_smoke():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "node tests/frontend_contract_smoke.js" in ci
