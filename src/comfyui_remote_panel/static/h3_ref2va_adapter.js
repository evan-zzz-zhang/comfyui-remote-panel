(() => {
  const ENTRY_ID = "h3-ref2va-group";
  const DEFAULT_MODE = "v4step600";
  const DEFAULT_BACKEND = "raw";
  const DEFAULT_PROFILE = "int8";
  const DEFAULT_OLLAMA_MODEL = "gemma4:e4b";
  const PHYSICAL_IDS = new Set([
    "h3-ref2va", "h3-ref2va-lightx2v", "h3-ref2va-v4step600",
    "ref2va_original_raw", "ref2va_original_ollama", "ref2va_original_qwen35",
    "ref2va_lightx2v_raw", "ref2va_lightx2v_ollama", "ref2va_lightx2v_qwen35",
    "ref2va_v4step600_raw", "ref2va_v4step600_ollama", "ref2va_v4step600_qwen35",
  ]);
  const MODE_TUNING = {
    original: { scheduler: "simple", sampler: "res_multistep", steps: 20 },
    lightx2v: { scheduler: "simple", sampler: "euler", steps: 4 },
    v4step600: { scheduler: "beta", sampler: "euler", steps: 8 },
  };
  const STORAGE = {
    mode: "comfy-remote.ref2va.generation-mode",
    backend: "comfy-remote.ref2va.prompt-backend",
    mainModel: "comfy-remote.ref2va.inference-profile",
    ollamaModel: "comfy-remote.ref2va.ollama-model",
    seedPolicy: "comfy-remote.ref2va.seed-policy",
  };
  function normalizeMode(value) { return String(value || "").toLowerCase() === "v4_600step" ? "v4step600" : String(value || "").toLowerCase(); }
  function normalizeBackend(value) { return ({ off: "raw", comfyui: "qwen35" }[String(value || "").toLowerCase()] || String(value || "").toLowerCase()); }
  function normalizeMainModel(value) { return String(value || "").toLowerCase() === "auto" ? DEFAULT_PROFILE : String(value || "").toLowerCase(); }
  function clone(value) {
    if (!value || typeof value !== "object") return value;
    return JSON.parse(JSON.stringify(value));
  }
  function referenceResolutionFromTransport(value, fallback) {
    const parsed = typeof value === "string" ? (() => { try { return JSON.parse(value); } catch (_) { return null; } })() : value;
    return { ui: parsed && typeof parsed === "object" ? clone(parsed) : fallback, transport: null };
  }
  function referenceResolutionToTransport(ui) { return ui ? clone(ui) : null; }
  function targetId(mode, backend) { return `ref2va_${normalizeMode(mode)}_${normalizeBackend(backend)}`; }
  function group() { return state.presets?.get?.(ENTRY_ID); }
  function refresh() { return group(); }
  function mapPreset(presetId, overrides = {}) {
    if (presetId === ENTRY_ID) return { presetId: ENTRY_ID, overrides };
    if (!PHYSICAL_IDS.has(presetId)) return null;
    const mode = presetId.includes("lightx2v") ? "lightx2v" : presetId.includes("v4step600") ? "v4step600" : "original";
    return { presetId: ENTRY_ID, overrides: { ...overrides, generation_mode: normalizeMode(overrides.generation_mode || mode) } };
  }
  function valuesFromFormData(formData) {
    const values = {};
    for (const raw of formData.getAll("values_json")) {
      try { const parsed = JSON.parse(raw); if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) Object.assign(values, parsed); } catch (_) {}
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
      // A Retry draft contains the previous resolved seed in the base form.
      // Randomize must omit it so the server generates a fresh seed.
      formData.delete("seed");
    }
    if (ui.referenceResolution) values.media_resolution = ui.referenceResolution;
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
    family: "ref2va", entryId: ENTRY_ID, name: "MiniMax H3 Ref2VA",
    modeValues: ["original", "lightx2v", "v4step600"], modeLabels: ["原版", "LightX2V", "v4_600step"],
    modelValues: ["int8", "fp16_bf16"], modelLabels: ["pruned_int8", "pruned_bf16"],
    normalizeMode, normalizeBackend, normalizeMainModel, modeTuning: mode => MODE_TUNING[normalizeMode(mode)],
    defaults: { mode: DEFAULT_MODE, backend: DEFAULT_BACKEND, mainModel: DEFAULT_PROFILE, ollamaModel: DEFAULT_OLLAMA_MODEL, scheduler: "beta", sampler: "euler", steps: "8", seedPolicy: "randomize", referenceResolution: null },
    referenceResolutionFromTransport, referenceResolutionToTransport,
    storage: STORAGE, physicalPresetIds: PHYSICAL_IDS, refresh, mapPreset, augmentFormData, getModelAvailability, getSubmitAvailability,
    isEntry: preset => preset?.id === ENTRY_ID || preset?.family === "ref2va",
  };
  window.H3CreationRuntime?.registerAdapter?.(adapter);
  window.ComfyRemoteH3AdvancedSettings?.registerAdapter?.(adapter);
})();
