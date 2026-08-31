(() => {
  const FL2VA_ENTRY_ID = "h3-fl2va-group";
  const DEFAULT_FL2VA_ASPECT = "9:16";

  const baseApplyPresetV046Selection = applyPreset;
  const baseLoadPresetsV046Selection = loadPresets;
  const baseLoadWorkflowsV046Selection = loadWorkflows;
  const baseUploadFormV046Selection = uploadForm;
  const baseApiActionV046Selection = apiAction;

  let explicitFl2vaAspect = null;
  let explicitFl2vaAspectSource = null;

  function renderedSpecializedFamily() {
    const fl2va = document.querySelector("#fl2va-media");
    const ref2va = document.querySelector("#ref2va-media");
    if (!fl2va || !ref2va) return null;
    const fl2vaVisible = !fl2va.classList.contains("hidden");
    const ref2vaVisible = !ref2va.classList.contains("hidden");
    if (fl2vaVisible && !ref2vaVisible) return "fl2va";
    if (ref2vaVisible && !fl2vaVisible) return "ref2va";
    return null;
  }

  function hasPresetOption(select, presetId) {
    return [...select.options].some(option => option.value === presetId);
  }

  function normalizeAspect(value) {
    if (typeof value !== "string" || !value.trim()) return null;
    const normalized = value.trim();
    return normalized === "reference_image" ? "reference" : normalized;
  }

  function aspectFromOverrides(overrides) {
    const values = overrides?.values && typeof overrides.values === "object"
      ? overrides.values
      : {};
    return normalizeAspect(overrides?.aspect_ratio ?? values.aspect_ratio);
  }

  function isFl2vaPreset(presetId) {
    if (presetId === FL2VA_ENTRY_ID) return true;
    return state.presets?.get?.(presetId)?.family === "fl2va";
  }

  function hasAspectOption(select, value) {
    return [...select.options].some(option => option.value === value);
  }

  function desiredFl2vaAspect(select) {
    if (explicitFl2vaAspect && hasAspectOption(select, explicitFl2vaAspect)) {
      return explicitFl2vaAspect;
    }
    return DEFAULT_FL2VA_ASPECT;
  }

  function restoreRenderedPresetInvariant() {
    const select = document.querySelector("#preset-select");
    if (!select) return;
    if (renderedSpecializedFamily() !== "fl2va") return;
    if (!hasPresetOption(select, FL2VA_ENTRY_ID)) return;

    // v0.4.2 rebuilds the hidden native select by removing and re-inserting
    // the virtual FL2VA option. Removing the selected option makes browsers
    // silently select the next option without firing change; v0.4.6 then
    // removes hidden Qwen physical choices, which can advance the value again
    // (often to Ref2VA) while the visible creation UI still shows FL2VA.
    // The rendered creation family is the user-visible source of truth here.
    if (select.value !== FL2VA_ENTRY_ID) select.value = FL2VA_ENTRY_ID;
  }

  function restoreRenderedAspectInvariant() {
    if (renderedSpecializedFamily() !== "fl2va") return;
    const select = document.querySelector('select[name="aspect_ratio"]');
    if (!select || !hasAspectOption(select, DEFAULT_FL2VA_ASPECT)) return;
    const desired = desiredFl2vaAspect(select);
    if (select.value === desired) return;
    select.value = desired;
    if (explicitFl2vaAspect) select.dataset.v046AspectExplicit = "true";
    else delete select.dataset.v046AspectExplicit;
    select.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function restoreRenderedInvariants() {
    restoreRenderedPresetInvariant();
    restoreRenderedAspectInvariant();
  }

  applyPreset = function(presetId, overrides = {}) {
    const aspect = aspectFromOverrides(overrides);
    if (aspect && isFl2vaPreset(presetId)) {
      explicitFl2vaAspect = aspect;
      explicitFl2vaAspectSource = "override";
    }
    const result = baseApplyPresetV046Selection(presetId, overrides);
    queueMicrotask(restoreRenderedInvariants);
    return result;
  };

  loadPresets = async function(...args) {
    const result = await baseLoadPresetsV046Selection(...args);
    queueMicrotask(restoreRenderedInvariants);
    return result;
  };

  loadWorkflows = async function(...args) {
    const result = await baseLoadWorkflowsV046Selection(...args);
    queueMicrotask(restoreRenderedInvariants);
    return result;
  };

  apiAction = async function(path, options = {}) {
    const result = await baseApiActionV046Selection(path, options);
    const method = String(options.method || "GET").toUpperCase();
    if (method === "POST" && /^\/api\/workflows\/[^/]+\/status$/.test(path)) {
      // v0.4.2 schedules its group-select rebuild with setTimeout after this
      // request. Schedule the invariant restore afterward in the same timer
      // queue so a status toggle cannot leave the hidden select on Ref2VA or
      // an unrelated hidden aspect value.
      window.setTimeout(restoreRenderedInvariants, 0);
    }
    return result;
  };

  uploadForm = function(path, formData, onProgress) {
    if (path === "/api/jobs" && renderedSpecializedFamily() === "fl2va") {
      restoreRenderedInvariants();
      const presetSelect = document.querySelector("#preset-select");
      if (presetSelect && hasPresetOption(presetSelect, FL2VA_ENTRY_ID)) {
        presetSelect.value = FL2VA_ENTRY_ID;
        // FormData was constructed before uploadForm is called. Repair the
        // captured scalar as well so the v0.4.2/v0.4.6 routing wrappers that
        // run underneath this guard see the same FL2VA entry the user sees.
        formData.set("preset_id", FL2VA_ENTRY_ID);
      }

      const aspectSelect = document.querySelector('select[name="aspect_ratio"]');
      if (aspectSelect && hasAspectOption(aspectSelect, DEFAULT_FL2VA_ASPECT)) {
        const desired = desiredFl2vaAspect(aspectSelect);
        aspectSelect.value = desired;
        formData.set("aspect_ratio", desired);
      }
    }
    return baseUploadFormV046Selection(path, formData, onProgress);
  };

  document.addEventListener("DOMContentLoaded", () => {
    queueMicrotask(restoreRenderedInvariants);

    document.addEventListener("click", event => {
      const aspectButton = event.target.closest?.("[data-sheet-aspect]");
      if (aspectButton && renderedSpecializedFamily() === "fl2va") {
        const aspect = normalizeAspect(aspectButton.dataset.sheetAspect);
        if (aspect) {
          explicitFl2vaAspect = aspect;
          explicitFl2vaAspectSource = "user";
        }
      }

      if (event.target.closest?.("#clear-retry") && explicitFl2vaAspectSource === "override") {
        explicitFl2vaAspect = null;
        explicitFl2vaAspectSource = null;
        queueMicrotask(restoreRenderedAspectInvariant);
      }
    }, true);

    document.querySelector("#preset-select")?.addEventListener("change", () => {
      queueMicrotask(restoreRenderedInvariants);
    });
  });
})();
