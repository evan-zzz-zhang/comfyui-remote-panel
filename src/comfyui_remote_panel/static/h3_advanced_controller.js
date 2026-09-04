(() => {
  const ORDER = [
    "generation-mode", "prompt-backend", "main-model", "ollama-model",
    "scheduler", "sampler", "steps", "seed-policy", "seed-value",
    "reference-resolution",
  ];
  const BACKENDS = ["raw", "ollama", "qwen35"];
  const SEED_POLICIES = ["randomize", "fixed", "increment"];
  const RESOLUTION_VALUES = ["0.5", "1.0", "1.5", "2.0", "original"];
  const adapters = new Map();
  const familyStates = new Map();
  let activeState = null;
  let bound = false;

  function valuesOf(overrides) {
    return overrides?.values && typeof overrides.values === "object" ? overrides.values : {};
  }

  function candidate(overrides, ...keys) {
    const values = valuesOf(overrides);
    for (const key of keys) {
      const value = overrides?.[key] ?? values[key];
      if (value !== undefined && value !== null && value !== "") return value;
    }
    return undefined;
  }

  function stringValue(value) {
    return value === undefined || value === null ? "" : String(value);
  }

  function valid(value, options) {
    return options.includes(stringValue(value).toLowerCase());
  }

  function remember(key, value) {
    if (!key || value === undefined || value === null || value === "") return;
    try { window.localStorage.setItem(key, String(value)); } catch (_) {}
  }

  function remembered(key) {
    if (!key) return "";
    try { return window.localStorage.getItem(key) || ""; } catch (_) { return ""; }
  }

  function option(value, label) {
    const item = document.createElement("option");
    item.value = value;
    item.textContent = label;
    return item;
  }

  function setOptions(select, values, labels, selected) {
    const normalizedValues = values.map(value => String(value));
    const normalizedLabels = normalizedValues.map((value, index) => String(labels[index] ?? value));
    const currentOptions = [...select.options].map(item => [String(item.value), String(item.textContent)]);
    const nextOptions = normalizedValues.map((value, index) => [value, normalizedLabels[index]]);
    if (currentOptions.length !== nextOptions.length
      || currentOptions.some((item, index) => item[0] !== nextOptions[index][0] || item[1] !== nextOptions[index][1])) {
      select.replaceChildren(...nextOptions.map(([value, label]) => option(value, label)));
    }
    const desired = String(selected ?? "");
    if (normalizedValues.includes(desired)) select.value = desired;
    else if (!normalizedValues.includes(String(select.value))) select.value = normalizedValues[0] || "";
  }

  function imageSlotSpecs(preset) {
    const media = preset?.input_bindings?.media;
    if (!media) return [];
    if (media.type === "frame_pair") {
      return Object.keys(media.roles || {}).map(role => {
        const spec = media.resolution_defaults?.[role] || {};
        return {
          role,
          label: role === "first" ? "首帧" : role === "last" ? "尾帧" : role,
          policy: spec.resolution_policy || "auto",
          target: spec.target_megapixels ?? 1.0,
          allowAuto: spec.allow_auto !== false,
        };
      });
    }
    if (media.type === "collection" && media.kinds?.images?.max) {
      const spec = media.resolution_defaults?.image || {};
      return [{
        role: "image", label: "参考图", policy: spec.resolution_policy || "auto",
        target: spec.target_megapixels ?? 1.0, allowAuto: spec.allow_auto !== false,
      }];
    }
    if (media.type === "slots") {
      return Object.entries(media.slots || {})
        .filter(([, slot]) => (slot?.kind || "") === "image")
        .map(([role, slot]) => ({
          role,
          label: slot.ui?.label || role,
          policy: slot.resolution_policy || "original",
          target: slot.target_megapixels ?? 1.0,
          allowAuto: slot.allow_auto !== false,
        }));
    }
    return [];
  }

  function resolutionOptions(spec, selected) {
    const values = spec.allowAuto ? RESOLUTION_VALUES : ["original"];
    return values.map(value => option(
      value,
      value === "original" ? "保持原图" : `${value} MP`,
    )).map(item => {
      if (String(item.value) === String(selected)) item.selected = true;
      return item;
    });
  }

  function requestedResolution(spec, overrides, previous) {
    let supplied = candidate(overrides, "media_resolution") || previous;
    if (typeof supplied === "string") {
      try { supplied = JSON.parse(supplied); } catch (_) { supplied = previous; }
    }
    const value = supplied?.[spec.role] || (spec.role.startsWith("image_") ? supplied?.image : null);
    const policy = value?.policy || value?.resolution_policy || spec.policy;
    return policy === "auto" ? String(value?.target_megapixels ?? spec.target ?? 1.0) : "original";
  }

  function normalizeReferenceResolution(value, fallback = null) {
    if (typeof value === "string") {
      try { value = JSON.parse(value); } catch (_) { return fallback; }
    }
    return value && typeof value === "object" ? value : fallback;
  }

  function clone(value) {
    if (!value || typeof value !== "object") return value;
    return JSON.parse(JSON.stringify(value));
  }

  function fieldRole(field) {
    return field?.dataset?.h3AdvancedRole || "";
  }

  function managedFields(grid) {
    return [...grid.children].filter(node => node.matches?.("label.field") && fieldRole(node));
  }

  function normalize(grid = document.querySelector("#advanced-settings .advanced-grid")) {
    if (!grid) return;
    const fields = managedFields(grid);
    const unique = new Map();
    for (const field of fields) {
      const role = fieldRole(field);
      if (!unique.has(role)) unique.set(role, field);
      else field.remove();
    }
    const ordered = ORDER.map(role => unique.get(role)).filter(Boolean);
    const current = [...grid.children].filter(node => node.matches?.("label.field") && fieldRole(node));
    const currentRoles = current.map(fieldRole);
    const desiredRoles = ordered.map(fieldRole);
    if (currentRoles.length === desiredRoles.length
      && currentRoles.every((role, index) => role === desiredRoles[index])) return;
    const marker = document.createElement("span");
    marker.hidden = true;
    const first = current[0] || grid.firstElementChild;
    if (first) grid.insertBefore(marker, first);
    for (const field of current) field.remove();
    for (const field of ordered) grid.insertBefore(field, marker);
    marker.remove();
  }

  function removeLegacyFields(grid) {
    grid.querySelectorAll(
      "[data-v042-mode-field], [data-v042-standardizer-field], "
      + "[data-v045-ollama-model-field], [data-v047-inference-profile-field], "
      + "[data-v048-ref2va-generation-mode-field], [data-v048-ref2va-prompt-backend-field], "
      + "[data-v048-ref2va-ollama-model-field], [data-v048-ref2va-inference-profile-field]",
    ).forEach(field => {
      if (!field.dataset.h3Owned) field.remove();
    });
  }

  function ensureField(grid, role, key, label, values, labels, selected) {
    let field = grid.querySelector(`[data-h3-advanced-role="${role}"]`);
    if (!field) {
      field = document.createElement("label");
      field.className = "field";
      field.dataset.h3AdvancedRole = role;
      field.dataset.h3Owned = "true";
      field.innerHTML = `<span>${label}</span>`;
      const select = document.createElement("select");
      select.dataset[key] = "true";
      field.append(select);
      grid.append(field);
    }
    const select = field.querySelector("select");
    const current = select.value;
    setOptions(select, values, labels, valid(selected, values) ? String(selected).toLowerCase() : current);
    return { field, select };
  }

  function ensureOllamaField(grid, selected, state) {
    const result = ensureField(grid, "ollama-model", "h3OllamaModel", "Ollama 标准化模型", [], [], "");
    const select = result.select;
    select.dataset.v045OllamaModel = "true";
    select.dataset.h3OllamaModel = "true";
    if (selected && ![...select.options].some(item => item.value === selected)) {
      select.append(option(selected, selected));
    }
    if (selected) select.value = selected;
    result.field.hidden = state.promptBackend !== "ollama";
    result.field.dataset.h3OllamaField = "true";
    void window.H3OllamaModelService?.getModels?.().then(models => {
      if (!select.isConnected) return;
      const values = [...new Set([selected, ...models].filter(Boolean))];
      const live = select.value;
      setOptions(select, values, values, values.includes(live) ? live : selected);
    }).catch(() => {});
    return result;
  }

  function ensureSeedPolicy(grid, state) {
    const base = grid.querySelector('input[name="seed"]');
    const baseField = base?.closest("label.field");
    if (!base || !baseField) return;
    baseField.dataset.h3AdvancedRole = "seed-value";
    baseField.dataset.h3BaseField = "true";
    let field = grid.querySelector('[data-h3-advanced-role="seed-policy"]');
    if (!field) {
      field = document.createElement("label");
      field.className = "field";
      field.dataset.h3AdvancedRole = "seed-policy";
      field.dataset.h3Owned = "true";
      field.innerHTML = "<span>种子策略</span><select data-v04-seed-policy><option value=\"randomize\">随机</option><option value=\"fixed\">固定</option><option value=\"increment\">递增</option></select>";
      grid.append(field);
    }
    const select = field.querySelector("select");
    setOptions(select, SEED_POLICIES, ["随机", "固定", "递增"], state.seedPolicy);
    select.value = valid(state.seedPolicy, SEED_POLICIES) ? state.seedPolicy : "randomize";
    base.value = state.seedPolicy === "randomize" ? "" : state.seedValue;
    base.placeholder = state.seedPolicy === "increment" ? "起始 Seed" : "Seed";
    baseField.hidden = state.seedPolicy === "randomize";
    baseField.classList.remove("hidden");
    baseField.dataset.h3SeedValue = "true";
  }

  function ensureResolution(grid, preset, state) {
    const specs = imageSlotSpecs(preset);
    const existing = [...grid.querySelectorAll('[data-h3-advanced-role="reference-resolution"]')];
    if (!specs.length) {
      existing.forEach(field => field.remove());
      return;
    }
    // H3 exposes one product-level reference resolution control. Even when a
    // manifest describes multiple media roles, keep the controller's
    // reference-resolution role singular so the family layouts cannot drift.
    const visible = [{ ...specs[0], role: "image", label: "参考图" }];
    visible.forEach((spec, index) => {
      const field = existing[index] || document.createElement("label");
      field.className = "field v04-control v04-resolution";
      field.dataset.h3AdvancedRole = "reference-resolution";
      field.dataset.h3Owned = "true";
      let label = field.querySelector(":scope > span");
      if (!label) {
        label = document.createElement("span");
        field.prepend(label);
      }
      label.textContent = `${spec.label}分辨率`;
      let select = field.querySelector("select");
      if (!select) {
        select = document.createElement("select");
        field.append(select);
      }
      select.dataset.v04Resolution = spec.role;
      const values = spec.allowAuto ? RESOLUTION_VALUES : ["original"];
      setOptions(select, values, values.map(value => value === "original" ? "保持原图" : `${value} MP`), requestedResolution(spec, { media_resolution: state.referenceResolution }, state.referenceResolution));
      if (!field.parentElement) grid.append(field);
    });
    existing.slice(visible.length).forEach(field => field.remove());
  }

  function readLiveState(family, grid) {
    const state = familyStates.get(family) || {};
    const read = role => grid.querySelector(`[data-h3-advanced-role="${role}"] select, [data-h3-advanced-role="${role}"] input`)?.value;
    return {
      ...state,
      generationMode: read("generation-mode") || state.generationMode,
      promptBackend: read("prompt-backend") || state.promptBackend,
      mainModel: read("main-model") || state.mainModel,
      ollamaModel: read("ollama-model") || state.ollamaModel,
      scheduler: grid.querySelector('select[name="scheduler"]')?.value || state.scheduler,
      sampler: grid.querySelector('select[name="sampler"]')?.value || state.sampler,
      steps: grid.querySelector('input[name="steps"]')?.value || state.steps,
      seedPolicy: read("seed-policy") || state.seedPolicy,
      seedValue: grid.querySelector('input[name="seed"]')?.value || state.seedValue,
      referenceResolution: state.referenceResolution,
      referenceResolutionTransport: state.referenceResolutionTransport,
      referenceResolutionDirty: state.referenceResolutionDirty,
    };
  }

  function resolve(adapter, preset, overrides, grid) {
    const previous = activeState?.family === adapter.family
      ? readLiveState(adapter.family, grid)
      : (familyStates.get(adapter.family) || {});
    const explicitMode = candidate(overrides, "generation_mode");
    const explicitBackendValue = candidate(overrides, "prompt_backend", "prompt_standardization_mode");
    const legacyStandardization = candidate(overrides, "prompt_standardization");
    const explicitBackend = explicitBackendValue ?? (legacyStandardization === false ? "raw" : legacyStandardization === true ? "ollama" : undefined);
    const explicitModel = candidate(overrides, "inference_profile", "main_model");
    const explicitSeed = candidate(overrides, "seed_policy");
    const mode = adapter.normalizeMode(explicitMode ?? previous.generationMode ?? remembered(adapter.storage?.mode) ?? adapter.defaults.mode);
    const backend = adapter.normalizeBackend(explicitBackend ?? previous.promptBackend ?? remembered(adapter.storage?.backend) ?? adapter.defaults.backend);
    const mainModel = adapter.normalizeMainModel(explicitModel ?? previous.mainModel ?? remembered(adapter.storage?.mainModel) ?? adapter.defaults.mainModel);
    const ollamaModel = stringValue(candidate(overrides, "ollama_model") ?? previous.ollamaModel ?? remembered(adapter.storage?.ollamaModel) ?? adapter.defaults.ollamaModel).trim() || adapter.defaults.ollamaModel;
    const tuning = adapter.modeTuning(mode) || {};
    const hasExplicitTuning = ["scheduler", "sampler", "steps"].some(key => candidate(overrides, key) !== undefined);
    const modeChanged = explicitMode !== undefined && mode !== previous.generationMode;
    const tuningDefaults = modeChanged && !hasExplicitTuning ? tuning : {};
    const seedPolicy = valid(explicitSeed, SEED_POLICIES)
      ? String(explicitSeed)
      : valid(previous.seedPolicy, SEED_POLICIES)
        ? previous.seedPolicy
        : valid(remembered(adapter.storage?.seedPolicy), SEED_POLICIES)
          ? remembered(adapter.storage?.seedPolicy)
          : adapter.defaults.seedPolicy;
    const seedValue = seedPolicy === "randomize"
      ? ""
      : stringValue(candidate(overrides, "seed_value", "seed") ?? previous.seedValue ?? "");
    const explicitResolution = candidate(overrides, "media_resolution");
    let referenceResolution = previous.referenceResolution ?? adapter.defaults.referenceResolution;
    let referenceResolutionTransport = previous.referenceResolutionTransport || null;
    let referenceResolutionDirty = previous.referenceResolutionDirty === true;
    if (explicitResolution !== undefined) {
      const mapped = adapter.referenceResolutionFromTransport?.(
        explicitResolution,
        referenceResolution,
      ) || { ui: normalizeReferenceResolution(explicitResolution, referenceResolution), transport: null };
      referenceResolution = mapped.ui;
      referenceResolutionTransport = mapped.transport || null;
      referenceResolutionDirty = overrides.reference_resolution_dirty === true;
    }
    return {
      family: adapter.family,
      generationMode: mode,
      promptBackend: backend,
      mainModel,
      ollamaModel,
      scheduler: stringValue(candidate(overrides, "scheduler") ?? tuningDefaults.scheduler ?? previous.scheduler ?? tuning.scheduler ?? adapter.defaults.scheduler),
      sampler: stringValue(candidate(overrides, "sampler") ?? tuningDefaults.sampler ?? previous.sampler ?? tuning.sampler ?? adapter.defaults.sampler),
      steps: stringValue(candidate(overrides, "steps") ?? tuningDefaults.steps ?? previous.steps ?? tuning.steps ?? adapter.defaults.steps),
      seedPolicy,
      seedValue,
      referenceResolution,
      referenceResolutionTransport,
      referenceResolutionDirty,
    };
  }

  function applyState(adapter, preset, state, overrides) {
    const details = document.querySelector("#advanced-settings");
    const grid = details?.querySelector(".advanced-grid");
    if (!details || !grid) return;
    removeLegacyFields(grid);
    const mode = ensureField(grid, "generation-mode", "h3GenerationMode", "生成模式", adapter.modeValues, adapter.modeLabels, state.generationMode);
    const backend = ensureField(grid, "prompt-backend", "h3PromptBackend", "标准化提示词", BACKENDS, ["原始提示词", "Ollama 标准化", "Qwen3.5 标准化"], state.promptBackend);
    const model = ensureField(grid, "main-model", "h3MainModel", "主模型", adapter.modelValues, adapter.modelLabels, state.mainModel);
    ensureOllamaField(grid, state.ollamaModel, state);
    const scheduler = grid.querySelector('select[name="scheduler"]');
    const sampler = grid.querySelector('select[name="sampler"]');
    const steps = grid.querySelector('input[name="steps"]');
    const schedulerValues = Object.keys(preset?.parameters?.scheduler?.values || {});
    const samplerValues = Object.keys(preset?.parameters?.sampler?.values || {});
    if (scheduler) { scheduler.dataset.h3AdvancedRole = "scheduler"; scheduler.closest("label.field")?.setAttribute("data-h3-base-field", "true"); scheduler.closest("label.field")?.setAttribute("data-h3-advanced-role", "scheduler"); if (schedulerValues.length) setOptions(scheduler, schedulerValues, schedulerValues, state.scheduler); else scheduler.value = state.scheduler; }
    if (sampler) { sampler.dataset.h3AdvancedRole = "sampler"; sampler.closest("label.field")?.setAttribute("data-h3-base-field", "true"); sampler.closest("label.field")?.setAttribute("data-h3-advanced-role", "sampler"); if (samplerValues.length) setOptions(sampler, samplerValues, samplerValues, state.sampler); else sampler.value = state.sampler; }
    if (steps) { steps.dataset.h3AdvancedRole = "steps"; steps.closest("label.field")?.setAttribute("data-h3-base-field", "true"); steps.closest("label.field")?.setAttribute("data-h3-advanced-role", "steps"); steps.value = state.steps; }
    ensureSeedPolicy(grid, state);
    ensureResolution(grid, preset, state);
    mode.select.dataset.h3AdvancedRole = "generation-mode";
    backend.select.dataset.h3AdvancedRole = "prompt-backend";
    model.select.dataset.h3AdvancedRole = "main-model";
    normalize(grid);
    familyStates.set(adapter.family, { ...state });
    activeState = { ...state };
    const availability = adapter.getModelAvailability?.(state) || {};
    const modelSelect = model.select;
    for (const item of modelSelect.options || []) {
      const available = availability[item.value];
      item.disabled = available === false;
      if (item.disabled) item.title = "当前内置资产不可用";
      else item.removeAttribute("title");
    }
    if (modelSelect.options?.some(item => item.value === state.mainModel && !item.disabled)) {
      modelSelect.value = state.mainModel;
    } else {
      modelSelect.value = adapter.defaults.mainModel;
      activeState.mainModel = adapter.defaults.mainModel;
      familyStates.set(adapter.family, { ...activeState });
    }
    adapter.onRender?.(state);
  }

  function restoreBaseFields(grid) {
    for (const role of ["scheduler", "sampler", "steps", "seed-value"]) {
      const field = grid.querySelector(`[data-h3-advanced-role="${role}"]`);
      if (!field) continue;
      field.hidden = false;
      field.classList.remove("hidden");
      delete field.dataset.h3AdvancedRole;
      delete field.dataset.h3BaseField;
      delete field.dataset.h3SeedValue;
      field.querySelector("select, input")?.removeAttribute("data-h3-advanced-role");
    }
  }

  function unmount() {
    const grid = document.querySelector("#advanced-settings .advanced-grid");
    if (grid) {
      grid.querySelectorAll('[data-h3-owned="true"]').forEach(field => field.remove());
      restoreBaseFields(grid);
      normalize(grid);
    }
    activeState = null;
  }

  function mount(adapter, preset, overrides = {}) {
    if (!adapter || !preset) return;
    sync(preset, overrides);
  }

  function sync(preset, overrides = {}) {
    const family = preset?.family;
    const adapter = adapters.get(family);
    if (!adapter) return;
    const grid = document.querySelector("#advanced-settings .advanced-grid");
    if (!grid) return;
    const state = resolve(adapter, preset, overrides, grid);
    applyState(adapter, preset, state, overrides);
    window.ComfyRemoteH3AdvancedSettings?.onStateRendered?.(state);
  }

  function syncH3CreationUI(preset, overrides = {}) {
    sync(preset, overrides);
  }

  function publicState(state) {
    if (!state) return null;
    return {
      family: state.family,
      generationMode: state.generationMode,
      promptBackend: state.promptBackend,
      mainModel: state.mainModel,
      ollamaModel: state.ollamaModel,
      scheduler: state.scheduler,
      sampler: state.sampler,
      steps: state.steps,
      seedPolicy: state.seedPolicy,
      seedValue: state.seedValue,
      referenceResolution: clone(state.referenceResolution),
    };
  }

  function getState() {
    return publicState(activeState);
  }

  function getSubmissionState() {
    if (!activeState) return null;
    return {
      ...publicState(activeState),
      referenceResolutionTransport: clone(activeState.referenceResolutionTransport),
      referenceResolutionDirty: activeState.referenceResolutionDirty === true,
    };
  }

  function handleChange(event) {
    const target = event.target;
    const field = target?.closest?.("[data-h3-advanced-role]");
    const preset = selectedPreset?.();
    const adapter = adapters.get(preset?.family);
    if (!field || !adapter || !activeState || activeState.family !== adapter.family) return;
    const role = field.dataset.h3AdvancedRole;
    const value = target.value;
    const next = { ...activeState };
    if (role === "generation-mode") {
      next.generationMode = adapter.normalizeMode(value);
      const tuning = adapter.modeTuning(next.generationMode) || {};
      next.scheduler = tuning.scheduler ?? next.scheduler;
      next.sampler = tuning.sampler ?? next.sampler;
      next.steps = String(tuning.steps ?? next.steps);
    } else if (role === "prompt-backend") next.promptBackend = adapter.normalizeBackend(value);
    else if (role === "main-model") next.mainModel = adapter.normalizeMainModel(value);
    else if (role === "ollama-model") next.ollamaModel = String(value || "").trim() || next.ollamaModel;
    else if (role === "scheduler") next.scheduler = value;
    else if (role === "sampler") next.sampler = value;
    else if (role === "steps") next.steps = value;
    else if (role === "seed-policy") {
      next.seedPolicy = valid(value, SEED_POLICIES) ? value : "randomize";
      if (next.seedPolicy === "randomize") next.seedValue = "";
    } else if (role === "seed-value") next.seedValue = value;
    else if (role === "reference-resolution") {
      next.referenceResolution = { [target.dataset.v04Resolution]: target.value === "original" ? { policy: "original", target_megapixels: null } : { policy: "auto", target_megapixels: Number(target.value) } };
      next.referenceResolutionTransport = null;
      next.referenceResolutionDirty = true;
    }
    familyStates.set(adapter.family, next);
    activeState = next;
    remember(adapter.storage?.mode, next.generationMode);
    remember(adapter.storage?.backend, next.promptBackend);
    remember(adapter.storage?.mainModel, next.mainModel);
    remember(adapter.storage?.ollamaModel, next.ollamaModel);
    remember(adapter.storage?.seedPolicy, next.seedPolicy);
    if (role === "prompt-backend" || role === "generation-mode" || role === "seed-policy") {
      sync(preset, {
        generation_mode: next.generationMode,
        prompt_backend: next.promptBackend,
        inference_profile: next.mainModel,
        ollama_model: next.ollamaModel,
        scheduler: next.scheduler,
        sampler: next.sampler,
        steps: next.steps,
        seed_policy: next.seedPolicy,
        seed_value: next.seedValue,
      });
    }
    if (role === "reference-resolution") {
      sync(preset, {
        generation_mode: next.generationMode,
        prompt_backend: next.promptBackend,
        inference_profile: next.mainModel,
        ollama_model: next.ollamaModel,
        scheduler: next.scheduler,
        sampler: next.sampler,
        steps: next.steps,
        seed_policy: next.seedPolicy,
        seed_value: next.seedValue,
        media_resolution: next.referenceResolution,
        reference_resolution_dirty: true,
      });
    }
    adapter.onChange?.(next, role);
  }

  function register(adapter) {
    if (!adapter?.family) return;
    adapters.set(adapter.family, adapter);
  }

  function bind() {
    if (bound) return;
    bound = true;
    document.querySelector("#job-form")?.addEventListener("change", handleChange, true);
    document.querySelector("#job-form")?.addEventListener("input", event => {
      const field = event.target?.closest?.('[data-h3-advanced-role="steps"], [data-h3-advanced-role="seed-value"]');
      if (field) handleChange(event);
    }, true);
  }

  window.ComfyRemoteH3AdvancedSettings = {
    registerAdapter: register,
    sync,
    syncH3CreationUI,
    render: sync,
    normalize,
    getState,
    getSubmissionState,
    bind,
    mount,
    unmount,
    getAdapters: () => new Map(adapters),
  };
  window.syncH3CreationUI = syncH3CreationUI;

  document.addEventListener("DOMContentLoaded", bind);
})();
