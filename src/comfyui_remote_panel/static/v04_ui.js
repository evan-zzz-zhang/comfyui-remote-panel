(() => {
  const SEED_POLICIES = ["randomize", "fixed", "increment"];
  let syncTimer = null;

  function seedEntry(preset) {
    return Object.entries(preset?.parameters || {}).find(([id, spec]) =>
      id === "seed"
      || spec?.ui?.semantic === "seed"
      || /(?:^|_)seed$/i.test(id)
    ) || null;
  }

  function ensureSeedMetadata(preset) {
    const entry = seedEntry(preset);
    if (!entry) return;
    const [, spec] = entry;
    spec.ui = { ...(spec.ui || {}), semantic: "seed", label: spec.ui?.label || "Seed" };
    preset.seed_policy = {
      supported: true,
      default: preset.seed_policy?.default || preset.default_seed_policy || "randomize",
      values: preset.seed_policy?.values || SEED_POLICIES,
    };
  }

  function seedBindingFromInspection() {
    return (state.workflowInspection?.parameters || []).find(item =>
      item?.semantic === "seed"
      || item?.id === "seed"
      || /(?:^|_)seed$/i.test(item?.input || "")
    ) || null;
  }

  // Seed is an advanced parameter, but Configurator 2.0 can still detect it.
  // Persist that binding automatically so imported workflows get the same
  // Random / Fixed / Increment policy controls as built-in workflows.
  const baseApiActionV04 = apiAction;
  apiAction = function(path, options = {}) {
    if (path === "/api/workflows" && String(options.method || "GET").toUpperCase() === "POST" && typeof options.body === "string") {
      try {
        const payload = JSON.parse(options.body);
        const parameters = payload?.config?.parameters;
        const seed = seedBindingFromInspection();
        const alreadySaved = Array.isArray(parameters) && parameters.some(item =>
          item?.id === "seed"
          || item?.ui?.semantic === "seed"
          || /(?:^|_)seed$/i.test(item?.input || "")
        );
        if (seed && Array.isArray(parameters) && !alreadySaved) {
          parameters.push({
            id: "seed",
            node: seed.node,
            input: seed.input,
            type: seed.type || "integer",
            default: seed.default ?? 0,
            ...(seed.minimum != null ? { minimum: seed.minimum } : {}),
            ...(seed.maximum != null ? { maximum: seed.maximum } : {}),
            ...(seed.step != null ? { step: seed.step } : {}),
            ui: {
              label: seed.label || "Seed",
              control: seed.control || "number",
              semantic: "seed",
            },
          });
          payload.config.default_seed_policy = document.querySelector("#v04-config-seed-policy")?.value
            || payload.config.default_seed_policy
            || "randomize";
          options = { ...options, body: JSON.stringify(payload) };
        }
      } catch (_) {}
    }
    return baseApiActionV04(path, options);
  };

  function installV04Styles() {
    if (document.querySelector("#v04-creation-style")) return;
    const style = document.createElement("style");
    style.id = "v04-creation-style";
    style.textContent = `
      #advanced-settings.v04-advanced-layout {
        overflow: visible;
        background: transparent;
        border: 0;
        border-radius: 0;
      }
      #advanced-settings.v04-advanced-layout > summary {
        min-height: 0;
        padding: 0;
        color: var(--text-primary);
        font-size: 15px;
        font-weight: 650;
      }
      #advanced-settings.v04-advanced-layout[open] > summary { margin-bottom: 10px; }
      #advanced-settings.v04-advanced-layout > .advanced-grid {
        padding: 12px;
        background: var(--surface-1);
        border: 1px solid var(--border);
        border-radius: var(--radius);
      }
      #advanced-settings.v04-advanced-layout > p { display: none; }
      #advanced-settings .v04-hidden-for-generic { display: none !important; }
      .generic-advanced.v04-source-hidden { display: none !important; }
    `;
    document.head.append(style);
  }

  function cleanSettingsChips() {
    document.querySelectorAll("#settings-chips .settings-chip").forEach(chip => {
      if (/工作流决定|跟随源图|跟随输入图/.test(chip.textContent.trim())) chip.remove();
    });
  }

  function cleanResolutionCopy(root = document) {
    root.querySelectorAll(".v04-resolution small, .v04-media-resolution .field small, .v04-media-resolution > p").forEach(node => node.remove());
  }

  function syncGenerationSettingsVisibility() {
    const preset = selectedPreset();
    const section = document.querySelector("#basic-settings");
    if (!preset || !section || preset.family !== "generic") return;
    const hasEditableSetting = ["width", "height", "batch_size"].some(id =>
      Boolean(preset.parameters?.[id] && document.querySelector(`#job-form [data-generic-binding="${CSS.escape(id)}"]`))
    );
    section.classList.toggle("hidden", !hasEditableSetting);
  }

  function baseAdvancedFields() {
    return [
      document.querySelector('#advanced-settings select[name="scheduler"]')?.closest("label.field"),
      document.querySelector('#advanced-settings select[name="sampler"]')?.closest("label.field"),
      document.querySelector('#advanced-settings input[name="steps"]')?.closest("label.field"),
      document.querySelector('#advanced-settings input[name="seed"]')?.closest("label.field"),
    ].filter(Boolean);
  }

  function clearPreviousGenericAdvanced() {
    document.querySelectorAll("#advanced-settings .v04-generic-advanced-field").forEach(node => node.remove());
    document.querySelectorAll("#job-form .generic-advanced.v04-source-hidden").forEach(node => node.remove());
  }

  function moveGenericAdvancedIntoUnifiedSection(preset) {
    const advanced = document.querySelector("#advanced-settings");
    const grid = advanced?.querySelector(":scope > .advanced-grid");
    if (!advanced || !grid) return;

    const generic = preset?.family === "generic";
    for (const field of baseAdvancedFields()) {
      field.classList.toggle("v04-hidden-for-generic", generic);
    }
    if (!generic) {
      advanced.classList.remove("hidden");
      return;
    }

    const policyField = document.querySelector("#job-form [data-v04-seed-policy]")?.closest("label.field") || null;
    const seed = seedEntry(preset);
    const seedInput = seed
      ? document.querySelector(`#job-form [data-generic-binding="${CSS.escape(seed[0])}"]`)
      : null;
    const seedField = seedInput?.closest("label.field") || null;
    const resolutionFields = [...document.querySelectorAll("#job-form [data-v04-resolution]")]
      .map(node => node.closest("label.field"))
      .filter(Boolean);
    const sourceAdvancedFields = [...document.querySelectorAll("#job-form .generic-advanced .field")]
      .filter(field => !grid.contains(field));

    const special = new Set([policyField, seedField, ...resolutionFields].filter(Boolean));
    const regular = sourceAdvancedFields.filter(field => !special.has(field));
    const ordered = [...regular, policyField, seedField, ...resolutionFields].filter(Boolean);
    const unique = [...new Set(ordered)];

    for (const field of unique) {
      if (resolutionFields.includes(field)) field.querySelectorAll("small").forEach(node => node.remove());
      field.classList.add("v04-generic-advanced-field");
      grid.append(field);
    }

    document.querySelectorAll("#job-form .generic-advanced").forEach(details => {
      if (details !== advanced) details.classList.add("hidden", "v04-source-hidden");
    });

    advanced.classList.toggle("hidden", unique.length === 0);
  }

  function syncAdvancedHierarchy() {
    const preset = selectedPreset();
    const advanced = document.querySelector("#advanced-settings");
    if (!preset || !advanced) return;
    advanced.classList.add("v04-advanced-layout");
    const title = advanced.querySelector(":scope > summary > span");
    if (title) title.textContent = "高级设置";
    moveGenericAdvancedIntoUnifiedSection(preset);
  }

  function syncCreationUx() {
    installV04Styles();
    cleanResolutionCopy();
    cleanSettingsChips();
    syncGenerationSettingsVisibility();
    syncAdvancedHierarchy();
  }

  function scheduleCreationUx() {
    if (syncTimer != null) window.clearTimeout(syncTimer);
    syncTimer = window.setTimeout(() => {
      syncTimer = null;
      syncCreationUx();
    }, 0);
  }

  const baseApplyPresetV04 = applyPreset;
  applyPreset = function(presetId, overrides = {}) {
    clearPreviousGenericAdvanced();
    const result = baseApplyPresetV04(presetId, overrides);
    // The lower wrappers create the preset and queue v0.4 controls before this
    // task finishes. Mutating the shared preset object here makes that queued
    // control installation see the Seed capability as well.
    ensureSeedMetadata(state.presets.get(presetId) || selectedPreset());
    scheduleCreationUx();
    return result;
  };

  document.addEventListener("DOMContentLoaded", () => {
    installV04Styles();
    scheduleCreationUx();

    document.querySelector("#job-form")?.addEventListener("input", () => queueMicrotask(cleanSettingsChips));
    document.querySelector("#job-form")?.addEventListener("change", scheduleCreationUx);

    // No custom keyboard button. Tapping outside the prompt simply returns
    // focus to the page, matching normal mobile form behaviour.
    document.addEventListener("pointerdown", event => {
      const active = document.activeElement;
      if (active?.tagName === "TEXTAREA" && event.target !== active) active.blur();
    }, true);
  });

  if (typeof renderMetrics === "function") {
    const baseRenderMetrics = renderMetrics;
    renderMetrics = function(metrics) {
      baseRenderMetrics(metrics);
      if (!metrics) return;

      const panel = metrics.panel || { online: true, state: "online" };
      const comfy = metrics.comfyui || {};
      const pill = document.querySelector("#connection-pill");
      if (pill) {
        pill.className = `status-pill ${panel.online ? "status-online" : "status-offline"}`;
        pill.innerHTML = `<span></span>${panel.online ? "面板在线" : "面板离线"}`;
      }

      const stateLabels = {
        online: "在线",
        starting: "正在启动",
        offline: "离线",
        unknown: "未知",
      };
      const comfyState = comfy.state || (comfy.online ? "online" : "unknown");
      const comfyLabel = stateLabels[comfyState] || comfyState;
      const overview = document.querySelector("#device-overview");
      if (overview) {
        overview.innerHTML = `<div class="device-chip ${panel.online ? "online" : ""}"><small>PANEL</small><strong>${panel.online ? "在线" : "离线"}</strong></div><div class="device-chip ${comfyState === "online" ? "online" : ""}"><small>COMFYUI</small><strong>${escapeHtml(comfyLabel)}${comfyState === "online" && comfy.version ? ` · ${escapeHtml(comfy.version)}` : ""}</strong></div><div class="device-chip"><small>队列任务</small><strong>${comfy.queue_count ?? "—"}</strong></div>`;
      }
    };
  }
})();
