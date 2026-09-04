(() => {
  const ENTRY_ID = "h3-fl2va-group";
  const ORIGINAL_ID = "h3-fl2va";
  const DEFAULT_MODE = "v4_600step";
  const DEFAULT_BACKEND = "ollama";
  const DEFAULT_PROFILE = "int8";
  const DEFAULT_OLLAMA_MODEL = "gemma4:e4b";
  const PHYSICAL_IDS = new Set([
    "h3-fl2va", "h3-fl2va-lightx2v", "h3-fl2va-v4step600",
    "h3-fl2va-qwen35-4b", "h3-fl2va-lightx2v-qwen35-4b", "h3-fl2va-v4step600-qwen35-4b",
    "fl2va_original_raw", "fl2va_original_ollama", "fl2va_original_qwen35",
    "fl2va_lightx2v_raw", "fl2va_lightx2v_ollama", "fl2va_lightx2v_qwen35",
    "fl2va_v4step600_raw", "fl2va_v4step600_ollama", "fl2va_v4step600_qwen35",
  ]);
  const MODE_TUNING = {
    original: { scheduler: "simple", sampler: "res_multistep", steps: 20 },
    lightx2v: { scheduler: "simple", sampler: "euler", steps: 8 },
    v4_600step: { scheduler: "beta", sampler: "euler", steps: 8 },
  };
  const STORAGE = {
    mode: "comfy-remote.fl2va.generation-mode",
    backend: "comfy-remote.fl2va.prompt-standardization-mode",
    mainModel: "comfy-remote.fl2va.inference-profile",
    ollamaModel: "comfy-remote.fl2va.ollama-model",
    seedPolicy: "comfy-remote.fl2va.seed-policy",
  };

  function normalizeMode(value) {
    return String(value || "").toLowerCase() === "v4step600" ? "v4_600step" : String(value || "").toLowerCase();
  }
  function normalizeBackend(value) {
    return ({ off: "raw", comfyui: "qwen35" }[String(value || "").toLowerCase()]
      || String(value || "").toLowerCase());
  }
  function normalizeMainModel(value) {
    return String(value || "").toLowerCase() === "auto" ? DEFAULT_PROFILE : String(value || "").toLowerCase();
  }
  function clone(value) {
    if (!value || typeof value !== "object") return value;
    return JSON.parse(JSON.stringify(value));
  }
  function referenceResolutionFromTransport(value, fallback) {
    const parsed = typeof value === "string" ? (() => { try { return JSON.parse(value); } catch (_) { return null; } })() : value;
    if (parsed?.first || parsed?.last) {
      const display = clone(parsed.first || parsed.last);
      return { ui: display ? { image: display } : fallback, transport: clone(parsed) };
    }
    return { ui: parsed && typeof parsed === "object" ? clone(parsed) : fallback, transport: null };
  }
  function referenceResolutionToTransport(ui, state) {
    if (!ui) return null;
    if (!state?.referenceResolutionDirty && state?.referenceResolutionTransport
      && (state.referenceResolutionTransport.first || state.referenceResolutionTransport.last)) {
      return clone(state.referenceResolutionTransport);
    }
    const value = ui.image || ui.first || ui.last;
    return value ? { first: clone(value), last: clone(value) } : null;
  }
  function modeKey(mode) { return normalizeMode(mode) === "v4_600step" ? "v4step600" : normalizeMode(mode); }
  function targetId(mode, backend) { return `fl2va_${modeKey(mode)}_${normalizeBackend(backend)}`; }
  function merged(overrides) { return { ...(overrides || {}), ...(overrides?.values || {}) }; }
  function group() { return state.presets?.get?.(ENTRY_ID); }
  function sourcePreset(mode = DEFAULT_MODE, backend = DEFAULT_BACKEND) {
    return state.presets?.get?.(targetId(mode, backend))
      || state.presets?.get?.(ORIGINAL_ID)
      || [...(state.presets?.values?.() || [])].find(item => item?.family === "fl2va");
  }
  function publicParameters(manifest, fallback) {
    const parameters = manifest?.parameters || fallback?.parameters || {};
    return Object.fromEntries(Object.entries(parameters).map(([name, spec]) => [name, { ...spec }]));
  }
  function buildGroupPreset() {
    const source = sourcePreset();
    if (!source) return null;
    const manifest = state.workflowItems?.get?.(ORIGINAL_ID)?.manifest;
    const baseModes = {
      original: { label: "原版", preset_id: targetId("original", "raw") },
      lightx2v: { label: "LightX2V", preset_id: targetId("lightx2v", "raw") },
      v4_600step: { label: "v4_600step", preset_id: targetId("v4_600step", "raw") },
    };
    return {
      ...source,
      id: ENTRY_ID,
      name: "MiniMax H3 FL2VA",
      family: "fl2va",
      description: "首尾帧视频生成 · 原版 / LightX2V / v4_600step",
      parameters: publicParameters(manifest, source),
      generation_modes: manifest?.generation_modes || source.generation_modes || { default: DEFAULT_MODE, values: baseModes },
      available: true,
    };
  }
  function refresh() {
    const next = buildGroupPreset();
    if (next) state.presets.set(ENTRY_ID, next);
    return next;
  }
  function mapPreset(presetId, overrides = {}) {
    if (presetId === ENTRY_ID) return { presetId: ENTRY_ID, overrides };
    if (!PHYSICAL_IDS.has(presetId)) return null;
    const mode = presetId.includes("lightx2v") ? "lightx2v" : presetId.includes("v4step600") ? "v4_600step" : "original";
    return { presetId: ENTRY_ID, overrides: { ...overrides, generation_mode: normalizeMode(overrides.generation_mode || mode) } };
  }
  function valuesFromFormData(formData) {
    const values = {};
    for (const raw of formData.getAll("values_json")) {
      try {
        const parsed = JSON.parse(raw);
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) Object.assign(values, parsed);
      } catch (_) {}
    }
    return values;
  }
  function augmentFormData(formData, ui = {}) {
    if (String(formData.get("preset_id") || "") !== ENTRY_ID) return formData;
    const values = valuesFromFormData(formData);
    const backend = normalizeBackend(ui.promptBackend || DEFAULT_BACKEND);
    const seedPolicy = ui.seedPolicy || "randomize";
    Object.assign(values, {
      generation_mode: normalizeMode(ui.generationMode || DEFAULT_MODE),
      prompt_backend: backend,
      prompt_standardization_mode: backend === "raw" ? "off" : backend === "qwen35" ? "comfyui" : "ollama",
      prompt_standardization: backend !== "raw",
      inference_profile: normalizeMainModel(ui.mainModel || DEFAULT_PROFILE),
      scheduler: ui.scheduler,
      sampler: ui.sampler,
      steps: ui.steps,
      seed_policy: seedPolicy,
    });
    if (seedPolicy !== "randomize") values.seed_value = ui.seedValue ?? "";
    else {
      delete values.seed_value;
      // Retry drafts expose the previous task's resolved seed through the base
      // form. Randomize must not accidentally resubmit that hidden old seed.
      formData.delete("seed");
    }
    if (ui.referenceResolution) values.media_resolution = referenceResolutionToTransport(ui.referenceResolution, ui);
    if (backend === "ollama") values.ollama_model = String(ui.ollamaModel || DEFAULT_OLLAMA_MODEL).trim() || DEFAULT_OLLAMA_MODEL;
    else delete values.ollama_model;
    formData.delete("values_json");
    formData.set("values_json", JSON.stringify(values));
    return formData;
  }
  function getModelAvailability(ui = {}) {
    const target = state.workflowItems?.get?.(targetId(ui.generationMode, ui.promptBackend));
    const variant = target?.manifest?.model_profile?.main_model?.variants?.fp16_bf16;
    return { fp16_bf16: variant?.available !== false };
  }
  function getSubmitAvailability(ui = {}) {
    const id = targetId(ui.generationMode, ui.promptBackend);
    const item = state.workflowItems?.get?.(id);
    return Boolean(item?.status === "enabled" && state.metrics?.presets?.[id]?.available === true);
  }

  const adapter = {
    family: "fl2va", entryId: ENTRY_ID, name: "MiniMax H3 FL2VA",
    modeValues: ["original", "lightx2v", "v4_600step"],
    modeLabels: ["原版", "LightX2V", "v4_600step"],
    modelValues: ["int8", "fp16_bf16"], modelLabels: ["pruned_int8", "pruned_bf16"],
    normalizeMode, normalizeBackend, normalizeMainModel, modeTuning: mode => MODE_TUNING[normalizeMode(mode)],
    defaults: { mode: DEFAULT_MODE, backend: DEFAULT_BACKEND, mainModel: DEFAULT_PROFILE, ollamaModel: DEFAULT_OLLAMA_MODEL, scheduler: "beta", sampler: "euler", steps: "8", seedPolicy: "randomize", referenceResolution: null },
    referenceResolutionFromTransport, referenceResolutionToTransport,
    storage: STORAGE, physicalPresetIds: PHYSICAL_IDS, refresh, mapPreset, augmentFormData, getModelAvailability, getSubmitAvailability,
    isEntry: preset => preset?.id === ENTRY_ID || preset?.family === "fl2va",
  };
  window.H3CreationRuntime?.registerAdapter?.(adapter);
  window.ComfyRemoteH3AdvancedSettings?.registerAdapter?.(adapter);
})();
