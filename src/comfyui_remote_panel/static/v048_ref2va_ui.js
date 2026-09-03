(() => {
  const ENTRY_ID = "h3-ref2va-group";
  const STORAGE_MODE = "comfy-remote.ref2va.generation-mode";
  const STORAGE_BACKEND = "comfy-remote.ref2va.prompt-backend";
  const STORAGE_PROFILE = "comfy-remote.ref2va.inference-profile";
  const STORAGE_OLLAMA_MODEL = "comfy-remote.ref2va.ollama-model";
  const DEFAULT_MODE = "v4step600";
  const DEFAULT_BACKEND = "raw";
  const DEFAULT_PROFILE = "int8";
  const DEFAULT_OLLAMA_MODEL = "gemma4:e4b";
  const MODES = ["v4step600", "lightx2v", "original"];
  const BACKENDS = ["raw", "ollama", "qwen35"];
  const PROFILES = ["int8", "fp16_bf16"];
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

  function valid(value, values) { return values.includes(String(value || "").toLowerCase()); }
  function remembered(key, values, fallback) {
    try {
      const value = window.localStorage.getItem(key);
      return valid(value, values) ? String(value).toLowerCase() : fallback;
    } catch (_) { return fallback; }
  }
  function remember(key, value) { try { window.localStorage.setItem(key, value); } catch (_) {} }
  function rememberedText(key, fallback) {
    try { return window.localStorage.getItem(key)?.trim() || fallback; } catch (_) { return fallback; }
  }
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
  function mergedOverrides(overrides) {
    return { ...overrides, ...overridesValues(overrides) };
  }
  function canonicalMode(value) {
    const mode = String(value || "").toLowerCase();
    return mode === "v4_600step" ? "v4step600" : mode;
  }
  function visibleProfile(value) {
    const profile = String(value || "").toLowerCase();
    return profile === "auto" ? "int8" : profile;
  }
  function preferredMode(value) {
    const explicit = canonicalMode(value);
    if (valid(explicit, MODES)) return explicit;
    const live = canonicalMode(document.querySelector("select[data-v048-ref2va-generation-mode]")?.value);
    if (valid(live, MODES)) return live;
    return remembered(STORAGE_MODE, MODES, DEFAULT_MODE);
  }
  function removePhysicalCreationChoices() {
    document.querySelectorAll("#preset-select option").forEach(item => {
      if (PHYSICAL.has(item.value)) item.remove();
    });
    document.querySelectorAll("#sheet-body [data-pick-workflow]").forEach(item => {
      if (PHYSICAL.has(item.dataset.pickWorkflow)) item.remove();
    });
  }
  function ensureField(grid, key, labelText, values, labels, storageKey, fallback, explicit, normalize = value => String(value || "").toLowerCase()) {
    let field = grid.querySelector(`[data-v048-ref2va-${key}-field]`);
    let select = field?.querySelector("select");
    const live = normalize(select?.value);
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
        updateSubmitAvailability();
      });
    }
    const normalizedExplicit = normalize(explicit);
    const next = valid(normalizedExplicit, values)
      ? normalizedExplicit
      : valid(live, values)
        ? live
        : remembered(storageKey, values, fallback);
    select.value = next;
    return select;
  }
  function ensureOllamaField(grid, backend, explicit) {
    let field = grid.querySelector("[data-v048-ref2va-ollama-model-field]");
    let control = field?.querySelector("[data-v045-ollama-model]");
    const normalizedExplicit = typeof explicit === "string" ? explicit.trim() : "";
    const live = String(control?.value || "").trim();
    const next = normalizedExplicit || live || rememberedText(STORAGE_OLLAMA_MODEL, DEFAULT_OLLAMA_MODEL);
    if (!field) {
      field = document.createElement("label");
      field.className = "field";
      field.dataset.v048Ref2vaOllamaModelField = "true";
      field.dataset.ollamaStorageKey = STORAGE_OLLAMA_MODEL;
      field.innerHTML = '<span>Ollama 标准化模型</span><input type="text" autocomplete="off" data-v045-ollama-model>';
      grid.append(field);
      control = field.querySelector("[data-v045-ollama-model]");
    }
    if (control?.tagName === "SELECT" && ![...control.options].some(item => item.value === next)) {
      control.append(option(next, next));
    }
    if (control) control.value = next;
    field.hidden = backend !== "ollama";
    return control;
  }
  function positionRef2vaFields(grid) {
    const scheduler = grid.querySelector('select[name="scheduler"]')?.closest("label.field");
    if (!scheduler) return;
    let anchor = scheduler;
    for (const key of ["inference-profile", "ollama-model", "prompt-backend", "generation-mode"]) {
      const field = grid.querySelector(`[data-v048-ref2va-${key}-field]`);
      if (!field) continue;
      if (field.nextElementSibling !== anchor) grid.insertBefore(field, anchor);
      anchor = field;
    }
  }
  function applyModeDefaults(mode) {
    const defaults = MODE_TUNING[canonicalMode(mode)];
    if (!defaults) return;
    const scheduler = document.querySelector('select[name="scheduler"]');
    const sampler = document.querySelector('select[name="sampler"]');
    const steps = document.querySelector('input[name="steps"]');
    if (scheduler) scheduler.value = defaults.scheduler;
    if (sampler) sampler.value = defaults.sampler;
    if (steps) steps.value = String(defaults.steps);
  }
  function ensureRef2vaFields(overrides = {}) {
    if (!selectedRef2va()) {
      removeRef2vaFields();
      return;
    }
    const grid = document.querySelector("#advanced-settings .advanced-grid");
    if (!grid) return;
    if (!grid.querySelector("[data-v04-seed-policy]")) {
      window.ComfyRemoteCreationControls?.install?.(group(), overrides);
    }
    const mode = ensureField(grid, "generation-mode", "生成模式", MODES,
      ["v4_600step", "LightX2V", "原版"], STORAGE_MODE, DEFAULT_MODE,
      candidate(overrides, "generation_mode", null), canonicalMode);
    const backend = ensureField(grid, "prompt-backend", "标准化提示词", BACKENDS,
      ["原始提示词", "Ollama 标准化", "Qwen3.5 标准化"], STORAGE_BACKEND, DEFAULT_BACKEND,
      candidate(overrides, "prompt_backend", null));
    const ollamaModel = ensureOllamaField(
      grid, backend.value, candidate(overrides, "ollama_model", null)
    );
    const profile = ensureField(grid, "inference-profile", "主模型", PROFILES,
      ["pruned_int8", "pruned_bf16"], STORAGE_PROFILE, DEFAULT_PROFILE,
      candidate(overrides, "inference_profile", null), visibleProfile);
    mode.dataset.v048Ref2vaGenerationMode = "true";
    backend.dataset.v048Ref2vaPromptBackend = "true";
    if (ollamaModel) ollamaModel.dataset.v045OllamaModel = "true";
    profile.dataset.v048Ref2vaInferenceProfile = "true";
    mode.onchange = () => {
      if (!valid(mode.value, MODES)) return;
      remember(STORAGE_MODE, mode.value);
      applyModeDefaults(mode.value);
      updateSubmitAvailability();
    };
    backend.onchange = () => {
      if (!valid(backend.value, BACKENDS)) return;
      remember(STORAGE_BACKEND, backend.value);
      ensureOllamaField(grid, backend.value, null);
      updateSubmitAvailability();
    };
    positionRef2vaFields(grid);
    updateSubmitAvailability();
  }
  function removeRef2vaFields() {
    document.querySelectorAll(
      "[data-v048-ref2va-generation-mode-field], "
      + "[data-v048-ref2va-prompt-backend-field], "
      + "[data-v048-ref2va-ollama-model-field], "
      + "[data-v048-ref2va-inference-profile-field]"
    ).forEach(field => field.remove());
  }
  function currentRef2vaValues() {
    return {
      mode: document.querySelector("select[data-v048-ref2va-generation-mode]")?.value || DEFAULT_MODE,
      backend: document.querySelector("select[data-v048-ref2va-prompt-backend]")?.value || DEFAULT_BACKEND,
      profile: document.querySelector("select[data-v048-ref2va-inference-profile]")?.value || DEFAULT_PROFILE,
      ollamaModel: document.querySelector("[data-v048-ref2va-ollama-model-field] [data-v045-ollama-model]")?.value || DEFAULT_OLLAMA_MODEL,
    };
  }
  function updateRef2vaAvailability() {
    if (!selectedRef2va()) return;
    const {mode, backend, profile, ollamaModel} = currentRef2vaValues();
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
    if (!submit) return;
    const baseDisabled = submit.disabled;
    const baseTitle = submit.getAttribute("title");
    const available = Boolean(
      target
      && target.status === "enabled"
      && state.metrics?.presets?.[target.id]?.available === true
    );
    if (!available) {
      submit.disabled = true;
      submit.title = REF2VA_UNAVAILABLE_TITLE;
      submit.dataset.v048Ref2vaAvailability = "unavailable";
    } else if (submit.dataset.v048Ref2vaAvailability === "unavailable") {
      // Restore the base state so isSubmitting and other workflow guards keep
      // their authority when the Ref2VA target becomes available again.
      submit.disabled = baseDisabled;
      if (baseTitle) submit.title = baseTitle;
      else submit.removeAttribute("title");
      delete submit.dataset.v048Ref2vaAvailability;
    }
  }

  updateSubmitAvailability = function(...args) {
    baseUpdateSubmitAvailability(...args);
    updateRef2vaAvailability();
  };
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
    if (backend === "ollama") values.ollama_model = ollamaModel;
    else delete values.ollama_model;
    formData.delete("values_json");
    formData.set("values_json", JSON.stringify(values));
    return formData;
  }

  applyPreset = function(presetId, overrides = {}) {
    const merged = mergedOverrides(overrides);
    const mode = preferredMode(merged.generation_mode);
    const hasExplicitTuning = ["scheduler", "sampler", "steps"].some(
      key => merged[key] !== undefined && merged[key] !== null && merged[key] !== ""
    );
    const nextOverrides = presetId === ENTRY_ID && !hasExplicitTuning
      ? { ...overrides, ...MODE_TUNING[mode] }
      : overrides;
    const result = baseApply(presetId, nextOverrides);
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
    updateSubmitAvailability();
    return result;
  };
  loadWorkflows = async function(...args) {
    const result = await baseLoadWorkflows(...args);
    removePhysicalCreationChoices();
    ensureRef2vaFields();
    updateSubmitAvailability();
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
