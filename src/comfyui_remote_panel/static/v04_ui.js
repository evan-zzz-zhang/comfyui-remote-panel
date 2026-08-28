(() => {
  const SEED_POLICIES = ["randomize", "fixed", "increment"];

  // v0.4 stability mode: keep the UI in Simplified Chinese and prevent the
  // legacy page-wide i18n watcher from attaching. main already proved stable
  // without that watcher on the same phone/browser path.
  try { localStorage.setItem("comfy-remote-language", "zh-CN"); } catch (_) {}
  window.ComfyI18n?.setLanguage?.("zh-CN");

  const observerPrototype = window.MutationObserver?.prototype;
  const nativeObserve = observerPrototype?.observe;
  if (observerPrototype && nativeObserve) {
    let skippedLegacyI18nObserver = false;
    observerPrototype.observe = function(target, options) {
      const legacyPageWideObserver = !skippedLegacyI18nObserver
        && target === document.body
        && options?.subtree === true
        && options?.childList === true
        && options?.characterData === true
        && options?.attributes === true;
      if (legacyPageWideObserver) {
        skippedLegacyI18nObserver = true;
        observerPrototype.observe = nativeObserve;
        return;
      }
      return nativeObserve.call(this, target, options);
    };
  }

  function t(text) {
    return text;
  }

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
      item?.semantic === "seed" || item?.id === "seed" || /(?:^|_)seed$/i.test(item?.input || "")
    ) || null;
  }

  const baseApiActionV04 = apiAction;
  apiAction = function(path, options = {}) {
    if (path === "/api/workflows" && String(options.method || "GET").toUpperCase() === "POST" && typeof options.body === "string") {
      try {
        const payload = JSON.parse(options.body);
        const parameters = payload?.config?.parameters;
        const seed = seedBindingFromInspection();
        const alreadySaved = Array.isArray(parameters) && parameters.some(item =>
          item?.id === "seed" || item?.ui?.semantic === "seed" || /(?:^|_)seed$/i.test(item?.input || "")
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
          payload.config.default_seed_policy = document.querySelector("#v04-config-seed-policy")?.value || payload.config.default_seed_policy || "randomize";
          options = { ...options, body: JSON.stringify(payload) };
        }
      } catch (_) {}
    }
    return baseApiActionV04(path, options);
  };

  function cleanSettingsChips() {
    document.querySelectorAll("#settings-chips .settings-chip").forEach(chip => {
      const text = chip.textContent.trim();
      if (/工作流决定|跟随源图|跟随输入图/.test(text)) chip.remove();
    });
  }

  function cleanResolutionCopy() {
    document.querySelectorAll(".v04-resolution small, .v04-media-resolution .field small, .v04-media-resolution > p").forEach(node => node.remove());
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

  function syncSeedQuickControl() {
    if (document.querySelector(".v04-seed-quick")) return;
    const preset = selectedPreset();
    if (!preset) return;

    if (preset.family !== "generic") {
      const summary = document.querySelector("#advanced-settings > summary > span");
      if (summary && preset.seed_policy?.supported) summary.textContent = "高级设置 · Seed";
      return;
    }

    const entry = seedEntry(preset);
    const policy = document.querySelector("#job-form [data-v04-seed-policy]");
    if (!entry || !policy) return;
    const [seedId] = entry;
    const seedInput = document.querySelector(`#job-form [data-generic-binding="${CSS.escape(seedId)}"]`);
    const policyField = policy.closest("label.field");
    const seedField = seedInput?.closest("label.field");
    if (!policyField || !seedField) return;

    const section = document.createElement("section");
    section.className = "creation-section v04-seed-quick";
    section.innerHTML = '<div class="section-heading"><span>Seed</span></div><div class="advanced-grid v04-seed-grid"></div>';
    const grid = section.querySelector(".v04-seed-grid");
    policyField.querySelector(":scope > span")?.replaceChildren("模式");
    seedField.querySelector(":scope > span")?.replaceChildren("数值");
    grid.append(policyField, seedField);
    document.querySelector("#basic-settings")?.before(section);
  }

  function installPromptDismiss() {
    if (!document.querySelector("#v04-mobile-ux-style")) {
      const style = document.createElement("style");
      style.id = "v04-mobile-ux-style";
      style.textContent = `
        .v04-keyboard-dismiss { display:none; margin-left:auto; border:0; background:transparent; color:var(--muted, #9a9f95); font:inherit; font-size:13px; padding:4px 0 4px 12px; }
        .prompt-field:focus-within .v04-keyboard-dismiss,
        .semantic-prompt:focus-within .v04-keyboard-dismiss { display:inline-flex; }
        .v04-seed-quick .advanced-grid { margin-top:14px; }
      `;
      document.head.append(style);
    }

    document.querySelectorAll('#job-form textarea[name="prompt"], #job-form textarea[data-generic-binding="prompt"], #job-form textarea[data-generic-binding="positive_prompt"]').forEach(textarea => {
      const field = textarea.closest("label");
      const heading = field?.querySelector(".section-heading");
      if (!heading || heading.querySelector(".v04-keyboard-dismiss")) return;
      const button = document.createElement("button");
      button.type = "button";
      button.className = "v04-keyboard-dismiss";
      button.textContent = "收起键盘";
      button.addEventListener("click", event => {
        event.preventDefault();
        event.stopPropagation();
        textarea.blur();
      });
      heading.append(button);
    });
  }

  function syncCreationUx() {
    cleanResolutionCopy();
    cleanSettingsChips();
    syncGenerationSettingsVisibility();
    syncSeedQuickControl();
    installPromptDismiss();
  }

  const baseApplyPresetV04 = applyPreset;
  applyPreset = function(presetId, overrides = {}) {
    document.querySelector(".v04-seed-quick")?.remove();
    const preset = state.presets.get(presetId);
    ensureSeedMetadata(preset);
    const result = baseApplyPresetV04(presetId, overrides);
    queueMicrotask(syncCreationUx);
    return result;
  };

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelector("#language-toggle")?.remove();
    document.documentElement.lang = "zh-CN";
    queueMicrotask(syncCreationUx);

    document.querySelector("#open-generation-settings")?.addEventListener("click", () => {
      const done = document.querySelector("#sheet-done span");
      if (done) done.textContent = "关闭";
    });

    document.querySelector("#job-form")?.addEventListener("input", () => queueMicrotask(cleanSettingsChips));
    document.querySelector("#job-form")?.addEventListener("change", () => queueMicrotask(() => {
      cleanSettingsChips();
      cleanResolutionCopy();
    }));

    document.addEventListener("pointerdown", event => {
      const active = document.activeElement;
      if (active?.tagName === "TEXTAREA" && event.target !== active && !event.target.closest?.(".v04-keyboard-dismiss")) {
        active.blur();
      }
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
        pill.innerHTML = `<span></span>${panel.online ? t("面板在线") : t("面板离线")}`;
      }

      const stateLabels = {
        online: t("在线"),
        starting: t("正在启动"),
        offline: t("离线"),
        unknown: t("未知")
      };
      const comfyState = comfy.state || (comfy.online ? "online" : "unknown");
      const comfyLabel = stateLabels[comfyState] || comfyState;
      const overview = document.querySelector("#device-overview");
      if (overview) {
        overview.innerHTML = `<div class="device-chip ${panel.online ? "online" : ""}"><small>PANEL</small><strong>${panel.online ? t("在线") : t("离线")}</strong></div><div class="device-chip ${comfyState === "online" ? "online" : ""}"><small>COMFYUI</small><strong>${escapeHtml(comfyLabel)}${comfyState === "online" && comfy.version ? ` · ${escapeHtml(comfy.version)}` : ""}</strong></div><div class="device-chip"><small>${t("队列任务")}</small><strong>${comfy.queue_count ?? "—"}</strong></div>`;
      }
    };
  }
})();
