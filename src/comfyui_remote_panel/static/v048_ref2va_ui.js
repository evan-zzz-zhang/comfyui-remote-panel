(() => {
  const ENTRY_ID = "h3-ref2va-group";
  const STORAGE_MODE = "comfy-remote.ref2va.generation-mode";
  const STORAGE_BACKEND = "comfy-remote.ref2va.prompt-backend";
  const STORAGE_PROFILE = "comfy-remote.ref2va.inference-profile";
  const DEFAULT_MODE = "v4step600";
  const DEFAULT_BACKEND = "raw";
  const DEFAULT_PROFILE = "auto";
  const MODES = ["v4step600", "lightx2v", "original"];
  const BACKENDS = ["raw", "ollama", "qwen35"];
  const PROFILES = ["auto", "int8", "fp16_bf16"];
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

  function valid(value, values) { return values.includes(String(value || "").toLowerCase()); }
  function remembered(key, values, fallback) {
    try {
      const value = window.localStorage.getItem(key);
      return valid(value, values) ? String(value).toLowerCase() : fallback;
    } catch (_) { return fallback; }
  }
  function remember(key, value) { try { window.localStorage.setItem(key, value); } catch (_) {} }
  function option(value, label) {
    const item = document.createElement("option");
    item.value = value;
    item.textContent = label;
    return item;
  }
  function group() { return state.presets.get(ENTRY_ID); }
  function selectedRef2va() { return selectedPreset()?.id === ENTRY_ID; }
  function targetId(mode, backend) {
    return `ref2va_${mode}_${backend}`;
  }
  function overridesValues(overrides) {
    return overrides?.values && typeof overrides.values === "object" ? overrides.values : {};
  }
  function candidate(overrides, key, fallback) {
    const values = overridesValues(overrides);
    return overrides?.[key] ?? values[key] ?? fallback;
  }
  function removePhysicalCreationChoices() {
    document.querySelectorAll("#preset-select option").forEach(item => {
      if (PHYSICAL.has(item.value)) item.remove();
    });
    document.querySelectorAll("#sheet-body [data-pick-workflow]").forEach(item => {
      if (PHYSICAL.has(item.dataset.pickWorkflow)) item.remove();
    });
  }
  function ensureField(grid, key, labelText, values, labels, storageKey, fallback, explicit) {
    let field = grid.querySelector(`[data-v048-ref2va-${key}-field]`);
    let select = field?.querySelector("select");
    if (!field) {
      field = document.createElement("label");
      field.className = "field";
      field.setAttribute(`data-v048-ref2va-${key}-field`, "true");
      field.innerHTML = `<span>${labelText}</span>`;
      select = document.createElement("select");
      select.setAttribute(`data-v048-ref2va-${key}`, "true");
      values.forEach((value, index) => select.append(option(value, labels[index])));
      field.append(select);
      grid.append(field);
      select.addEventListener("change", () => {
        if (valid(select.value, values)) remember(storageKey, select.value);
        updateRef2vaAvailability();
      });
    }
    const next = valid(explicit, values) ? String(explicit).toLowerCase() : remembered(storageKey, values, fallback);
    select.value = next;
    return select;
  }
  function ensureRef2vaFields(overrides = {}) {
    if (!selectedRef2va()) return;
    const grid = document.querySelector("#advanced-settings .advanced-grid");
    if (!grid) return;
    const mode = ensureField(grid, "generation-mode", "Generation Mode", MODES,
      ["v4step600", "LightX2V", "original"], STORAGE_MODE, DEFAULT_MODE,
      candidate(overrides, "generation_mode", null));
    const backend = ensureField(grid, "prompt-backend", "Prompt Backend", BACKENDS,
      ["Raw", "Ollama", "Qwen3.5 4B"], STORAGE_BACKEND, DEFAULT_BACKEND,
      candidate(overrides, "prompt_backend", null));
    const profile = ensureField(grid, "inference-profile", "Model Configuration", PROFILES,
      ["Auto", "INT8", "FP16/BF16"], STORAGE_PROFILE, DEFAULT_PROFILE,
      candidate(overrides, "inference_profile", null));
    mode.dataset.v048Ref2vaGenerationMode = "true";
    backend.dataset.v048Ref2vaPromptBackend = "true";
    profile.dataset.v048Ref2vaInferenceProfile = "true";
    updateRef2vaAvailability();
  }
  function currentRef2vaValues() {
    return {
      mode: document.querySelector("select[data-v048-ref2va-generation-mode]")?.value || DEFAULT_MODE,
      backend: document.querySelector("select[data-v048-ref2va-prompt-backend]")?.value || DEFAULT_BACKEND,
      profile: document.querySelector("select[data-v048-ref2va-inference-profile]")?.value || DEFAULT_PROFILE,
    };
  }
  function updateRef2vaAvailability() {
    if (!selectedRef2va()) return;
    const {mode, backend, profile} = currentRef2vaValues();
    const target = state.workflowItems?.get?.(targetId(mode, backend));
    const profileSelect = document.querySelector("select[data-v048-ref2va-inference-profile]");
    const variant = target?.manifest?.model_profile?.main_model?.variants?.fp16_bf16;
    const fp16 = profileSelect?.querySelector('option[value="fp16_bf16"]');
    if (fp16) {
      fp16.disabled = Boolean(variant && variant.available === false);
      fp16.title = fp16.disabled ? (variant.reason || "当前 Ref2VA BF16 变体不可用") : "";
    }
    if (profileSelect?.selectedOptions[0]?.disabled) profileSelect.value = DEFAULT_PROFILE;
    const submit = document.querySelector("#submit-button");
    const unavailable = backend === "qwen35" && (!target || target.status !== "enabled" || state.metrics?.presets?.[target.id]?.available !== true);
    if (submit && unavailable) {
      submit.disabled = true;
      submit.title = "当前 Ref2VA Qwen3.5 4B 工作流不可用";
    } else if (submit?.title === "当前 Ref2VA Qwen3.5 4B 工作流不可用") {
      submit.removeAttribute("title");
    }
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
  function addRef2vaRouting(formData) {
    if (String(formData.get("preset_id") || "") !== ENTRY_ID) return formData;
    const {mode, backend, profile} = currentRef2vaValues();
    const values = valuesFromFormData(formData);
    values.generation_mode = mode;
    values.prompt_backend = backend;
    values.inference_profile = profile;
    formData.delete("values_json");
    formData.set("values_json", JSON.stringify(values));
    return formData;
  }

  applyPreset = function(presetId, overrides = {}) {
    const result = baseApply(presetId, overrides);
    queueMicrotask(() => {
      removePhysicalCreationChoices();
      ensureRef2vaFields(overrides);
    });
    return result;
  };
  uploadForm = function(path, formData, onProgress) {
    if (path === "/api/jobs") addRef2vaRouting(formData);
    return baseUpload(path, formData, onProgress);
  };
  loadPresets = async function(...args) {
    const result = await baseLoadPresets(...args);
    removePhysicalCreationChoices();
    ensureRef2vaFields();
    return result;
  };
  loadWorkflows = async function(...args) {
    const result = await baseLoadWorkflows(...args);
    removePhysicalCreationChoices();
    ensureRef2vaFields();
    return result;
  };

  document.addEventListener("DOMContentLoaded", () => {
    const advanced = document.querySelector("#advanced-settings");
    const grid = advanced?.querySelector(".advanced-grid");
    if (grid) {
      new MutationObserver(() => queueMicrotask(() => ensureRef2vaFields()))
        .observe(grid, { childList: true });
    }
    queueMicrotask(() => {
      removePhysicalCreationChoices();
      ensureRef2vaFields();
    });
  });
})();
