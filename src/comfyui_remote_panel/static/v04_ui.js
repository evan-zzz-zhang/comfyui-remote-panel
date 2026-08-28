(() => {
  const SEED_POLICIES = ["randomize", "fixed", "increment"];
  const BASIC_SEMANTICS = new Set([
    "prompt", "positive_prompt", "negative_prompt", "width", "height", "batch_size",
    "duration", "duration_seconds", "aspect_ratio", "resolution", "megapixels",
  ]);
  const LABELS = {
    seed: "Seed",
    steps: "Steps",
    cfg: "CFG",
    sampler: "Sampler",
    scheduler: "Scheduler",
    denoise: "Denoise",
    checkpoint: "Checkpoint",
    lora: "LoRA",
    vae: "VAE",
  };
  const RESOLUTION_VALUES = ["0.5", "1.0", "1.5", "2.0", "original"];
  let syncQueued = false;

  function workflowKind(preset) {
    return preset?.family === "generic" ? "generic" : "specialized";
  }

  function parameterSemantic(id, spec) {
    const semantic = spec?.ui?.semantic;
    if (semantic && semantic !== "advanced") return semantic;
    if (id === "seed" || /(?:^|_)seed$/i.test(id)) return "seed";
    if (id === "steps" || /(?:^|_)steps$/i.test(id)) return "steps";
    if (id === "cfg" || /(?:^|_)cfg(?:_scale)?$/i.test(id)) return "cfg";
    if (/sampler(?:_name)?$/i.test(id)) return "sampler";
    if (/scheduler$/i.test(id)) return "scheduler";
    if (/denoise(?:_strength)?$/i.test(id)) return "denoise";
    if (/ckpt_name|checkpoint/i.test(id)) return "checkpoint";
    if (/lora/i.test(id)) return "lora";
    if (/vae/i.test(id)) return "vae";
    return semantic === "advanced" ? "advanced" : id;
  }

  function parameterSpec(preset, id, publicSpec = {}) {
    // /api/presets intentionally strips node/input from public parameter metadata.
    // The authoritative Generic workflow bindings remain in input_bindings.values.
    const bindingSpec = preset?.input_bindings?.values?.[id]
      || state.workflowItems?.get?.(preset?.id)?.manifest?.parameters?.[id]
      || {};
    return {
      ...bindingSpec,
      ...publicSpec,
      ui: {
        ...(bindingSpec?.ui || {}),
        ...(publicSpec?.ui || {}),
      },
    };
  }

  function parameterEntries(preset) {
    return Object.entries(preset?.parameters || {}).map(([id, spec]) => [
      id,
      parameterSpec(preset, id, spec),
    ]);
  }

  function hasRealBinding(spec) {
    return spec?.node != null && Boolean(spec?.input);
  }

  function seedEntry(preset) {
    return parameterEntries(preset).find(([id, spec]) =>
      parameterSemantic(id, spec) === "seed" && hasRealBinding(spec)
    ) || null;
  }

  function ensureSeedMetadata(preset) {
    const entry = seedEntry(preset);
    if (!entry) return;
    const [id, spec] = entry;
    const manifestDefault = state.workflowItems?.get?.(preset.id)?.manifest?.default_seed_policy;
    if (preset.parameters?.[id]) {
      preset.parameters[id].ui = {
        ...(preset.parameters[id].ui || {}),
        semantic: "seed",
        label: preset.parameters[id].ui?.label || spec.ui?.label || "Seed",
      };
    }
    preset.seed_policy = {
      supported: true,
      default: preset.seed_policy?.default || preset.default_seed_policy || manifestDefault || "randomize",
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

  // Configurator may detect Seed even when an older import UI did not keep it.
  // Persist the real node/input binding so Generic UI can offer a policy without
  // inventing a parameter that is not present in the workflow.
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
      #advanced-settings.v04-specialized-advanced,
      .generic-advanced.v04-generic-advanced {
        overflow: visible;
        background: transparent;
        border: 0;
        border-radius: 0;
      }
      #advanced-settings.v04-specialized-advanced > summary,
      .generic-advanced.v04-generic-advanced > summary {
        min-height: 0;
        padding: 0;
        color: var(--text-primary);
        font-size: 15px;
        font-weight: 650;
      }
      #advanced-settings.v04-specialized-advanced[open] > summary,
      .generic-advanced.v04-generic-advanced[open] > summary { margin-bottom: 10px; }
      #advanced-settings.v04-specialized-advanced > .advanced-grid,
      .generic-advanced.v04-generic-advanced > .generic-advanced-grid {
        padding: 12px;
        background: var(--surface-1);
        border: 1px solid var(--border);
        border-radius: var(--radius);
      }
      #advanced-settings.v04-specialized-advanced > p,
      .generic-advanced.v04-generic-advanced > p { display: none; }
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
    if (!preset || !section || workflowKind(preset) !== "generic") return;
    const hasEditableSetting = ["width", "height", "batch_size"].some(id =>
      Boolean(preset.parameters?.[id] && document.querySelector(`#job-form [data-generic-binding="${CSS.escape(id)}"]`))
    );
    section.classList.toggle("hidden", !hasEditableSetting);
  }

  function genericValueSnapshot() {
    const values = {};
    document.querySelectorAll("#job-form [data-generic-binding]").forEach(input => {
      const id = input.dataset.genericBinding;
      if (!id) return;
      values[id] = input.type === "checkbox" ? input.checked : input.value;
    });
    return values;
  }

  function optionKeys(spec) {
    return Object.keys(spec?.values || {});
  }

  function genericField(id, spec, value) {
    const semantic = parameterSemantic(id, spec);
    const label = escapeHtml(spec?.ui?.label || LABELS[semantic] || id);
    const binding = `data-generic-binding="${escapeHtml(id)}" data-value-type="${escapeHtml(spec?.type || "string")}" data-workflow-node="${escapeHtml(spec.node)}" data-workflow-input="${escapeHtml(spec.input)}"`;
    if (spec.type === "boolean") {
      return `<label class="field"><span>${label}</span><input type="checkbox" name="generic_${escapeHtml(id)}" ${binding}${value ? " checked" : ""}></label>`;
    }
    if (spec.type === "enum") {
      const options = optionKeys(spec).map(option => `<option value="${escapeHtml(option)}"${String(option) === String(value) ? " selected" : ""}>${escapeHtml(option)}</option>`).join("");
      return `<label class="field"><span>${label}</span><select name="generic_${escapeHtml(id)}" ${binding}>${options}</select></label>`;
    }
    const type = ["integer", "number"].includes(spec.type) ? "number" : "text";
    return `<label class="field"><span>${label}</span><input type="${type}" name="generic_${escapeHtml(id)}" ${binding} value="${escapeHtml(value ?? "")}"${spec.minimum != null ? ` min="${escapeHtml(spec.minimum)}"` : ""}${spec.maximum != null ? ` max="${escapeHtml(spec.maximum)}"` : ""}${spec.step != null ? ` step="${escapeHtml(spec.step)}"` : ""}></label>`;
  }

  function imageSlotSpecs(preset) {
    const media = preset?.input_bindings?.media;
    if (!media) return [];
    if (media.type === "slots") {
      return Object.entries(media.slots || {})
        .filter(([role, slot]) => (slot?.kind || mediaKindFromRole(role)) === "image")
        .map(([role, slot]) => ({
          role,
          label: slot.ui?.label || role,
          policy: slot.resolution_policy || "original",
          target: slot.target_megapixels ?? 1.0,
          allowAuto: slot.allow_auto !== false,
        }));
    }
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
        role: "image",
        label: "参考图",
        policy: spec.resolution_policy || "auto",
        target: spec.target_megapixels ?? 1.0,
        allowAuto: spec.allow_auto !== false,
      }];
    }
    return [];
  }

  function resolutionLabel(value) {
    return value === "original" ? "保持原图" : `${value} MP`;
  }

  function resolutionOptions(spec, selected) {
    const values = spec.allowAuto ? RESOLUTION_VALUES : ["original"];
    return values.map(value => `<option value="${value}"${String(value) === String(selected) ? " selected" : ""}>${resolutionLabel(value)}</option>`).join("");
  }

  function resolutionValue(spec, snapshot) {
    const raw = snapshot.media_resolution;
    if (raw) {
      try {
        const parsed = typeof raw === "string" ? JSON.parse(raw) : raw;
        const value = parsed?.[spec.role] || (spec.role.startsWith("image_") ? parsed?.image : null);
        if (value) {
          const policy = value.policy || value.resolution_policy;
          return policy === "auto" ? String(value.target_megapixels ?? spec.target ?? 1.0) : "original";
        }
      } catch (_) {}
    }
    return spec.policy === "auto" ? String(spec.target ?? 1.0) : "original";
  }

  function removeGenericAdvanced() {
    document.querySelectorAll("#job-form .generic-advanced").forEach(node => node.remove());
  }

  function syncGenericResolutionHidden(section) {
    const hidden = section.querySelector('[data-generic-binding="media_resolution"]');
    if (!hidden) return;
    const values = {};
    section.querySelectorAll("[data-v04-resolution]").forEach(select => {
      const value = select.value;
      values[select.dataset.v04Resolution] = value === "original"
        ? { policy: "original", target_megapixels: null }
        : { policy: "auto", target_megapixels: Number(value) };
    });
    hidden.value = JSON.stringify(values);
  }

  function renderGenericAdvanced(preset, snapshot) {
    const form = document.querySelector("#job-form");
    const basic = document.querySelector("#basic-settings");
    const specialized = document.querySelector("#advanced-settings");
    if (!form || !basic) return;

    if (specialized) specialized.classList.add("hidden");
    removeGenericAdvanced();

    const seed = seedEntry(preset);
    const seedId = seed?.[0] || null;
    const entries = parameterEntries(preset).filter(([id, spec]) => {
      if (!hasRealBinding(spec)) return false;
      const semantic = parameterSemantic(id, spec);
      return !BASIC_SEMANTICS.has(semantic) && id !== seedId;
    });
    const resolutionSpecs = imageSlotSpecs(preset);
    const supportsSeed = Boolean(seed && preset.seed_policy?.supported);
    if (!entries.length && !supportsSeed && !resolutionSpecs.length) return;

    const section = document.createElement("details");
    section.className = "generic-advanced v04-generic-advanced";
    section.dataset.refinedOrder = "true";
    section.innerHTML = `<summary><span>高级设置</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></summary><div class="generic-advanced-grid"></div>`;
    const grid = section.querySelector(".generic-advanced-grid");

    const overrideValues = snapshot.__overrides || {};
    const valueFor = (id, spec) => snapshot[id] ?? overrideValues[id] ?? spec?.default ?? "";
    for (const [id, spec] of entries) {
      grid.insertAdjacentHTML("beforeend", genericField(id, spec, valueFor(id, spec)));
    }

    if (supportsSeed) {
      const [id, spec] = seed;
      const policy = snapshot.seed_policy || overrideValues.seed_policy || preset.seed_policy?.default || "randomize";
      const policyField = document.createElement("label");
      policyField.className = "field v04-seed-policy";
      policyField.innerHTML = `<span>Seed 策略</span><select data-v04-seed-policy>
        <option value="randomize">随机</option>
        <option value="fixed">固定</option>
        <option value="increment">递增</option>
      </select><input type="hidden" data-generic-binding="seed_policy" data-value-type="string">`;
      grid.append(policyField);
      const select = policyField.querySelector("select");
      const hidden = policyField.querySelector('[data-generic-binding="seed_policy"]');
      select.value = SEED_POLICIES.includes(policy) ? policy : "randomize";
      hidden.value = select.value;

      const seedWrapper = document.createElement("div");
      seedWrapper.innerHTML = genericField(id, spec, valueFor(id, spec));
      const seedField = seedWrapper.firstElementChild;
      grid.append(seedField);
      const seedInput = seedField.querySelector("[data-generic-binding]");
      const syncSeed = () => {
        hidden.value = select.value;
        seedField.classList.toggle("hidden", select.value === "randomize");
        if (select.value === "randomize") seedInput.value = "";
        else if (!seedInput.value) seedInput.value = String(overrideValues.seed_value ?? spec.default ?? spec.minimum ?? 0);
        seedInput.placeholder = select.value === "increment" ? "起始 Seed" : "Seed";
      };
      select.addEventListener("change", syncSeed);
      syncSeed();
    }

    if (resolutionSpecs.length) {
      const same = resolutionSpecs.every(item =>
        item.policy === resolutionSpecs[0].policy
        && Number(item.target ?? 1) === Number(resolutionSpecs[0].target ?? 1)
        && item.allowAuto === resolutionSpecs[0].allowAuto
      );
      const visibleSpecs = same && resolutionSpecs.length > 1
        ? [{ ...resolutionSpecs[0], role: "image", label: "参考图" }]
        : resolutionSpecs;
      for (const spec of visibleSpecs) {
        const label = visibleSpecs.length === 1 ? "参考图分辨率" : `${spec.label}分辨率`;
        const field = document.createElement("label");
        field.className = "field v04-resolution";
        field.innerHTML = `<span>${escapeHtml(label)}</span><select data-v04-resolution="${escapeHtml(spec.role)}">${resolutionOptions(spec, resolutionValue(spec, snapshot))}</select>`;
        grid.append(field);
      }
      const hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.dataset.genericBinding = "media_resolution";
      hidden.dataset.valueType = "string";
      section.append(hidden);
      section.querySelectorAll("[data-v04-resolution]").forEach(select => {
        select.addEventListener("change", () => syncGenericResolutionHidden(section));
      });
      syncGenericResolutionHidden(section);
    }

    basic.insertAdjacentElement("afterend", section);
  }

  function renderSpecializedAdvanced() {
    removeGenericAdvanced();
    const specialized = document.querySelector("#advanced-settings");
    if (!specialized) return;
    specialized.classList.add("v04-specialized-advanced");
    const title = specialized.querySelector(":scope > summary > span");
    if (title) title.textContent = "高级设置";
    cleanResolutionCopy(specialized);
  }

  function syncCreationUx(overrides = {}) {
    installV04Styles();
    cleanSettingsChips();
    syncGenerationSettingsVisibility();

    const preset = selectedPreset();
    if (!preset) return;
    ensureSeedMetadata(preset);
    if (workflowKind(preset) === "generic") {
      const snapshot = genericValueSnapshot();
      snapshot.__overrides = overrides?.values && typeof overrides.values === "object"
        ? { ...overrides, ...overrides.values }
        : (overrides || {});
      renderGenericAdvanced(preset, snapshot);
    } else {
      renderSpecializedAdvanced();
    }
  }

  function queueCreationUx(overrides = {}) {
    if (syncQueued) return;
    syncQueued = true;
    queueMicrotask(() => {
      syncQueued = false;
      syncCreationUx(overrides);
    });
  }

  const baseApplyPresetV04 = applyPreset;
  applyPreset = function(presetId, overrides = {}) {
    const result = baseApplyPresetV04(presetId, overrides);
    ensureSeedMetadata(state.presets.get(presetId) || selectedPreset());
    // configurator_v2_runtime queues its own controls first; this renderer runs
    // immediately after and establishes the final, family-isolated UI before paint.
    queueCreationUx(overrides);
    return result;
  };

  document.addEventListener("DOMContentLoaded", () => {
    installV04Styles();
    queueCreationUx({});

    document.querySelector("#job-form")?.addEventListener("input", () => queueMicrotask(cleanSettingsChips));

    // No custom keyboard button. Tapping outside the prompt returns focus to the page.
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