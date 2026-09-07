(() => {
  const ACTIVE_STATUSES = new Set(["submitting", "queued", "running"]);
  const RESOLUTION_VALUES = ["0.5", "1.0", "1.5", "2.0", "original"];
  const seedPolicyLabel = value => ({ randomize: "随机", fixed: "固定", increment: "递增" })[value] || value;
  const resolutionLabel = value => value === "original" ? "保持原图" : `${value} MP`;

  const MediaUI = window.ComfyRemoteMediaUI = window.ComfyRemoteMediaUI || {};

  MediaUI.bindSingleImageInput = function(input, { card = null, image = null } = {}) {
    if (!input || input.dataset.mediaUiBound === "1") return;
    const targetCard = card || input.closest(".upload-card");
    if (!targetCard) return;
    let preview = image || targetCard.querySelector(":scope > img");
    if (!preview) {
      preview = document.createElement("img");
      preview.alt = "图片预览";
      input.insertAdjacentElement("afterend", preview);
    }

    const revoke = () => {
      if (preview.dataset.objectUrl) URL.revokeObjectURL(preview.dataset.objectUrl);
      delete preview.dataset.objectUrl;
    };
    const sync = () => {
      const file = input.files?.[0];
      revoke();
      targetCard.classList.toggle("has-image", Boolean(file));
      if (!file) {
        preview.removeAttribute("src");
        return;
      }
      const url = URL.createObjectURL(file);
      preview.dataset.objectUrl = url;
      preview.src = url;
    };

    input.dataset.mediaUiBound = "1";
    input.addEventListener("change", sync);
    sync();
  };

  function genericFamily(job) {
    return state.presets.get(job?.preset_id)?.family
      || state.workflowItems?.get(job?.preset_id)?.manifest?.family
      || null;
  }

  function prepareGenericImageCards() {
    const preset = selectedPreset();
    if (!preset || preset.family !== "generic") return;
    const slots = preset.input_bindings?.media?.slots || {};
    for (const [role, slot] of Object.entries(slots)) {
      if (slot?.kind !== "image") continue;
      const input = document.querySelector(`#job-form input[name="${CSS.escape(role)}"]`);
      const card = input?.closest(".generic-reference-card");
      if (!input || !card) continue;
      card.classList.add("upload-card");
      let image = card.querySelector(":scope > img");
      if (!image) {
        image = document.createElement("img");
        image.alt = slot.ui?.label ? `${slot.ui.label}预览` : "参考图预览";
        input.insertAdjacentElement("afterend", image);
      }
      MediaUI.bindSingleImageInput(input, { card, image });
    }
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
          note: slot.semantic === "source_image" || slot.ui?.semantic === "source_image"
            ? "缩放 img2img 源图可能同时改变生成尺寸"
            : (!slot.allow_auto ? "该输入用途不明确或存在像素级关联，默认保持原图" : ""),
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
          note: "",
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
        note: "",
      }];
    }
    return [];
  }

  function resolutionOptions(spec, selected) {
    const values = spec.allowAuto ? RESOLUTION_VALUES : ["original"];
    return values.map(value => `<option value="${value}"${String(value) === String(selected) ? " selected" : ""}>${resolutionLabel(value)}</option>`).join("");
  }

  function requestedResolutionValue(spec, overrides) {
    const value = overrides?.media_resolution?.[spec.role]
      || (spec.role.startsWith("image_") ? overrides?.media_resolution?.image : null);
    const policy = value?.policy || value?.resolution_policy || spec.policy;
    return policy === "auto" ? String(value?.target_megapixels ?? spec.target ?? 1.0) : "original";
  }

  function seedStorageKey(preset) {
    if (preset?.id === "h3-ref2va-group" || preset?.family === "ref2va") {
      return "comfy-remote.ref2va.seed-policy";
    }
    if (preset?.id === "h3-fl2va-group" || preset?.family === "fl2va") {
      return "comfy-remote.fl2va.seed-policy";
    }
    return "";
  }

  function validSeedPolicy(value) {
    return ["randomize", "fixed", "increment"].includes(String(value || ""));
  }

  function rememberedSeedPolicy(preset) {
    const key = seedStorageKey(preset);
    if (!key) return "";
    try {
      const value = window.localStorage.getItem(key);
      return validSeedPolicy(value) ? value : "";
    } catch (_) {
      return "";
    }
  }

  function rememberSeedPolicy(preset, value) {
    const key = seedStorageKey(preset);
    if (!key || !validSeedPolicy(value)) return;
    try { window.localStorage.setItem(key, value); } catch (_) {}
  }

  function seedControlValue(preset, overrides, live) {
    const explicit = overrides?.seed_policy ?? overrides?.values?.seed_policy;
    if (validSeedPolicy(explicit)) return explicit;
    if (validSeedPolicy(live)) return live;
    return rememberedSeedPolicy(preset) || preset?.seed_policy?.default || "randomize";
  }

  function installGenericControls(preset, overrides = {}) {
    const root = document.querySelector("#generic-parameters");
    if (!root) return;
    root.querySelectorAll(".v04-control").forEach(node => node.remove());

    const parameters = preset?.parameters || {};
    const seedEntry = Object.entries(parameters).find(([id, spec]) =>
      id === "seed" || spec?.ui?.semantic === "seed"
    );
    if (preset?.seed_policy?.supported && seedEntry) {
      const [seedId] = seedEntry;
      const seedInput = root.querySelector(`[data-generic-binding="${CSS.escape(seedId)}"]`);
      const seedLabel = seedInput?.closest("label.field");
      if (seedInput && seedLabel) {
        const policy = seedControlValue(preset, overrides);
        const wrapper = document.createElement("label");
        wrapper.className = "field v04-control";
        wrapper.innerHTML = `<span>Seed 策略</span><select data-v04-seed-policy>
          <option value="randomize">随机</option>
          <option value="fixed">固定</option>
          <option value="increment">递增</option>
        </select><input type="hidden" data-generic-binding="seed_policy" data-value-type="string">`;
        seedLabel.before(wrapper);
        const select = wrapper.querySelector("select");
        const hiddenPolicy = wrapper.querySelector('[data-generic-binding="seed_policy"]');
        select.value = policy;
        const base = overrides?.seed_value ?? overrides?.values?.[seedId] ?? overrides?.[seedId];
        if (policy !== "randomize" && base != null && base !== "") seedInput.value = String(base);
        const sync = () => {
          hiddenPolicy.value = select.value;
          seedLabel.classList.toggle("hidden", select.value === "randomize");
          if (select.value === "randomize") seedInput.value = "";
          else if (!seedInput.value) seedInput.value = String(overrides?.seed_value ?? parameters[seedId]?.default ?? parameters[seedId]?.minimum ?? 0);
        };
        select.addEventListener("change", sync);
        sync();
      }
    }

    const specs = imageSlotSpecs(preset);
    if (specs.length) {
      const section = document.createElement("details");
      section.className = "generic-advanced v04-control v04-media-resolution";
      section.open = false;
      section.innerHTML = `<summary><span>参考图分辨率</span><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 9 6 6 6-6"/></svg></summary><div class="generic-advanced-grid"></div><p>只降低进入 Workflow 的参考图像素，不裁剪、不放大小图。</p>`;
      const grid = section.querySelector(".generic-advanced-grid");
      const same = specs.every(item =>
        item.policy === specs[0].policy
        && Number(item.target ?? 1) === Number(specs[0].target ?? 1)
        && item.allowAuto === specs[0].allowAuto
      );
      const visibleSpecs = same && specs.length > 1 ? [{ ...specs[0], role: "image", label: "全部参考图" }] : specs;
      for (const spec of visibleSpecs) {
        const field = document.createElement("label");
        field.className = "field";
        field.innerHTML = `<span>${escapeHtml(spec.label)}</span><select data-v04-resolution="${escapeHtml(spec.role)}">${resolutionOptions(spec, requestedResolutionValue(spec, overrides))}</select>${spec.note ? `<small>${escapeHtml(spec.note)}</small>` : ""}`;
        grid.append(field);
      }
      const hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.className = "v04-control";
      hidden.dataset.genericBinding = "media_resolution";
      hidden.dataset.valueType = "string";
      section.append(hidden);
      root.append(section);
      const sync = () => {
        hidden.value = JSON.stringify(collectResolutionOverrides(preset));
      };
      section.querySelectorAll("[data-v04-resolution]").forEach(select => select.addEventListener("change", sync));
      sync();
    }
  }

  function collectResolutionOverrides(preset = selectedPreset()) {
    const result = {};
    const selects = document.querySelectorAll("#job-form [data-v04-resolution]");
    for (const select of selects) {
      const role = select.dataset.v04Resolution;
      const value = select.value;
      result[role] = value === "original"
        ? { policy: "original", target_megapixels: null }
        : { policy: "auto", target_megapixels: Number(value) };
    }
    return result;
  }

  function installCreationControls(preset, overrides = {}) {
    if (preset?.family === "generic") installGenericControls(preset, overrides);
  }

  const CreationControls = window.ComfyRemoteCreationControls = window.ComfyRemoteCreationControls || {};
  CreationControls.install = installCreationControls;

  const baseApplyPresetForMedia = applyPreset;
  applyPreset = function(...args) {
    const result = baseApplyPresetForMedia(...args);
    const preset = state.presets.get(args[0]) || selectedPreset();
    const overrides = args[1] || {};
    queueMicrotask(() => {
      prepareGenericImageCards();
      installCreationControls(preset, overrides);
    });
    return result;
  };

  function hasProgress(value) {
    return value !== null && value !== undefined && Number.isFinite(Number(value));
  }

  function stabilizeGenericProgress(job) {
    const previous = state.jobs.get(job?.id);
    if (!previous || genericFamily(job) !== "generic") return job;
    if (!ACTIVE_STATUSES.has(previous.status) || !ACTIVE_STATUSES.has(job.status)) return job;

    const next = { ...job };
    if (!hasProgress(next.progress_percent) && hasProgress(previous.progress_percent)) {
      next.progress_percent = previous.progress_percent;
    }
    return next;
  }

  function patchActiveGenericCard(job, previous) {
    const list = document.querySelector("#jobs-list");
    const card = list?.querySelector(`[data-job="${CSS.escape(job.id)}"]`);
    if (!card || !previous) return false;
    if (genericFamily(job) !== "generic") return false;
    if (!ACTIVE_STATUSES.has(previous.status) || !ACTIVE_STATUSES.has(job.status)) return false;

    state.jobs.set(job.id, job);

    const status = card.querySelector(".job-status");
    if (status) {
      status.className = `job-status ${job.status}`;
      status.textContent = statusLabels[job.status] || job.status;
    }

    const progress = Math.max(0, Math.min(100, Number(job.progress_percent) || 0));
    const queueText = job.status === "queued" && job.queue_position ? ` · 第 ${job.queue_position} 位` : "";
    const progressBox = card.querySelector(".job-progress");
    if (progressBox) {
      const label = progressBox.querySelector("span");
      const value = progressBox.querySelector("b");
      const track = progressBox.querySelector(".progress-track");
      if (label) label.textContent = `${job.stage || "等待状态"}${queueText}`;
      if (value) value.textContent = `${progress}% · ${formatDuration(job.elapsed_seconds)}`;
      if (track) {
        track.value = progress;
        track.setAttribute("aria-label", `进度 ${progress}%`);
      }
    }

    updateJobsSummary();
    return true;
  }

  const baseJobCard = jobCard;
  jobCard = function(job) {
    let html = baseJobCard(job);
    if (job?.actual_seed != null) {
      const policy = seedPolicyLabel(job.seed_policy || "fixed");
      const seedMeta = `<span>Seed ${escapeHtml(job.actual_seed)}</span><span>${escapeHtml(policy)}</span>`;
      html = html.replace('<div class="job-meta">', `<div class="job-meta">${seedMeta}`);
    }
    return html;
  };

  const baseUpsertJob = upsertJob;
  upsertJob = function(job) {
    const previous = state.jobs.get(job?.id);
    const stable = stabilizeGenericProgress(job);
    if (patchActiveGenericCard(stable, previous)) return;
    return baseUpsertJob(stable);
  };

  function injectConfiguratorControls(result) {
    const root = document.querySelector("#workflow-inspection");
    if (!root) return;
    root.querySelector(".v04-configurator")?.remove();
    const imageInputs = (result?.media_inputs || []).filter(item => item.kind === "image");
    const supportsSeed = (result?.parameters || []).some(item => item.semantic === "seed" || item.id === "seed");
    if (!supportsSeed && !imageInputs.length) return;

    const section = document.createElement("section");
    section.className = "v2-analysis-section v04-configurator";
    const rows = [];
    if (supportsSeed) {
      const existing = state.workflowEditingDetail?.definition?.manifest?.default_seed_policy || "randomize";
      rows.push(`<label class="field"><span>默认 Seed 策略</span><select id="v04-config-seed-policy">
        <option value="randomize"${existing === "randomize" ? " selected" : ""}>随机</option>
        <option value="fixed"${existing === "fixed" ? " selected" : ""}>固定</option>
        <option value="increment"${existing === "increment" ? " selected" : ""}>递增</option>
      </select></label>`);
    }
    for (const item of imageInputs) {
      const existingSlots = state.workflowEditingDetail?.definition?.manifest?.input_bindings?.media?.slots || {};
      const existing = Object.values(existingSlots).find(slot =>
        String(slot?.node) === String(item.node) && String(slot?.input) === String(item.input)
      );
      const policy = existing?.resolution_policy || item.resolution_policy || "original";
      const target = existing?.target_megapixels ?? item.target_megapixels ?? 1.0;
      const selected = policy === "auto" ? String(target) : "original";
      const allowAuto = existing?.allow_auto ?? item.allow_auto ?? false;
      const spec = { allowAuto };
      rows.push(`<label class="field"><span>${escapeHtml(item.label || "图片输入")}分辨率</span>
        <select data-v04-config-media="${escapeHtml(item.id)}" data-node="${escapeHtml(item.node)}" data-input="${escapeHtml(item.input)}" data-allow-auto="${allowAuto ? "1" : "0"}">${resolutionOptions(spec, selected)}</select>
        <small>${escapeHtml(item.resolution_note || (allowAuto ? "可在创作页临时覆盖" : "保守保持原图"))}</small>
      </label>`);
    }
    section.innerHTML = `<div class="section-heading"><span>创作默认值</span><small>v0.4</small></div><div class="generic-advanced-grid">${rows.join("")}</div>`;
    root.append(section);
  }

  if (typeof renderWorkflowInspection === "function") {
    const baseRenderWorkflowInspection = renderWorkflowInspection;
    renderWorkflowInspection = function(result) {
      const value = baseRenderWorkflowInspection(result);
      queueMicrotask(() => injectConfiguratorControls(result));
      return value;
    };
  }

  const baseApiAction = apiAction;
  apiAction = function(path, options = {}) {
    if (path === "/api/workflows" && String(options.method || "GET").toUpperCase() === "POST" && typeof options.body === "string") {
      try {
        const payload = JSON.parse(options.body);
        if (payload?.config) {
          const policy = document.querySelector("#v04-config-seed-policy")?.value;
          if (policy) payload.config.default_seed_policy = policy;

          const controls = [...document.querySelectorAll("[data-v04-config-media]")];
          if (payload.config.media?.type === "slots") {
            for (const [role, slot] of Object.entries(payload.config.media.slots || {})) {
              const control = controls.find(item =>
                item.dataset.v04ConfigMedia === role
                || (String(slot?.node) === String(item.dataset.node) && String(slot?.input) === String(item.dataset.input))
              );
              if (!control || !slot) continue;
              const value = control.value;
              slot.resolution_policy = value === "original" ? "original" : "auto";
              slot.target_megapixels = value === "original" ? null : Number(value);
              slot.allow_auto = control.dataset.allowAuto === "1";
            }
          }
          options = { ...options, body: JSON.stringify(payload) };
        }
      } catch (_) {}
    }
    return baseApiAction(path, options);
  };

  function syncSubmitMetadata() {
    const preset = selectedPreset();
    if (!preset) return;
    const form = document.querySelector("#job-form");
    const policy = form.querySelector("[data-v04-seed-policy]")?.value;
    const resolution = collectResolutionOverrides(preset);

    if (preset.family === "generic") {
      const hiddenResolution = form.querySelector('[data-generic-binding="media_resolution"]');
      if (hiddenResolution) hiddenResolution.value = JSON.stringify(resolution);
      const hiddenPolicy = form.querySelector('[data-generic-binding="seed_policy"]');
      if (hiddenPolicy && policy) hiddenPolicy.value = policy;
      return;
    }

    let hidden = form.querySelector('input[name="values_json"].v04-control');
    if (!hidden) {
      hidden = document.createElement("input");
      hidden.type = "hidden";
      hidden.name = "values_json";
      hidden.className = "v04-control";
      form.append(hidden);
    }
    const seedInput = form.querySelector('input[name="seed"]');
    hidden.value = JSON.stringify({
      ...(policy ? { seed_policy: policy } : {}),
      ...(policy && policy !== "randomize" ? { seed_value: seedInput?.value || "0" } : {}),
      media_resolution: resolution,
    });
  }

  document.addEventListener("DOMContentLoaded", () => {
    queueMicrotask(() => {
      prepareGenericImageCards();
      installCreationControls(selectedPreset(), {});
    });
    document.querySelector("#job-form")?.addEventListener("submit", syncSubmitMetadata, true);
  });
})();
