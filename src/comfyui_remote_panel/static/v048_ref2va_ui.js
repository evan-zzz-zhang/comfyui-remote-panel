(() => {
  const ENTRY_ID = "h3-ref2va-group";
  const STORAGE_MODE = "comfy-remote.ref2va.generation-mode";
  const STORAGE_BACKEND = "comfy-remote.ref2va.prompt-backend";
  const STORAGE_PROFILE = "comfy-remote.ref2va.inference-profile";
  const STORAGE_OLLAMA_MODEL = "comfy-remote.ref2va.ollama-model";
  const STORAGE_SEED_POLICY = "comfy-remote.ref2va.seed-policy";
  const DEFAULT_MODE = "v4step600";
  const DEFAULT_BACKEND = "raw";
  const DEFAULT_PROFILE = "int8";
  const DEFAULT_OLLAMA_MODEL = "gemma4:e4b";
  const MODE_TUNING = {
    original: { scheduler: "simple", sampler: "res_multistep", steps: 20 },
    lightx2v: { scheduler: "simple", sampler: "euler", steps: 4 },
    v4step600: { scheduler: "beta", sampler: "euler", steps: 8 },
  };
  const PHYSICAL = new Set([
    "h3-ref2va", "h3-ref2va-lightx2v", "h3-ref2va-v4step600",
    "ref2va_original_raw", "ref2va_original_ollama", "ref2va_original_qwen35",
    "ref2va_lightx2v_raw", "ref2va_lightx2v_ollama", "ref2va_lightx2v_qwen35",
    "ref2va_v4step600_raw", "ref2va_v4step600_ollama", "ref2va_v4step600_qwen35",
  ]);
  const baseApply = applyPreset;
  const baseUpload = uploadForm;
  const baseLoadPresets = loadPresets;
  const baseLoadWorkflows = loadWorkflows;
  const baseUpdateSubmitAvailability = updateSubmitAvailability;
  const REF2VA_UNAVAILABLE_TITLE = "当前 Ref2VA 工作流不可用";

  function canonicalMode(value) {
    const mode = String(value || "").toLowerCase();
    return mode === "v4_600step" ? "v4step600" : mode;
  }
  function canonicalBackend(value) {
    return ({ off: "raw", comfyui: "qwen35" }[String(value || "").toLowerCase()]
      || String(value || "").toLowerCase());
  }
  function validMode(value) { return ["original", "lightx2v", "v4step600"].includes(canonicalMode(value)); }
  function validBackend(value) { return ["raw", "ollama", "qwen35"].includes(canonicalBackend(value)); }
  function remembered(key, values, fallback) {
    try {
      const value = String(window.localStorage.getItem(key) || "").toLowerCase();
      return values.includes(value) ? value : fallback;
    } catch (_) { return fallback; }
  }
  function rememberedText(key, fallback) {
    try { return window.localStorage.getItem(key)?.trim() || fallback; } catch (_) { return fallback; }
  }
  function group() { return state.presets.get(ENTRY_ID); }
  function selectedRef2va() { return selectedPreset()?.id === ENTRY_ID; }
  function targetId(mode, backend) { return `ref2va_${canonicalMode(mode)}_${canonicalBackend(backend)}`; }
  function mergedOverrides(overrides) {
    return { ...overrides, ...(overrides?.values && typeof overrides.values === "object" ? overrides.values : {}) };
  }
  function preferredMode(value) {
    const explicit = canonicalMode(value);
    if (validMode(explicit)) return explicit;
    const ui = window.ComfyRemoteH3AdvancedSettings?.getState?.();
    if (ui?.family === "ref2va" && validMode(ui.generationMode)) return ui.generationMode;
    return remembered(STORAGE_MODE, ["original", "lightx2v", "v4step600"], DEFAULT_MODE);
  }
  function removePhysicalCreationChoices() {
    document.querySelectorAll("#preset-select option").forEach(item => {
      if (PHYSICAL.has(item.value)) item.remove();
    });
    document.querySelectorAll("#sheet-body [data-pick-workflow]").forEach(item => {
      if (PHYSICAL.has(item.dataset.pickWorkflow)) item.remove();
    });
  }
  function currentRef2vaValues() {
    const ui = window.ComfyRemoteH3AdvancedSettings?.getState?.();
    return {
      mode: ui?.family === "ref2va" ? ui.generationMode : preferredMode(),
      backend: ui?.family === "ref2va" ? ui.promptBackend : remembered(STORAGE_BACKEND, ["raw", "ollama", "qwen35"], DEFAULT_BACKEND),
      profile: ui?.family === "ref2va" ? ui.mainModel : remembered(STORAGE_PROFILE, ["int8", "fp16_bf16"], DEFAULT_PROFILE),
      ollamaModel: ui?.family === "ref2va" ? ui.ollamaModel : rememberedText(STORAGE_OLLAMA_MODEL, DEFAULT_OLLAMA_MODEL),
    };
  }
  function updateRef2vaAvailability() {
    if (!selectedRef2va()) return;
    const { mode, backend } = currentRef2vaValues();
    const target = state.workflowItems?.get?.(targetId(mode, backend));
    const submit = document.querySelector("#submit-button");
    if (!submit) return;
    const available = Boolean(target && target.status === "enabled" && state.metrics?.presets?.[target.id]?.available === true);
    if (!available) {
      submit.disabled = true;
      submit.title = REF2VA_UNAVAILABLE_TITLE;
      submit.dataset.v048Ref2vaAvailability = "unavailable";
    } else if (submit.dataset.v048Ref2vaAvailability === "unavailable") {
      delete submit.dataset.v048Ref2vaAvailability;
      submit.removeAttribute("title");
    }
  }
  function syncMainModelAvailability(ui) {
    if (!selectedRef2va()) return;
    const target = state.workflowItems?.get?.(targetId(ui.generationMode, ui.promptBackend))?.manifest;
    const variant = target?.model_profile?.main_model?.variants?.fp16_bf16;
    const select = document.querySelector('[data-h3-advanced-role="main-model"] select');
    const option = select?.querySelector?.('option[value="fp16_bf16"]');
    if (!option) return;
    option.disabled = Boolean(variant && variant.available === false);
    option.title = option.disabled ? (variant.reason || "当前 Ref2VA BF16 变体不可用") : "";
    if (option.disabled && select.value === "fp16_bf16") select.value = DEFAULT_PROFILE;
  }

  window.ComfyRemoteH3AdvancedSettings?.registerAdapter?.({
    family: "ref2va",
    modeValues: ["original", "lightx2v", "v4step600"],
    modeLabels: ["原版", "LightX2V", "v4_600step"],
    modelValues: ["int8", "fp16_bf16"],
    modelLabels: ["pruned_int8", "pruned_bf16"],
    normalizeMode: canonicalMode,
    normalizeBackend: canonicalBackend,
    normalizeMainModel: value => String(value || "").toLowerCase() === "auto" ? DEFAULT_PROFILE : String(value || "").toLowerCase(),
    modeTuning: mode => MODE_TUNING[canonicalMode(mode)],
    defaults: {
      mode: DEFAULT_MODE, backend: DEFAULT_BACKEND, mainModel: DEFAULT_PROFILE, ollamaModel: DEFAULT_OLLAMA_MODEL,
      scheduler: "beta", sampler: "euler", steps: "8", seedPolicy: "randomize", referenceResolution: null,
    },
    storage: { mode: STORAGE_MODE, backend: STORAGE_BACKEND, mainModel: STORAGE_PROFILE, ollamaModel: STORAGE_OLLAMA_MODEL, seedPolicy: STORAGE_SEED_POLICY },
    onRender: syncMainModelAvailability,
  });

  function valuesFromFormData(formData) {
    const values = {};
    for (const raw of formData.getAll("values_json")) {
      if (typeof raw !== "string" || !raw) continue;
      try {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) Object.assign(values, parsed);
      } catch (_) {}
    }
    return values;
  }
  function addRef2vaRouting(formData) {
    if (String(formData.get("preset_id") || "") !== ENTRY_ID) return formData;
    const { mode, backend, profile, ollamaModel } = currentRef2vaValues();
    const values = valuesFromFormData(formData);
    values.generation_mode = mode;
    values.prompt_backend = backend;
    values.inference_profile = profile;
    if (backend === "ollama") values.ollama_model = ollamaModel;
    else delete values.ollama_model;
    formData.delete("values_json");
    formData.set("values_json", JSON.stringify(values));
    return formData;
  }
  window.ComfyRemoteRef2vaControls = { addRouting: addRef2vaRouting, currentValues: currentRef2vaValues };

  applyPreset = function(presetId, overrides = {}) {
    const merged = mergedOverrides(overrides);
    const mode = preferredMode(merged.generation_mode);
    const nextOverrides = presetId === ENTRY_ID ? { ...overrides, generation_mode: mode } : overrides;
    const result = baseApply(presetId, nextOverrides);
    queueMicrotask(removePhysicalCreationChoices);
    return result;
  };
  uploadForm = function(path, formData, onProgress) {
    if (path === "/api/jobs") addRef2vaRouting(formData);
    return baseUpload(path, formData, onProgress);
  };
  loadPresets = async function(...args) {
    const result = await baseLoadPresets(...args);
    removePhysicalCreationChoices();
    updateRef2vaAvailability();
    return result;
  };
  loadWorkflows = async function(...args) {
    const result = await baseLoadWorkflows(...args);
    removePhysicalCreationChoices();
    updateRef2vaAvailability();
    return result;
  };
  updateSubmitAvailability = function(...args) {
    baseUpdateSubmitAvailability(...args);
    updateRef2vaAvailability();
  };
  document.addEventListener("DOMContentLoaded", () => {
    document.querySelector("#workflow-picker-button")?.addEventListener("click", () => {
      window.setTimeout(removePhysicalCreationChoices, 0);
    });
    queueMicrotask(removePhysicalCreationChoices);
  });
})();
