(() => {
  const ENTRY_ID = "h3-fl2va-group";
  const ORIGINAL_ID = "h3-fl2va";
  const DEFAULT_MODE = "v4_600step";
  const DEFAULT_OLLAMA_MODEL = "gemma4:e4b";
  const MODE_STORAGE_KEY = "comfy-remote.fl2va.generation-mode";
  const OLLAMA_STORAGE_KEY = "comfy-remote.fl2va.ollama-model";
  const FALLBACK_MODES = {
    v4_600step: { label: "v4_600step", preset_id: "h3-fl2va-v4step600" },
    lightx2v: { label: "LightX2V", preset_id: "h3-fl2va-lightx2v" },
    original: { label: "原版", preset_id: ORIGINAL_ID },
  };
  const LEGACY_PHYSICAL_IDS = new Set([
    "h3-fl2va", "h3-fl2va-lightx2v", "h3-fl2va-v4step600",
    "h3-fl2va-qwen35-4b", "h3-fl2va-lightx2v-qwen35-4b", "h3-fl2va-v4step600-qwen35-4b",
    "fl2va_original_raw", "fl2va_original_ollama", "fl2va_original_qwen35",
    "fl2va_v4step600_raw", "fl2va_v4step600_ollama", "fl2va_v4step600_qwen35",
    "fl2va_lightx2v_raw", "fl2va_lightx2v_ollama", "fl2va_lightx2v_qwen35",
  ]);

  const baseLoadPresetsV042 = loadPresets;
  const baseLoadWorkflowsV042 = loadWorkflows;
  const baseApplyPresetV042 = applyPreset;
  const baseUpdateSubmitAvailabilityV042 = updateSubmitAvailability;
  const baseUploadFormV042 = uploadForm;
  const baseApiActionV042 = apiAction;

  function mergedOverrides(overrides) {
    if (overrides?.values && typeof overrides.values === "object") {
      return { ...overrides, ...overrides.values };
    }
    return overrides || {};
  }

  function originalWorkflowItem() {
    return state.workflowItems?.get?.(ORIGINAL_ID) || null;
  }

  function modeConfig() {
    return state.presets.get(ENTRY_ID)?.generation_modes
      || state.presets.get(ORIGINAL_ID)?.generation_modes
      || originalWorkflowItem()?.manifest?.generation_modes
      || { default: DEFAULT_MODE, values: FALLBACK_MODES };
  }

  function modeDefinitions() {
    const values = modeConfig()?.values;
    return values && typeof values === "object" ? values : FALLBACK_MODES;
  }

  function physicalPresetIds() {
    return new Set([
      ...LEGACY_PHYSICAL_IDS,
      ...Object.values(modeDefinitions()).map(item => item?.preset_id).filter(Boolean),
    ]);
  }

  function modeForPreset(presetId) {
    return Object.entries(modeDefinitions()).find(([, item]) => item?.preset_id === presetId)?.[0] || null;
  }

  function validMode(value) {
    return Object.prototype.hasOwnProperty.call(modeDefinitions(), value);
  }

  function modeEnabled(mode) {
    const definition = modeDefinitions()[mode];
    if (!definition?.preset_id) return false;
    const item = state.workflowItems?.get?.(definition.preset_id);
    return item?.status === "enabled";
  }

  function enabledModes() {
    return Object.keys(modeDefinitions()).filter(modeEnabled);
  }

  function preferredMode(candidate) {
    if (validMode(candidate) && modeEnabled(candidate)) return candidate;
    try {
      const stored = window.localStorage.getItem(MODE_STORAGE_KEY);
      if (validMode(stored) && modeEnabled(stored)) return stored;
    } catch (_) {}
    const configured = modeConfig()?.default;
    if (validMode(configured) && modeEnabled(configured)) return configured;
    if (modeEnabled(DEFAULT_MODE)) return DEFAULT_MODE;
    return enabledModes()[0] || null;
  }

  function targetWorkflowItem(mode) {
    const definition = modeDefinitions()[mode];
    return definition?.preset_id ? state.workflowItems?.get?.(definition.preset_id) || null : null;
  }

  function targetPreset(mode) {
    const item = targetWorkflowItem(mode);
    return item ? state.presets.get(item.id) || item.manifest || null : null;
  }

  function targetAvailable(mode) {
    const item = targetWorkflowItem(mode);
    if (!item || item.status !== "enabled") return false;
    return state.metrics?.presets?.[item.id]?.available === true;
  }

  function defaultOllamaModel(mode) {
    const value = targetPreset(mode)?.parameters?.ollama_model?.default
      ?? state.presets.get(ENTRY_ID)?.parameters?.ollama_model?.default
      ?? DEFAULT_OLLAMA_MODEL;
    return String(value || DEFAULT_OLLAMA_MODEL).trim() || DEFAULT_OLLAMA_MODEL;
  }

  function preferredOllamaModel(candidate, mode) {
    if (typeof candidate === "string" && candidate.trim()) return candidate.trim();
    try {
      const stored = window.localStorage.getItem(OLLAMA_STORAGE_KEY);
      if (stored?.trim()) return stored.trim();
    } catch (_) {}
    return defaultOllamaModel(mode);
  }

  function rememberOllamaModel(value) {
    const model = String(value || "").trim();
    if (!model) return;
    try { window.localStorage.setItem(OLLAMA_STORAGE_KEY, model); } catch (_) {}
  }

  function publicParametersFromManifest(manifest) {
    const family = manifest?.family || "fl2va";
    const parameters = {};
    for (const [name, spec] of Object.entries(manifest?.parameters || {})) {
      if (family !== "generic" && (name === "prompt" || name === "seed")) continue;
      parameters[name] = Object.fromEntries(
        ["type", "minimum", "maximum", "step", "default", "values", "ui"]
          .filter(key => Object.prototype.hasOwnProperty.call(spec, key))
          .map(key => [key, spec[key]])
      );
    }
    return parameters;
  }

  function buildGroupPreset() {
    if (!enabledModes().length) return null;
    const originalItem = originalWorkflowItem();
    const manifest = originalItem?.manifest || null;
    const source = state.presets.get(ORIGINAL_ID)
      || enabledModes().map(mode => targetPreset(mode)).find(Boolean)
      || null;
    if (!manifest && !source) return null;
    return {
      ...(source || {}),
      id: ENTRY_ID,
      name: "MiniMax H3 FL2VA",
      family: "fl2va",
      description: "首尾帧视频生成 · 原版 / LightX2V / v4_600step",
      parameters: manifest ? publicParametersFromManifest(manifest) : { ...(source?.parameters || {}) },
      input_bindings: manifest?.input_bindings || source?.input_bindings || { media: { type: "frame_pair", roles: { first: "first_frame", last: "last_frame" } } },
      output_bindings: manifest?.output_bindings || source?.output_bindings || [],
      generation_modes: manifest?.generation_modes || source?.generation_modes || { default: DEFAULT_MODE, values: FALLBACK_MODES },
      available: true,
      diagnostics: [],
    };
  }

  function fallbackVisiblePreset() {
    const physical = physicalPresetIds();
    return [...state.presets.values()].find(preset => {
      if (!preset || preset.id === ENTRY_ID || physical.has(preset.id)) return false;
      const item = state.workflowItems?.get?.(preset.id);
      return !item || item.status === "enabled";
    }) || null;
  }

  function syncNativePresetSelect(group) {
    const select = document.querySelector("#preset-select");
    if (!select) return;
    const physical = physicalPresetIds();
    for (const option of [...select.options]) {
      if (physical.has(option.value) || option.value === ENTRY_ID) option.remove();
    }
    if (group) {
      const option = document.createElement("option");
      option.value = ENTRY_ID;
      option.textContent = group.name;
      select.prepend(option);
    }
  }

  function installGroupPreset() {
    const group = buildGroupPreset();
    if (group) state.presets.set(ENTRY_ID, group);
    else state.presets.delete(ENTRY_ID);
    syncNativePresetSelect(group);
    return group;
  }

  function hidePhysicalWorkflowChoices() {
    const physical = physicalPresetIds();
    document.querySelectorAll("#sheet-body [data-pick-workflow]").forEach(button => {
      if (physical.has(button.dataset.pickWorkflow)) button.remove();
    });
  }

  function syncPromptRequired() {
    const prompt = document.querySelector('textarea[name="prompt"]');
    const backend = window.ComfyRemoteH3AdvancedSettings?.getState?.()?.promptBackend;
    const hasFrame = ["#first-frame", "#last-frame"].some(selector => {
      const input = document.querySelector(selector);
      return Boolean(input?.files?.length);
    }) || (state.retryRoles || []).some(role => role === "first" || role === "last");
    if (prompt) prompt.required = backend === "raw" ? !hasFrame : true;
  }

  function parseValuesJsonEntries(formData) {
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

  function resolutionOverrideFromDom() {
    const result = {};
    const hidden = document.querySelector('#job-form [data-generic-binding="media_resolution"]');
    if (hidden?.value) {
      try {
        const parsed = JSON.parse(hidden.value);
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) Object.assign(result, parsed);
      } catch (_) {}
    }
    document.querySelectorAll("#job-form [data-v04-resolution]").forEach(select => {
      const value = select.value;
      const setting = value === "original"
        ? { policy: "original", target_megapixels: null }
        : { policy: "auto", target_megapixels: Number(value) };
      const role = select.dataset.v04Resolution;
      if (role === "image" && selectedPreset()?.input_bindings?.media?.type === "frame_pair") {
        result.first = setting;
        result.last = setting;
      } else if (role) {
        result[role] = setting;
      }
    });
    return Object.keys(result).length ? result : null;
  }

  function dedupeScalarFields(formData) {
    for (const name of ["preset_id", "prompt", "duration_seconds", "aspect_ratio", "megapixels", "seed", "scheduler", "sampler", "steps", "retry_source_id", "retry_keep_roles"]) {
      const entries = formData.getAll(name);
      if (entries.length <= 1) continue;
      const value = entries[entries.length - 1];
      formData.delete(name);
      formData.set(name, value);
    }
  }

  function augmentJobFormData(formData) {
    if (String(formData.get("preset_id") || "") !== ENTRY_ID) return formData;
    dedupeScalarFields(formData);
    const ui = window.ComfyRemoteH3AdvancedSettings?.getState?.() || {};
    const mode = preferredMode(ui.generationMode);
    const standardize = ui.promptBackend !== "raw";
    const ollamaModel = preferredOllamaModel(ui.ollamaModel, mode);
    rememberOllamaModel(ollamaModel);
    const values = parseValuesJsonEntries(formData);
    const directMediaResolution = formData.get("media_resolution");
    if (typeof directMediaResolution === "string" && directMediaResolution) {
      try { values.media_resolution = JSON.parse(directMediaResolution); } catch (_) {}
    }
    const mediaResolution = resolutionOverrideFromDom();
    if (mediaResolution) values.media_resolution = mediaResolution;
    values.generation_mode = mode;
    values.prompt_standardization = standardize;
    values.ollama_model = ollamaModel;
    formData.delete("media_resolution");
    formData.delete("values_json");
    formData.set("values_json", JSON.stringify(values));
    return formData;
  }

  applyPreset = function(presetId, overrides = {}) {
    const directMode = presetId === ENTRY_ID ? null : modeForPreset(presetId);
    const isUnifiedFl2va = presetId === ENTRY_ID || directMode !== null;
    if (!isUnifiedFl2va) {
      return baseApplyPresetV042(presetId, overrides);
    }

    installGroupPreset();
    const merged = mergedOverrides(overrides);
    const mode = preferredMode(merged.generation_mode ?? directMode);
    if (!mode || !state.presets.has(ENTRY_ID)) {
      return;
    }

    const nextOverrides = { ...overrides, generation_mode: mode };
    const result = baseApplyPresetV042(ENTRY_ID, nextOverrides);
    return result;
  };

  function syncGroupSelection() {
    const group = installGroupPreset();
    const select = document.querySelector("#preset-select");
    if (!select) return;
    if (!group) {
      if (select.value === ENTRY_ID || physicalPresetIds().has(select.value)) {
        const fallback = fallbackVisiblePreset();
        if (fallback) applyPreset(fallback.id);
        else {
          select.value = "";
          const button = document.querySelector("#submit-button");
          if (button) button.disabled = true;
        }
      }
      return;
    }
    if (select.value === ENTRY_ID || physicalPresetIds().has(select.value) || !select.value) {
      const mode = preferredMode(window.ComfyRemoteH3AdvancedSettings?.getState?.()?.generationMode);
      applyPreset(ENTRY_ID, { generation_mode: mode });
    }
    hidePhysicalWorkflowChoices();
  }

  loadPresets = async function() {
    const result = await baseLoadPresetsV042();
    const group = installGroupPreset();
    if (group) applyPreset(ENTRY_ID);
    hidePhysicalWorkflowChoices();
    return result;
  };

  loadWorkflows = async function(...args) {
    const result = await baseLoadWorkflowsV042(...args);
    queueMicrotask(syncGroupSelection);
    return result;
  };

  apiAction = async function(path, options = {}) {
    const result = await baseApiActionV042(path, options);
    const method = String(options.method || "GET").toUpperCase();
    if (method === "POST" && /^\/api\/workflows\/[^/]+\/status$/.test(path)) {
      window.setTimeout(syncGroupSelection, 0);
    }
    return result;
  };

  uploadForm = function(path, formData, onProgress) {
    if (path === "/api/jobs") augmentJobFormData(formData);
    return baseUploadFormV042(path, formData, onProgress);
  };

  updateSubmitAvailability = function() {
    baseUpdateSubmitAvailabilityV042();
    const preset = selectedPreset();
    if (preset?.id !== ENTRY_ID) return;
    const button = document.querySelector("#submit-button");
    const mode = preferredMode(window.ComfyRemoteH3AdvancedSettings?.getState?.()?.generationMode);
    const available = Boolean(mode && modeEnabled(mode) && targetAvailable(mode));
    if (button && !available) button.disabled = true;
  };

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelector("#workflow-picker-button")?.addEventListener("click", () => {
      window.setTimeout(hidePhysicalWorkflowChoices, 0);
    });
    const form = document.querySelector("#job-form");
    form?.addEventListener("change", event => {
      if (event.target?.matches?.("#first-frame, #last-frame")) syncPromptRequired();
    });
    const sheet = document.querySelector("#sheet-body");
    if (sheet) new MutationObserver(() => queueMicrotask(hidePhysicalWorkflowChoices)).observe(sheet, { childList: true });
  });
})();
