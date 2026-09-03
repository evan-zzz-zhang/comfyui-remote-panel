(() => {
  const ENTRY_ID = "h3-fl2va-group";
  const STORAGE_BACKEND = "comfy-remote.fl2va.prompt-standardization-mode";
  const STORAGE_MODE = "comfy-remote.fl2va.generation-mode";
  const STORAGE_PROFILE = "comfy-remote.fl2va.inference-profile";
  const STORAGE_OLLAMA_MODEL = "comfy-remote.fl2va.ollama-model";
  const STORAGE_SEED_POLICY = "comfy-remote.fl2va.seed-policy";
  const DEFAULT_MODE = "v4_600step";
  const DEFAULT_PROFILE = "int8";
  const DEFAULT_OLLAMA_MODEL = "gemma4:e4b";
  const DEFAULT_ASPECT = "9:16";
  const MODE_TUNING = {
    original: { scheduler: "simple", sampler: "res_multistep", steps: 20 },
    lightx2v: { scheduler: "simple", sampler: "euler", steps: 8 },
    v4_600step: { scheduler: "beta", sampler: "euler", steps: 8 },
  };
  const QWEN_PRESETS = {
    original: "fl2va_original_qwen35",
    lightx2v: "fl2va_lightx2v_qwen35",
    v4_600step: "fl2va_v4step600_qwen35",
  };
  const CANONICAL_FL2VA_PRESET_IDS = new Set([
    "fl2va_original_raw", "fl2va_original_ollama", "fl2va_original_qwen35",
    "fl2va_v4step600_raw", "fl2va_v4step600_ollama", "fl2va_v4step600_qwen35",
    "fl2va_lightx2v_raw", "fl2va_lightx2v_ollama", "fl2va_lightx2v_qwen35",
  ]);
  const LEGACY_FL2VA_PRESET_IDS = new Set([
    "h3-fl2va-qwen35-4b", "h3-fl2va-lightx2v-qwen35-4b", "h3-fl2va-v4step600-qwen35-4b",
    "h3-fl2va", "h3-fl2va-lightx2v", "h3-fl2va-v4step600",
  ]);
  const PHYSICAL_FL2VA_PRESET_IDS = new Set([...CANONICAL_FL2VA_PRESET_IDS, ...LEGACY_FL2VA_PRESET_IDS]);

  const baseApplyPreset = applyPreset;
  const baseUploadForm = uploadForm;
  const baseLoadPresets = loadPresets;
  const baseLoadWorkflows = loadWorkflows;
  const baseUpdateSubmitAvailability = updateSubmitAvailability;

  function canonicalMode(value) {
    const mode = String(value || "").toLowerCase();
    return mode === "v4step600" ? "v4_600step" : mode;
  }
  function canonicalBackend(value) {
    return ({ off: "raw", comfyui: "qwen35" }[String(value || "").toLowerCase()]
      || String(value || "").toLowerCase());
  }
  function validMode(value) { return ["original", "lightx2v", "v4_600step"].includes(canonicalMode(value)); }
  function remember(key, value) {
    try { if (key && value) window.localStorage.setItem(key, String(value)); } catch (_) {}
  }
  function remembered(key, fallback) {
    try { return window.localStorage.getItem(key) || fallback; } catch (_) { return fallback; }
  }
  function preferredMode(value) {
    const explicit = canonicalMode(value);
    if (validMode(explicit)) return explicit;
    const controller = window.ComfyRemoteH3AdvancedSettings?.getState?.();
    if (controller?.family === "fl2va" && validMode(controller.generationMode)) return controller.generationMode;
    const stored = canonicalMode(remembered(STORAGE_MODE, ""));
    return validMode(stored) ? stored : DEFAULT_MODE;
  }
  function aspectFromOverrides(overrides) {
    const values = overrides?.values && typeof overrides.values === "object" ? overrides.values : {};
    const raw = overrides?.aspect_ratio ?? values.aspect_ratio;
    if (typeof raw !== "string" || !raw.trim()) return null;
    return raw.trim() === "reference_image" ? "reference" : raw.trim();
  }
  function removePhysicalCreationChoices() {
    document.querySelectorAll("#preset-select option").forEach(item => {
      if (PHYSICAL_FL2VA_PRESET_IDS.has(item.value)) item.remove();
    });
    document.querySelectorAll("#sheet-body [data-pick-workflow]").forEach(item => {
      if (PHYSICAL_FL2VA_PRESET_IDS.has(item.dataset.pickWorkflow)) item.remove();
    });
  }
  function ensureFl2vaReferenceAspectOption() {
    if (selectedPreset()?.id !== ENTRY_ID) return;
    const select = document.querySelector('select[name="aspect_ratio"]');
    const reference = document.querySelector("#reference-aspect-image-option");
    if (select && reference) {
      reference.value = "reference";
      reference.textContent = "参考图";
      reference.hidden = false;
      reference.disabled = false;
    }
  }
  function syncFl2vaAspectValue(candidate = null, previous = "", preservePrevious = false) {
    if (selectedPreset()?.id !== ENTRY_ID) return;
    ensureFl2vaReferenceAspectOption();
    const select = document.querySelector('select[name="aspect_ratio"]');
    if (!select) return;
    const available = new Set([...select.options].map(item => item.value));
    const explicit = candidate === "reference_image" ? "reference" : candidate;
    const next = explicit && available.has(explicit)
      ? explicit
      : preservePrevious && previous && available.has(previous) ? previous : DEFAULT_ASPECT;
    if (available.has(next)) select.value = next;
    if (!select.value || !available.has(select.value)) select.value = DEFAULT_ASPECT;
    if (explicit && available.has(explicit)) select.dataset.v046AspectExplicit = "true";
  }
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
  function addStandardizationMode(formData) {
    if (String(formData.get("preset_id") || "") !== ENTRY_ID) return formData;
    const ui = window.ComfyRemoteH3AdvancedSettings?.getState?.() || {};
    const values = valuesFromFormData(formData);
    const backend = canonicalBackend(ui.promptBackend || remembered(STORAGE_BACKEND, "ollama"));
    values.prompt_backend = backend;
    values.prompt_standardization_mode = backend === "raw" ? "off" : backend === "qwen35" ? "comfyui" : "ollama";
    if (ui.mainModel) values.inference_profile = ui.mainModel;
    formData.delete("values_json");
    formData.set("values_json", JSON.stringify(values));
    return formData;
  }
  function qwenRouteAvailable() {
    const mode = preferredMode(window.ComfyRemoteH3AdvancedSettings?.getState?.()?.generationMode);
    const targetId = QWEN_PRESETS[mode];
    const item = state.workflowItems?.get?.(targetId);
    return Boolean(item && item.status === "enabled" && state.metrics?.presets?.[targetId]?.available === true);
  }
  function syncMainModelAvailability(ui) {
    if (selectedPreset()?.id !== ENTRY_ID) return;
    const mode = ui.generationMode === "v4_600step" ? "v4step600" : ui.generationMode;
    const target = state.workflowItems?.get?.(`fl2va_${mode}_${ui.promptBackend}`)?.manifest;
    const variant = target?.model_profile?.main_model?.variants?.fp16_bf16;
    const select = document.querySelector('[data-h3-advanced-role="main-model"] select');
    const option = select?.querySelector?.('option[value="fp16_bf16"]');
    if (!option) return;
    option.disabled = Boolean(variant && variant.available === false);
    option.title = option.disabled ? (variant.reason || "当前内置资产未声明可用的 FP16/BF16 变体") : "";
    if (option.disabled && select.value === "fp16_bf16") select.value = DEFAULT_PROFILE;
  }

  window.ComfyRemoteH3AdvancedSettings?.registerAdapter?.({
    family: "fl2va",
    modeValues: ["original", "lightx2v", "v4_600step"],
    modeLabels: ["原版", "LightX2V", "v4_600step"],
    modelValues: ["int8", "fp16_bf16"],
    modelLabels: ["pruned_int8", "pruned_bf16"],
    normalizeMode: canonicalMode,
    normalizeBackend: canonicalBackend,
    normalizeMainModel: value => String(value || "").toLowerCase() === "auto" ? DEFAULT_PROFILE : String(value || "").toLowerCase(),
    modeTuning: mode => MODE_TUNING[canonicalMode(mode)],
    defaults: {
      mode: DEFAULT_MODE, backend: "ollama", mainModel: DEFAULT_PROFILE, ollamaModel: DEFAULT_OLLAMA_MODEL,
      scheduler: "beta", sampler: "euler", steps: "8", seedPolicy: "randomize", referenceResolution: null,
    },
    storage: { mode: STORAGE_MODE, backend: STORAGE_BACKEND, mainModel: STORAGE_PROFILE, ollamaModel: STORAGE_OLLAMA_MODEL, seedPolicy: STORAGE_SEED_POLICY },
    onRender: syncMainModelAvailability,
  });

  applyPreset = function(presetId, overrides = {}) {
    const aspect = document.querySelector('select[name="aspect_ratio"]');
    const previousAspect = aspect?.value || "";
    const preservePreviousAspect = aspect?.dataset.v046AspectExplicit === "true";
    const explicitAspect = aspectFromOverrides(overrides);
    const result = baseApplyPreset(presetId, overrides);
    queueMicrotask(() => {
      removePhysicalCreationChoices();
      syncFl2vaAspectValue(explicitAspect, previousAspect, preservePreviousAspect);
    });
    return result;
  };
  uploadForm = function(path, formData, onProgress) {
    if (path === "/api/jobs") addStandardizationMode(formData);
    return baseUploadForm(path, formData, onProgress);
  };
  loadPresets = async function(...args) {
    const result = await baseLoadPresets(...args);
    removePhysicalCreationChoices();
    syncFl2vaAspectValue();
    return result;
  };
  loadWorkflows = async function(...args) {
    const result = await baseLoadWorkflows(...args);
    removePhysicalCreationChoices();
    syncFl2vaAspectValue();
    return result;
  };
  updateSubmitAvailability = function(...args) {
    baseUpdateSubmitAvailability(...args);
    if (selectedPreset()?.id !== ENTRY_ID) return;
    const backend = window.ComfyRemoteH3AdvancedSettings?.getState?.()?.promptBackend;
    const button = document.querySelector("#submit-button");
    if (!button || backend !== "qwen35") return;
    if (!qwenRouteAvailable()) {
      button.disabled = true;
      button.title = "当前 Qwen3.5 标准化工作流不可用";
    } else if (button.title === "当前 Qwen3.5 标准化工作流不可用") {
      button.removeAttribute("title");
    }
  };
  document.addEventListener("DOMContentLoaded", () => {
    document.querySelector("#workflow-picker-button")?.addEventListener("click", () => {
      window.setTimeout(removePhysicalCreationChoices, 0);
    });
    document.addEventListener("click", event => {
      if (event.target.closest?.("#open-generation-settings")) {
        const select = document.querySelector('select[name="aspect_ratio"]');
        syncFl2vaAspectValue(null, select?.value || "", select?.dataset.v046AspectExplicit === "true");
      }
    }, true);
    document.addEventListener("change", event => {
      if (event.target?.matches?.("#first-frame, #last-frame")) queueMicrotask(ensureFl2vaReferenceAspectOption);
    });
    queueMicrotask(removePhysicalCreationChoices);
  });
})();
