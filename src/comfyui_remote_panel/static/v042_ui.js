(() => {
  const ENTRY_ID = "h3-fl2va";
  const DEFAULT_MODE = "v4_600step";
  const MODE_STORAGE_KEY = "comfy-remote.fl2va.generation-mode";
  const FALLBACK_MODES = {
    v4_600step: { label: "v4_600step", preset_id: "h3-fl2va-v4step600" },
    lightx2v: { label: "LightX2V", preset_id: "h3-fl2va-lightx2v" },
    original: { label: "原版", preset_id: "h3-fl2va" },
  };

  const baseApplyPresetV042 = applyPreset;
  const baseUpdateSubmitAvailabilityV042 = updateSubmitAvailability;

  function mergedOverrides(overrides) {
    if (overrides?.values && typeof overrides.values === "object") {
      return { ...overrides, ...overrides.values };
    }
    return overrides || {};
  }

  function modeConfig() {
    return state.presets.get(ENTRY_ID)?.generation_modes || {
      default: DEFAULT_MODE,
      values: FALLBACK_MODES,
    };
  }

  function modeDefinitions() {
    const values = modeConfig()?.values;
    return values && typeof values === "object" ? values : FALLBACK_MODES;
  }

  function modeForPreset(presetId) {
    return Object.entries(modeDefinitions()).find(([, item]) => item?.preset_id === presetId)?.[0] || null;
  }

  function validMode(value) {
    return Object.prototype.hasOwnProperty.call(modeDefinitions(), value);
  }

  function storedMode() {
    try {
      const value = window.localStorage.getItem(MODE_STORAGE_KEY);
      if (validMode(value)) return value;
    } catch (_) {}
    const configured = modeConfig()?.default;
    return validMode(configured) ? configured : DEFAULT_MODE;
  }

  function rememberMode(mode) {
    if (!validMode(mode)) return;
    try { window.localStorage.setItem(MODE_STORAGE_KEY, mode); } catch (_) {}
  }

  function targetPreset(mode) {
    const definition = modeDefinitions()[mode];
    return definition ? state.presets.get(definition.preset_id) : null;
  }

  function tuningDefaults(mode) {
    const preset = targetPreset(mode);
    if (!preset) return {};
    return {
      scheduler: preset.parameters?.scheduler?.default,
      sampler: preset.parameters?.sampler?.default,
      steps: preset.parameters?.steps?.default,
    };
  }

  function modeOptions(mode) {
    return Object.entries(modeDefinitions()).map(([id, item]) =>
      `<option value="${escapeHtml(id)}"${id === mode ? " selected" : ""}>${escapeHtml(item?.label || id)}</option>`
    ).join("");
  }

  function syncValuesJson() {
    const hidden = document.querySelector("#v042-fl2va-values");
    const mode = document.querySelector("[data-v042-generation-mode]")?.value;
    const standardize = document.querySelector("[data-v042-prompt-standardization]")?.checked;
    if (!hidden || !validMode(mode)) return;
    hidden.value = JSON.stringify({
      generation_mode: mode,
      prompt_standardization: standardize !== false,
    });
  }

  function applyModeDefaults(mode) {
    const preset = targetPreset(mode);
    if (!preset) return;
    const scheduler = document.querySelector('select[name="scheduler"]');
    const sampler = document.querySelector('select[name="sampler"]');
    const steps = document.querySelector('input[name="steps"]');
    if (scheduler && preset.parameters?.scheduler) {
      fillSelect(
        scheduler,
        Object.keys(preset.parameters.scheduler.values || {}),
        preset.parameters.scheduler.default
      );
    }
    if (sampler && preset.parameters?.sampler) {
      fillSelect(
        sampler,
        Object.keys(preset.parameters.sampler.values || {}),
        preset.parameters.sampler.default
      );
    }
    if (steps && preset.parameters?.steps) {
      steps.min = preset.parameters.steps.minimum;
      steps.max = preset.parameters.steps.maximum;
      steps.value = preset.parameters.steps.default;
    }
  }

  function syncPromptRequired() {
    const prompt = document.querySelector('textarea[name="prompt"]');
    const toggle = document.querySelector("[data-v042-prompt-standardization]");
    if (prompt) prompt.required = Boolean(toggle?.checked);
  }

  function removeControls() {
    document.querySelector("[data-v042-mode-field]")?.remove();
    document.querySelector("[data-v042-standardizer-field]")?.remove();
    document.querySelector("#v042-fl2va-values")?.remove();
  }

  function ensureControls(mode, standardization) {
    const preset = selectedPreset();
    const advanced = document.querySelector("#advanced-settings");
    const grid = advanced?.querySelector(".advanced-grid");
    const form = document.querySelector("#job-form");
    if (!preset || preset.id !== ENTRY_ID || !grid || !form) {
      removeControls();
      return;
    }

    let modeField = grid.querySelector("[data-v042-mode-field]");
    if (!modeField) {
      modeField = document.createElement("label");
      modeField.className = "field";
      modeField.dataset.v042ModeField = "true";
      modeField.innerHTML = `<span>生成模式</span><select data-v042-generation-mode></select>`;
      grid.prepend(modeField);
    }
    const modeSelect = modeField.querySelector("[data-v042-generation-mode]");
    modeSelect.innerHTML = modeOptions(mode);
    modeSelect.value = validMode(mode) ? mode : storedMode();

    let standardizerField = grid.querySelector("[data-v042-standardizer-field]");
    if (!standardizerField) {
      standardizerField = document.createElement("label");
      standardizerField.className = "field";
      standardizerField.dataset.v042StandardizerField = "true";
      standardizerField.innerHTML = `<span>使用 H3 提示词标准化</span><input type="checkbox" data-v042-prompt-standardization>`;
      modeField.insertAdjacentElement("afterend", standardizerField);
    }
    const checkbox = standardizerField.querySelector("[data-v042-prompt-standardization]");
    checkbox.checked = standardization !== false;
    checkbox.defaultChecked = true;

    let hidden = form.querySelector("#v042-fl2va-values");
    if (!hidden) {
      hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.id = "v042-fl2va-values";
      hidden.name = "values_json";
      form.append(hidden);
    }

    modeSelect.onchange = () => {
      const next = modeSelect.value;
      if (!validMode(next)) return;
      rememberMode(next);
      applyModeDefaults(next);
      syncValuesJson();
      updateSubmitAvailability();
    };
    checkbox.onchange = () => {
      syncValuesJson();
      syncPromptRequired();
    };
    syncValuesJson();
    syncPromptRequired();
  }

  applyPreset = function(presetId, overrides = {}) {
    const merged = mergedOverrides(overrides);
    const directMode = modeForPreset(presetId);
    const visibleId = directMode ? ENTRY_ID : presetId;
    const isUnifiedFl2va = visibleId === ENTRY_ID;
    const mode = isUnifiedFl2va
      ? (validMode(merged.generation_mode) ? merged.generation_mode : (directMode || storedMode()))
      : null;

    let nextOverrides = overrides;
    if (isUnifiedFl2va) {
      const hasExplicitTuning = ["scheduler", "sampler", "steps"].some(
        key => merged[key] !== undefined && merged[key] !== null && merged[key] !== ""
      );
      if (!hasExplicitTuning) {
        nextOverrides = { ...overrides, ...tuningDefaults(mode) };
      }
    }

    const result = baseApplyPresetV042(visibleId, nextOverrides);
    if (isUnifiedFl2va) {
      const refreshed = mergedOverrides(nextOverrides);
      const standardization = merged.prompt_standardization
        ?? refreshed.prompt_standardization
        ?? state.presets.get(ENTRY_ID)?.parameters?.prompt_standardization?.default
        ?? true;
      ensureControls(mode, standardization);
    } else {
      removeControls();
    }
    return result;
  };

  updateSubmitAvailability = function() {
    baseUpdateSubmitAvailabilityV042();
    const preset = selectedPreset();
    if (preset?.id !== ENTRY_ID) return;
    const button = document.querySelector("#submit-button");
    const mode = document.querySelector("[data-v042-generation-mode]")?.value || storedMode();
    const target = targetPreset(mode);
    const runtime = state.metrics?.presets?.[target?.id];
    const available = target && (runtime ? runtime.available : target.available);
    if (button && !available) button.disabled = true;
  };

  function hideModeWorkflowsFromPicker() {
    const hiddenIds = new Set(
      Object.values(modeDefinitions())
        .map(item => item?.preset_id)
        .filter(id => id && id !== ENTRY_ID)
    );
    document.querySelectorAll("[data-pick-workflow]").forEach(button => {
      if (hiddenIds.has(button.dataset.pickWorkflow)) button.remove();
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    const picker = document.querySelector("#workflow-picker-button");
    picker?.addEventListener("click", () => {
      window.setTimeout(hideModeWorkflowsFromPicker, 0);
    });

    const form = document.querySelector("#job-form");
    form?.addEventListener("change", event => {
      if (event.target?.matches?.("#first-frame, #last-frame")) syncPromptRequired();
    });
  });
})();
