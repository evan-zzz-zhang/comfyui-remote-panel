(() => {
  const adapters = new Map();
  const baseApplyPreset = applyPreset;
  const baseLoadPresets = loadPresets;
  const baseLoadWorkflows = loadWorkflows;
  const baseUploadForm = uploadForm;
  const baseUpdateSubmitAvailability = updateSubmitAvailability;

  function registerAdapter(adapter) {
    if (!adapter?.family) return;
    adapters.set(adapter.family, adapter);
    window.ComfyRemoteH3AdvancedSettings?.registerAdapter?.(adapter);
  }
  function refreshAdapters() {
    for (const adapter of adapters.values()) adapter.refresh?.();
    hidePhysicalChoices();
  }
  function hidePhysicalChoices() {
    const physical = new Set([...adapters.values()].flatMap(adapter => [...(adapter.physicalPresetIds || [])]));
    document.querySelectorAll("#preset-select option").forEach(option => { if (physical.has(option.value)) option.remove(); });
    document.querySelectorAll("#sheet-body [data-pick-workflow]").forEach(item => { if (physical.has(item.dataset.pickWorkflow)) item.remove(); });
  }
  function finishH3Apply(adapter) {
    hidePhysicalChoices();
    if (adapter.family !== "fl2va" || selectedPreset?.()?.id !== adapter.entryId) return;
    const select = document.querySelector('select[name="aspect_ratio"]');
    const reference = document.querySelector("#reference-aspect-image-option");
    if (reference) { reference.value = "reference"; reference.textContent = "参考图"; reference.hidden = false; reference.disabled = false; }
    if (select && [...select.options].some(option => option.value === "9:16") && !select.value) select.value = "9:16";
    const prompt = document.querySelector('textarea[name="prompt"]');
    const hasFrame = ["#first-frame", "#last-frame"].some(selector => document.querySelector(selector)?.files?.length)
      || (state.retryRoles || []).some(role => role === "first" || role === "last");
    if (prompt) prompt.required = window.ComfyRemoteH3AdvancedSettings?.getState?.()?.promptBackend === "raw" ? !hasFrame : true;
  }
  function adapterForPreset(presetId) {
    const current = state.presets?.get?.(presetId);
    for (const adapter of adapters.values()) {
      if (adapter.isEntry?.(current) || adapter.mapPreset?.(presetId)) return adapter;
    }
    return null;
  }
  function mergedOverrides(overrides) {
    return overrides?.values && typeof overrides.values === "object"
      ? { ...overrides, ...overrides.values } : (overrides || {});
  }
  function applyPresetWithH3(presetId, overrides = {}) {
    refreshAdapters();
    const adapter = adapterForPreset(presetId);
    if (!adapter) {
      window.ComfyRemoteH3AdvancedSettings?.unmount?.();
      return baseApplyPreset(presetId, overrides);
    }
    const mapped = adapter.mapPreset?.(presetId, overrides) || { presetId, overrides };
    const nextOverrides = mergedOverrides(mapped.overrides);
    const result = baseApplyPreset(mapped.presetId, nextOverrides);
    finishH3Apply(adapter);
    return result;
  }
  async function loadPresetsWithH3(...args) {
    const result = await baseLoadPresets(...args);
    refreshAdapters();
    const selected = selectedPreset?.();
    if (!selected) {
      const fl = adapters.get("fl2va")?.refresh?.();
      if (fl) applyPresetWithH3(fl.id);
    }
    return result;
  }
  async function loadWorkflowsWithH3(...args) {
    const result = await baseLoadWorkflows(...args);
    refreshAdapters();
    return result;
  }
  function uploadFormWithH3(path, formData, onProgress) {
    if (path === "/api/jobs") {
      const adapter = adapters.get(state.presets?.get?.(String(formData.get("preset_id") || ""))?.family);
      if (adapter) adapter.augmentFormData?.(formData, window.ComfyRemoteH3AdvancedSettings?.getSubmissionState?.() || window.ComfyRemoteH3AdvancedSettings?.getState?.() || {});
    }
    return baseUploadForm(path, formData, onProgress);
  }
  function updateSubmitAvailabilityWithH3(...args) {
    baseUpdateSubmitAvailability(...args);
    const preset = selectedPreset?.();
    const adapter = adapters.get(preset?.family);
    const button = document.querySelector("#submit-button");
    if (!adapter || !button) return;
    const ui = window.ComfyRemoteH3AdvancedSettings?.getState?.() || {};
    const available = adapter.getSubmitAvailability?.(ui);
    if (available === false) {
      button.disabled = true;
      button.dataset.h3RuntimeUnavailable = "true";
      button.title = "当前工作流不可用";
    } else if (available === true && button.dataset.h3RuntimeUnavailable === "true") {
      delete button.dataset.h3RuntimeUnavailable;
      button.removeAttribute("title");
      button.disabled = Boolean(state.isSubmitting);
    }
  }
  function mount(preset, overrides = {}) {
    const adapter = adapters.get(preset?.family);
    if (!adapter) return false;
    window.ComfyRemoteH3AdvancedSettings?.mount?.(adapter, preset, overrides);
    return true;
  }

  window.H3CreationRuntime = {
    registerAdapter,
    refresh: refreshAdapters,
    getAdapter: family => adapters.get(family),
    mount,
    getAdapters: () => new Map(adapters),
  };
  applyPreset = applyPresetWithH3;
  loadPresets = loadPresetsWithH3;
  loadWorkflows = loadWorkflowsWithH3;
  uploadForm = uploadFormWithH3;
  updateSubmitAvailability = updateSubmitAvailabilityWithH3;
  document.addEventListener("DOMContentLoaded", () => {
    refreshAdapters();
    window.ComfyRemoteH3AdvancedSettings?.bind?.();
  });
})();
