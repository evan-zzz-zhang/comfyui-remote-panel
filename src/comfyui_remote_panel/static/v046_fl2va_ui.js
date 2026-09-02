(() => {
  const ENTRY_ID = "h3-fl2va-group";
  const STORAGE_KEY = "comfy-remote.fl2va.prompt-standardization-mode";
  const DEFAULT_MODE = "ollama";
  const DEFAULT_ASPECT = "9:16";
  const STANDARDIZATION_MODES = new Set(["raw", "ollama", "qwen35", "off", "comfyui"]);
  const QWEN_PRESETS = {
    original: "fl2va_original_qwen35",
    lightx2v: "fl2va_lightx2v_qwen35",
    v4_600step: "fl2va_v4step600_qwen35",
  };
  const CANONICAL_FL2VA_PRESET_IDS = new Set([
    "fl2va_original_raw",
    "fl2va_original_ollama",
    "fl2va_original_qwen35",
    "fl2va_v4step600_raw",
    "fl2va_v4step600_ollama",
    "fl2va_v4step600_qwen35",
    "fl2va_lightx2v_raw",
    "fl2va_lightx2v_ollama",
    "fl2va_lightx2v_qwen35",
  ]);
  const LEGACY_FL2VA_PRESET_IDS = new Set([
    "h3-fl2va-qwen35-4b",
    "h3-fl2va-lightx2v-qwen35-4b",
    "h3-fl2va-v4step600-qwen35-4b",
    "h3-fl2va",
    "h3-fl2va-lightx2v",
    "h3-fl2va-v4step600",
  ]);
  const PHYSICAL_FL2VA_PRESET_IDS = new Set([
    ...CANONICAL_FL2VA_PRESET_IDS,
    ...LEGACY_FL2VA_PRESET_IDS,
  ]);

  const baseApplyPresetV046 = applyPreset;
  const baseUploadFormV046 = uploadForm;
  const baseLoadPresetsV046 = loadPresets;
  const baseLoadWorkflowsV046 = loadWorkflows;
  const baseUpdateSubmitAvailabilityV046 = updateSubmitAvailability;

  function validMode(value) {
    return STANDARDIZATION_MODES.has(String(value || "").toLowerCase());
  }

  function canonicalMode(value) {
    return { off: "raw", comfyui: "qwen35" }[String(value || "").toLowerCase()]
      || String(value || "").toLowerCase();
  }

  function rememberedMode() {
    try {
      const value = window.localStorage.getItem(STORAGE_KEY);
      return validMode(value) ? canonicalMode(value) : "";
    } catch (_) {
      return "";
    }
  }

  function preferredMode(candidate) {
    const explicit = String(candidate || "").toLowerCase();
    if (validMode(explicit)) return canonicalMode(explicit);
    return rememberedMode() || DEFAULT_MODE;
  }

  function rememberMode(mode) {
    mode = canonicalMode(mode);
    if (!validMode(mode)) return;
    try { window.localStorage.setItem(STORAGE_KEY, mode); } catch (_) {}
  }

  function modeFromOverrides(overrides) {
    const values = overrides?.values && typeof overrides.values === "object"
      ? overrides.values
      : {};
    const explicit = overrides?.prompt_backend
      ?? values.prompt_backend
      ?? overrides?.prompt_standardization_mode
      ?? values.prompt_standardization_mode;
    if (validMode(explicit)) return canonicalMode(explicit);
    const legacy = overrides?.prompt_standardization ?? values.prompt_standardization;
    if (legacy === false) return "raw";
    if (legacy === true) return "ollama";
    return null;
  }

  function aspectFromOverrides(overrides) {
    const values = overrides?.values && typeof overrides.values === "object"
      ? overrides.values
      : {};
    const raw = overrides?.aspect_ratio ?? values.aspect_ratio;
    if (typeof raw !== "string" || !raw.trim()) return null;
    const value = raw.trim();
    return value === "reference_image" ? "reference" : value;
  }

  function option(value, label) {
    const item = document.createElement("option");
    item.value = value;
    item.textContent = label;
    return item;
  }

  function installLegacyGuardStyle() {
    if (document.querySelector("#v046-standardizer-legacy-guard")) return;
    const style = document.createElement("style");
    style.id = "v046-standardizer-legacy-guard";
    style.textContent = `
      #advanced-settings .v042-switch,
      #advanced-settings [data-v042-prompt-standardization],
      #advanced-settings [data-v042-standardizer-switch] {
        display: none !important;
        visibility: hidden !important;
        pointer-events: none !important;
      }
    `;
    document.head.append(style);
  }

  function normalizeLegacyStandardizerControls() {
    installLegacyGuardStyle();
    const advanced = document.querySelector("#advanced-settings");
    if (!advanced) return null;
    const fields = [...advanced.querySelectorAll("[data-v042-standardizer-field]")];
    if (!fields.length) return null;

    const field = fields[0];
    const checkboxes = [...advanced.querySelectorAll("[data-v042-prompt-standardization]")];
    let compatibility = field.querySelector("[data-v042-prompt-standardization]") || checkboxes[0] || null;

    if (compatibility) {
      compatibility.hidden = true;
      compatibility.setAttribute("aria-hidden", "true");
      compatibility.tabIndex = -1;
      compatibility.style.setProperty("display", "none", "important");
      if (compatibility.parentElement !== field) field.append(compatibility);
    }

    for (const checkbox of checkboxes) {
      if (checkbox !== compatibility) checkbox.remove();
    }
    advanced.querySelectorAll(".v042-switch").forEach(node => node.remove());
    advanced.querySelectorAll("[data-v042-standardizer-switch]").forEach(node => node.remove());
    for (const duplicate of fields.slice(1)) duplicate.remove();
    return field;
  }

  function syncCompatibilityCheckbox(mode) {
    const checkbox = document.querySelector("[data-v042-prompt-standardization]");
    if (!checkbox) return;
    const next = canonicalMode(mode) !== "raw";
    if (checkbox.checked !== next) checkbox.checked = next;
    checkbox.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function syncOllamaField(mode) {
    const field = document.querySelector("[data-v045-ollama-model-field]");
    if (!field) return;
    field.style.display = canonicalMode(mode) === "ollama" ? "" : "none";
  }

  function ensureFl2vaReferenceAspectOption() {
    if (selectedPreset()?.id !== ENTRY_ID) return;
    const select = document.querySelector('select[name="aspect_ratio"]');
    if (!select) return;
    let reference = document.querySelector("#reference-aspect-image-option");
    if (!reference) {
      reference = document.createElement("option");
      reference.id = "reference-aspect-image-option";
      select.append(reference);
    }
    reference.value = "reference";
    reference.textContent = "参考图";
    reference.hidden = false;
    reference.disabled = false;
  }

  function syncFl2vaAspectValue(candidate = null, previous = "", preservePrevious = false) {
    if (selectedPreset()?.id !== ENTRY_ID) return;
    ensureFl2vaReferenceAspectOption();
    const select = document.querySelector('select[name="aspect_ratio"]');
    if (!select) return;
    const available = new Set([...select.options].map(item => item.value));
    const explicit = candidate === "reference_image" ? "reference" : candidate;
    let next = explicit && available.has(explicit) ? explicit : "";
    if (!next && preservePrevious && previous && available.has(previous)) next = previous;
    if (!next || !available.has(next)) next = DEFAULT_ASPECT;
    if (available.has(next)) select.value = next;
    if (!select.value || !available.has(select.value)) select.value = DEFAULT_ASPECT;
    if (explicit && available.has(explicit)) select.dataset.v046AspectExplicit = "true";
  }

  function ensureStandardizationSelector(candidate = null) {
    if (selectedPreset()?.id !== ENTRY_ID) return;
    const field = normalizeLegacyStandardizerControls();
    if (!field) return;

    const label = field.querySelector(":scope > span:first-child");
    if (label && label.textContent !== "标准化提示词") label.textContent = "标准化提示词";

    let select = field.querySelector("[data-v046-prompt-standardization-mode]");
    const existingMode = validMode(select?.value) ? String(select.value).toLowerCase() : null;
    if (!select) {
      select = document.createElement("select");
      select.dataset.v046PromptStandardizationMode = "true";
      select.append(
        option("raw", "原始提示词"),
        option("ollama", "Ollama 标准化"),
        option("qwen35", "Qwen3.5 标准化"),
      );
      field.append(select);
      select.addEventListener("change", () => {
        const mode = preferredMode(select.value);
        select.value = mode;
        rememberMode(mode);
        syncCompatibilityCheckbox(mode);
        syncOllamaField(mode);
        syncInferenceProfileAvailability();
        updateSubmitAvailability();
      });
    }

    // Retry/applyPreset can provide an explicit backend. Once it is applied,
    // later MutationObserver passes must preserve the live selector value
    // instead of restoring the last localStorage preference over the retry.
    const mode = preferredMode(candidate ?? existingMode);
    select.value = canonicalMode(mode);
    syncCompatibilityCheckbox(mode);
    normalizeLegacyStandardizerControls();
    syncOllamaField(mode);
  }

  function removePhysicalCreationChoices() {
    const native = document.querySelector("#preset-select");
    if (native) {
      for (const item of [...native.options]) {
        if (PHYSICAL_FL2VA_PRESET_IDS.has(item.value)) item.remove();
      }
    }
    document.querySelectorAll("[data-pick-workflow]").forEach(button => {
      if (PHYSICAL_FL2VA_PRESET_IDS.has(button.dataset.pickWorkflow)) button.remove();
    });
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

  function ensureInferenceProfileSelector() {
    if (selectedPreset()?.id !== ENTRY_ID) return;
    const grid = document.querySelector("#advanced-settings .advanced-grid");
    if (!grid || grid.querySelector("[data-v047-inference-profile-field]")) return;
    const label = document.createElement("label");
    label.className = "field";
    label.dataset.v047InferenceProfileField = "true";
    label.innerHTML = "<span>模型配置</span>";
    const select = document.createElement("select");
    select.name = "inference_profile";
    select.dataset.v047InferenceProfile = "true";
    select.append(
      option("auto", "自动"),
      option("int8", "INT8"),
      option("fp16_bf16", "FP16/BF16"),
    );
    label.append(select);
    grid.append(label);
    select.addEventListener("change", () => {
      try { window.localStorage.setItem("comfy-remote.fl2va.inference-profile", select.value); } catch (_) {}
    });
    try {
      const remembered = window.localStorage.getItem("comfy-remote.fl2va.inference-profile");
      if (["auto", "int8", "fp16_bf16"].includes(remembered)) select.value = remembered;
    } catch (_) {}
    syncInferenceProfileAvailability(select);
  }

  function syncInferenceProfileAvailability(select = document.querySelector("select[data-v047-inference-profile]")) {
    if (!select) return;
    const generation = document.querySelector("[data-v042-generation-mode]")?.value;
    const backend = canonicalMode(document.querySelector("[data-v046-prompt-standardization-mode]")?.value);
    const qwenId = QWEN_PRESETS[generation];
    const original = state.workflowItems?.get?.("h3-fl2va")?.manifest;
    const modeId = original?.generation_modes?.values?.[generation]?.preset_id;
    const target = state.workflowItems?.get?.(backend === "qwen35" ? qwenId : modeId)?.manifest;
    const main = target?.model_profile?.main_model;
    const variants = main?.variants && typeof main.variants === "object" ? main.variants : {};
    const fp16Variant = variants.fp16_bf16;
    const fp16 = select.querySelector('option[value="fp16_bf16"]');
    if (fp16) {
      const available = fp16Variant && typeof fp16Variant === "object" && fp16Variant.available !== false;
      fp16.disabled = !available;
      fp16.title = fp16.disabled
        ? (fp16Variant?.reason || "当前内置资产未声明可用的 FP16/BF16 变体")
        : "";
    }
    if (select.selectedOptions[0]?.disabled) select.value = "auto";
  }

  function syncInferenceProfile(candidate = null) {
    const select = document.querySelector("select[data-v047-inference-profile]");
    if (!select) return;
    if (["auto", "int8", "fp16_bf16"].includes(String(candidate || ""))) {
      select.value = candidate;
      return;
    }
    try {
      const remembered = window.localStorage.getItem("comfy-remote.fl2va.inference-profile");
      if (["auto", "int8", "fp16_bf16"].includes(remembered)) select.value = remembered;
    } catch (_) {}
  }

  function addStandardizationMode(formData) {
    if (String(formData.get("preset_id") || "") !== ENTRY_ID) return formData;
    const select = document.querySelector("[data-v046-prompt-standardization-mode]");
    const mode = preferredMode(select?.value);
    const values = valuesFromFormData(formData);
    const backend = canonicalMode(mode);
    values.prompt_backend = backend;
    values.prompt_standardization_mode = backend === "raw" ? "off" : backend === "qwen35" ? "comfyui" : "ollama";
    const profile = document.querySelector("select[data-v047-inference-profile]")?.value;
    if (profile) values.inference_profile = profile;
    formData.delete("values_json");
    formData.set("values_json", JSON.stringify(values));
    return formData;
  }

  function qwenRouteAvailable() {
    const generation = document.querySelector("[data-v042-generation-mode]")?.value;
    const targetId = QWEN_PRESETS[generation];
    if (!targetId) return false;
    const item = state.workflowItems?.get?.(targetId);
    if (item && item.status !== "enabled") return false;
    const target = state.presets.get(targetId) || item?.manifest;
    if (!target) return false;
    const runtime = state.metrics?.presets?.[targetId];
    return runtime ? Boolean(runtime.available) : target.available !== false;
  }

  applyPreset = function(presetId, overrides = {}) {
    const aspect = document.querySelector('select[name="aspect_ratio"]');
    const previousAspect = aspect?.value || "";
    const preservePreviousAspect = aspect?.dataset.v046AspectExplicit === "true";
    const explicitAspect = aspectFromOverrides(overrides);
    const result = baseApplyPresetV046(presetId, overrides);
    const candidate = modeFromOverrides(overrides);
    queueMicrotask(() => {
      removePhysicalCreationChoices();
      syncFl2vaAspectValue(explicitAspect, previousAspect, preservePreviousAspect);
      ensureStandardizationSelector(candidate);
      ensureInferenceProfileSelector();
      syncInferenceProfile(overrides?.inference_profile ?? overrides?.values?.inference_profile);
      syncInferenceProfileAvailability();
    });
    return result;
  };

  uploadForm = function(path, formData, onProgress) {
    if (path === "/api/jobs") addStandardizationMode(formData);
    return baseUploadFormV046(path, formData, onProgress);
  };

  loadPresets = async function(...args) {
    const result = await baseLoadPresetsV046(...args);
    removePhysicalCreationChoices();
    const aspect = document.querySelector('select[name="aspect_ratio"]');
    syncFl2vaAspectValue(null, aspect?.value || "", aspect?.dataset.v046AspectExplicit === "true");
    ensureStandardizationSelector();
    ensureInferenceProfileSelector();
    syncInferenceProfileAvailability();
    return result;
  };

  loadWorkflows = async function(...args) {
    const result = await baseLoadWorkflowsV046(...args);
    removePhysicalCreationChoices();
    const aspect = document.querySelector('select[name="aspect_ratio"]');
    syncFl2vaAspectValue(null, aspect?.value || "", aspect?.dataset.v046AspectExplicit === "true");
    ensureStandardizationSelector();
    ensureInferenceProfileSelector();
    syncInferenceProfileAvailability();
    return result;
  };

  updateSubmitAvailability = function() {
    baseUpdateSubmitAvailabilityV046();
    if (selectedPreset()?.id !== ENTRY_ID) return;
    const select = document.querySelector("[data-v046-prompt-standardization-mode]");
    if (preferredMode(select?.value) !== "qwen35") return;
    const button = document.querySelector("#submit-button");
    if (!button) return;
    const available = qwenRouteAvailable();
    if (!available) {
      button.disabled = true;
      button.title = "当前 Qwen3.5 标准化工作流不可用";
    } else if (button.title === "当前 Qwen3.5 标准化工作流不可用") {
      button.removeAttribute("title");
    }
  };

  document.addEventListener("DOMContentLoaded", () => {
    installLegacyGuardStyle();
    document.addEventListener("click", event => {
      const sheetAspect = event.target.closest?.("[data-sheet-aspect]");
      if (sheetAspect && selectedPreset()?.id === ENTRY_ID) {
        const select = document.querySelector('select[name="aspect_ratio"]');
        if (select) select.dataset.v046AspectExplicit = "true";
      }
      if (event.target.closest?.("#open-generation-settings")) {
        const select = document.querySelector('select[name="aspect_ratio"]');
        syncFl2vaAspectValue(null, select?.value || "", select?.dataset.v046AspectExplicit === "true");
      }
    }, true);
    document.addEventListener("change", event => {
      if (event.target?.matches?.("#first-frame, #last-frame")) {
        queueMicrotask(ensureFl2vaReferenceAspectOption);
      }
    });
    document.querySelector("#workflow-picker-button")?.addEventListener("click", () => {
      window.setTimeout(removePhysicalCreationChoices, 0);
    });
    const advanced = document.querySelector("#advanced-settings");
    if (advanced) {
      new MutationObserver(() => queueMicrotask(() => {
        ensureStandardizationSelector();
        ensureInferenceProfileSelector();
        syncInferenceProfileAvailability();
      }))
        .observe(advanced, { childList: true, subtree: true });
    }
    queueMicrotask(() => {
      removePhysicalCreationChoices();
      const aspect = document.querySelector('select[name="aspect_ratio"]');
      syncFl2vaAspectValue(null, aspect?.value || "", aspect?.dataset.v046AspectExplicit === "true");
      ensureStandardizationSelector();
      ensureInferenceProfileSelector();
      syncInferenceProfileAvailability();
    });
  });
})();
