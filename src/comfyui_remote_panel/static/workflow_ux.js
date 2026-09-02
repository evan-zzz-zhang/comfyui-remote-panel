(() => {
  const baseApplyPreset = applyPreset;
  const baseLoadPresets = loadPresets;

  state.workflowItems = new Map();
  state.workflowInspection = null;
  state.workflowEditingDetail = null;
  state.artifactHydrated = new Set();

  const BASIC_SEMANTICS = new Set([
    "prompt", "positive_prompt", "negative_prompt", "width", "height", "batch_size",
    "duration", "duration_seconds", "aspect_ratio", "resolution", "megapixels",
  ]);
  const LABELS = {
    prompt: "提示词", positive_prompt: "正面提示词", negative_prompt: "负面提示词",
    width: "宽度", height: "高度", batch_size: "生成数量", duration_seconds: "时长",
    aspect_ratio: "画幅", megapixels: "分辨率",
  };

  const icon = name => {
    const paths = {
      check: '<path d="m5 12 4 4L19 6"/>',
      chevron: '<path d="m9 18 6-6-6-6"/>',
      close: '<path d="M6 6l12 12M18 6 6 18"/>',
      plus: '<path d="M12 5v14M5 12h14"/>',
      image: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="m4 16 5-5 4 4 2-2 5 5"/><path d="M15 8h.01"/>',
      video: '<rect x="3" y="5" width="14" height="14" rx="2"/><path d="m17 9 4-2v10l-4-2"/>',
      audio: '<path d="M9 18V5l10-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="16" cy="16" r="3"/>',
      more: '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
      settings: '<path d="M4 7h10M18 7h2M4 17h2M10 17h10"/><circle cx="16" cy="7" r="2"/><circle cx="8" cy="17" r="2"/>',
    };
    return `<svg viewBox="0 0 24 24" aria-hidden="true">${paths[name] || paths.chevron}</svg>`;
  };

  function mergedOverrides(overrides) {
    if (overrides?.values && typeof overrides.values === "object") return { ...overrides, ...overrides.values };
    return overrides || {};
  }

  function workflowDisplayName(id, fallback = id) {
    return state.workflowItems.get(id)?.name || state.presets.get(id)?.name || fallback;
  }

  function outputKind(preset) {
    if (preset?.output_kind) return preset.output_kind;
    const outputs = preset?.output_bindings || [];
    return (outputs.find(item => item.primary) || outputs[0] || {}).kind || "file";
  }

  function semanticFor(name, spec) {
    const semantic = spec?.ui?.semantic;
    if (semantic && semantic !== "advanced") return semantic;
    if (BASIC_SEMANTICS.has(name)) return name;
    if (/positive.*prompt|prompt.*positive/i.test(name)) return "positive_prompt";
    if (/negative.*prompt|prompt.*negative/i.test(name)) return "negative_prompt";
    if (/batch.*size|batch_count|count/i.test(name)) return name === "count" ? "batch_size" : name;
    return semantic === "advanced" ? "advanced" : name;
  }

  function normalizePresetUi(preset) {
    if (!preset) return { inputs: {}, advanced: [], outputKind: "file", category: "其他", description: "" };
    const family = preset.family || "generic";
    const inputs = {};
    const advanced = [];
    const add = (semantic, value = {}) => { if (!inputs[semantic]) inputs[semantic] = value; };

    if (family === "fl2va" || family === "ref2va") {
      add("prompt", { source: "h3" });
      add("duration_seconds", preset.parameters?.duration_seconds || {});
      add("aspect_ratio", preset.parameters?.aspect_ratio || {});
      add("megapixels", preset.parameters?.megapixels || {});
      if (family === "fl2va") {
        add("first_frame", { kind: "image", optional: true });
        add("last_frame", { kind: "image", optional: true });
      } else {
        add("reference_images", { kind: "image", max: preset.reference_media?.images?.max || 9 });
        add("reference_videos", { kind: "video", max: preset.reference_media?.videos?.max || 3 });
        add("reference_audios", { kind: "audio", max: preset.reference_media?.audios?.max || 3 });
      }
      advanced.push("scheduler", "sampler", "steps", "seed");
    } else {
      for (const [name, spec] of Object.entries(preset.parameters || {})) {
        const semantic = semanticFor(name, spec);
        if (semantic === "advanced" || !BASIC_SEMANTICS.has(semantic)) advanced.push(name);
        else add(semantic, { ...spec, parameter: name });
      }
      const media = preset.input_bindings?.media;
      if (media?.type === "slots") {
        const slots = Object.entries(media.slots || {});
        const counts = slots.reduce((acc, [, slot]) => { const kind = slot.kind || "file"; acc[kind] = (acc[kind] || 0) + 1; return acc; }, {});
        for (const [role, slot] of slots) {
          const kind = slot.kind || mediaKindFromRole(role) || "file";
          const semantic = kind === "image" ? (counts.image > 1 ? "reference_images" : "reference_image") : kind === "video" ? (counts.video > 1 ? "reference_videos" : "reference_video") : kind === "audio" ? (counts.audio > 1 ? "reference_audios" : "reference_audio") : role;
          add(semantic, { kind, role, slot, optional: slot.ui?.optional !== false });
        }
      }
    }

    const kind = outputKind(preset);
    const category = kind === "video" ? "视频" : kind === "image" ? "图片" : "其他";
    const description = family === "fl2va" ? "视频 · 首尾帧生成" : family === "ref2va" ? "视频 · 参考生成" : kind === "image" ? "图片 · ComfyUI 工作流" : kind === "video" ? "视频 · ComfyUI 工作流" : "ComfyUI 工作流";
    return { family, inputs, advanced, outputKind: kind, category, description };
  }

  function applyWorkflowDisplayNames() {
    for (const [id, item] of state.workflowItems) {
      const preset = state.presets.get(id);
      if (preset) preset.name = item.name;
    }
  }

  async function fetchWorkflowItems() {
    const response = await fetch("/api/workflows");
    if (!response.ok) throw new Error("无法加载工作流管理列表");
    const data = await response.json();
    state.workflowItems = new Map(data.items.map(item => [item.id, item]));
    applyWorkflowDisplayNames();
    return data.items;
  }

  function updateWorkflowPicker(preset) {
    const button = $("#workflow-picker-button");
    if (!button || !preset) return;
    const ui = normalizePresetUi(preset);
    button.querySelector("strong").textContent = preset.name;
    button.querySelector("small").textContent = ui.description;
    $("#active-preset-label").textContent = preset.name;
  }

  function ratioLabel(width, height) {
    const w = Number(width), h = Number(height);
    if (!w || !h) return "自定义";
    const known = [[1,1],[3,4],[4,3],[9,16],[16,9],[2,3],[3,2],[21,9]];
    const ratio = w / h;
    const match = known.find(([rw, rh]) => Math.abs(ratio - rw / rh) < .025);
    return match ? `${match[0]}:${match[1]}` : "自定义";
  }

  function currentSettings(preset) {
    const ui = normalizePresetUi(preset);
    if (ui.family === "fl2va" || ui.family === "ref2va") {
      const aspect = $("select[name=aspect_ratio]")?.value || "9:16";
      const duration = $("input[name=duration_seconds]")?.value || "5";
      const mp = $("#megapixels-value")?.value || "0.4";
      return [aspectLabel(aspect), `${duration} 秒`, `${mp} MP`];
    }
    const width = $('[data-generic-binding="width"]')?.value;
    const height = $('[data-generic-binding="height"]')?.value;
    const batch = $('[data-generic-binding="batch_size"]')?.value;
    const values = [];
    if (width && height) values.push(ratioLabel(width, height), `${width}×${height}`);
    if (batch) values.push(`${batch} 张`);
    return values.length ? values : [ui.category];
  }

  function updateSettingsSummary() {
    const preset = selectedPreset();
    const root = $("#settings-chips");
    if (!preset || !root) return;
    root.innerHTML = currentSettings(preset).map(value => `<span class="settings-chip">${escapeHtml(value)}</span>`).join("");
  }

  function genericNumberInput(id, spec, value) {
    return `<input class="semantic-hidden-value" type="number" name="generic_${escapeHtml(id)}" data-generic-binding="${escapeHtml(id)}" data-value-type="${escapeHtml(spec.type || "integer")}" value="${escapeHtml(value ?? "")}"${spec.minimum != null ? ` min="${escapeHtml(spec.minimum)}"` : ""}${spec.maximum != null ? ` max="${escapeHtml(spec.maximum)}"` : ""}${spec.step != null ? ` step="${escapeHtml(spec.step)}"` : ""}>`;
  }

  function genericAdvancedField(id, spec, value) {
    const label = escapeHtml(spec.ui?.label || LABELS[id] || id);
    if (spec.type === "boolean") return `<label class="field"><span>${label}</span><input type="checkbox" name="generic_${escapeHtml(id)}" data-generic-binding="${escapeHtml(id)}" data-value-type="boolean"${value ? " checked" : ""}></label>`;
    if (spec.type === "enum") return `<label class="field"><span>${label}</span><select name="generic_${escapeHtml(id)}" data-generic-binding="${escapeHtml(id)}" data-value-type="enum">${optionKeys(spec).map(option => `<option value="${escapeHtml(option)}"${String(option) === String(value) ? " selected" : ""}>${escapeHtml(option)}</option>`).join("")}</select></label>`;
    const type = ["integer", "number"].includes(spec.type) ? "number" : "text";
    return `<label class="field"><span>${label}</span><input type="${type}" name="generic_${escapeHtml(id)}" data-generic-binding="${escapeHtml(id)}" data-value-type="${escapeHtml(spec.type || "string")}" value="${escapeHtml(value ?? "")}"${spec.minimum != null ? ` min="${escapeHtml(spec.minimum)}"` : ""}${spec.maximum != null ? ` max="${escapeHtml(spec.maximum)}"` : ""}${spec.step != null ? ` step="${escapeHtml(spec.step)}"` : ""}></label>`;
  }

  function renderGenericForm(preset, overrides = {}) {
    const root = $("#generic-parameters");
    const parameters = preset.parameters || {};
    const values = mergedOverrides(overrides);
    const valueFor = id => values[id] ?? parameters[id]?.default ?? "";
    const html = [];

    const media = preset.input_bindings?.media;
    if (media?.type === "slots" && Object.keys(media.slots || {}).length) {
      html.push(`<section class="creation-section generic-reference"><div class="section-heading"><span>参考素材</span><small>可选</small></div>`);
      for (const [role, slot] of Object.entries(media.slots || {})) {
        const kind = slot.kind || mediaKindFromRole(role) || "file";
        const accept = kind === "image" ? "image/jpeg,image/png,image/webp" : kind === "video" ? "video/mp4,video/quicktime,video/webm" : kind === "audio" ? ".wav,.mp3,.flac,.ogg,.m4a" : "";
        const label = slot.ui?.label || (kind === "image" ? "参考图" : kind === "video" ? "参考视频" : kind === "audio" ? "参考音频" : role);
        const retained = state.retryRoles.includes(role);
        html.push(`<label class="generic-reference-card"><input type="file" name="${escapeHtml(role)}" accept="${accept}">${icon(kind === "image" ? "image" : kind === "video" ? "video" : "audio")}<span><strong>${escapeHtml(label)}</strong><small>${retained ? "未重新选择时沿用上次素材" : "添加参考素材"}</small></span></label>`);
      }
      html.push(`</section>`);
    }

    const positiveId = parameters.positive_prompt ? "positive_prompt" : (parameters.prompt ? "prompt" : null);
    if (positiveId) {
      html.push(`<label class="creation-section semantic-prompt"><span class="section-heading"><span>${positiveId === "prompt" ? "提示词" : "正面提示词"}</span><small>描述想生成的内容</small></span><textarea name="generic_${escapeHtml(positiveId)}" rows="5" data-generic-binding="${escapeHtml(positiveId)}" data-value-type="string" placeholder="描述画面、主体、风格和细节……">${escapeHtml(valueFor(positiveId))}</textarea></label>`);
    }
    if (parameters.negative_prompt) {
      const negative = valueFor("negative_prompt");
      html.push(`<details class="negative-prompt"><summary><span>负面提示词${negative ? " · 已使用工作流默认值" : " · 可选"}</span>${icon("chevron")}</summary><label class="semantic-prompt"><textarea name="generic_negative_prompt" rows="4" data-generic-binding="negative_prompt" data-value-type="string" placeholder="不希望出现的内容……">${escapeHtml(negative)}</textarea></label></details>`);
    }

    for (const id of ["width", "height", "batch_size"]) {
      if (parameters[id]) html.push(genericNumberInput(id, parameters[id], valueFor(id)));
    }

    const advancedEntries = Object.entries(parameters).filter(([id, spec]) => ![positiveId, "negative_prompt", "width", "height", "batch_size"].includes(id) && (semanticFor(id, spec) === "advanced" || !BASIC_SEMANTICS.has(semanticFor(id, spec))));
    if (advancedEntries.length) {
      html.push(`<details class="generic-advanced"><summary><span>高级设置</span>${icon("chevron")}</summary><div class="generic-advanced-grid">${advancedEntries.map(([id, spec]) => genericAdvancedField(id, spec, valueFor(id))).join("")}</div><p>这些参数来自手动映射，通常无需修改。</p></details>`);
    }

    root.innerHTML = html.join("");
    $("#basic-settings").classList.toggle("hidden", !(parameters.width || parameters.height || parameters.batch_size));
    $("#advanced-settings").classList.add("hidden");
    updateSettingsSummary();
  }

  function renderCreation(preset, overrides = {}) {
    if (!preset) return;
    const ui = normalizePresetUi(preset);
    updateWorkflowPicker(preset);
    const h3 = ui.family === "fl2va" || ui.family === "ref2va";
    $("#fl2va-media").classList.toggle("hidden", ui.family !== "fl2va");
    $("#ref2va-media").classList.toggle("hidden", ui.family !== "ref2va");
    $("#reference-section").classList.toggle("hidden", !h3);
    $("#job-form > .prompt-field").classList.toggle("hidden", !h3);
    $("#generic-parameters").classList.toggle("hidden", h3);
    $("#basic-settings").classList.remove("hidden");
    $("#advanced-settings").classList.toggle("hidden", !h3 || ui.advanced.length === 0);
    if (h3) {
      const prompt = $("textarea[name=prompt]");
      if (prompt) prompt.placeholder = ui.family === "fl2va" ? "描述主体、动作、镜头运动、对白和声音……" : "描述参考主体如何运动、镜头变化、对白和声音……";
      $("#prompt-hint").textContent = ui.family === "fl2va" ? "纯文字或首尾帧生成" : "可引用 Picture / Video / Audio";
      $("#reference-section-hint").textContent = ui.family === "fl2va" ? "首帧、尾帧均可选" : "最多 9 图 · 3 视频 · 3 音频";
    } else {
      renderGenericForm(preset, overrides);
    }
    updateSettingsSummary();
  }

  applyPreset = function(presetId, overrides = {}) {
    const merged = mergedOverrides(overrides);
    baseApplyPreset(presetId, merged);
    renderCreation(selectedPreset(), merged);
  };

  loadPresets = async function() {
    await baseLoadPresets();
    try { await fetchWorkflowItems(); } catch (_) {}
    applyWorkflowDisplayNames();
    const current = selectedPreset();
    if (current) applyPreset(current.id);
  };

  function openSheet(title, html) {
    $("#sheet-title").textContent = title;
    $("#sheet-body").innerHTML = html;
    $("#sheet-backdrop").classList.remove("hidden");
    document.body.classList.add("sheet-open");
  }

  function closeSheet() {
    $("#sheet-backdrop").classList.add("hidden");
    document.body.classList.remove("sheet-open");
  }

  function openWorkflowPicker() {
    // FL2VA physical assets are resolver targets.  The creation picker owns
    // only the virtual entry; the workflow manager still reads all assets
    // from /api/workflows.
    const items = [...state.presets.values()].filter(preset =>
      preset?.id === "h3-fl2va-group" || preset?.family !== "fl2va"
    );
    const current = selectedPreset()?.id;
    const grouped = { video: [], image: [], other: [] };
    for (const preset of items) {
      const kind = outputKind(preset);
      grouped[kind === "video" ? "video" : kind === "image" ? "image" : "other"].push(preset);
    }
    const section = (key, label) => grouped[key].length ? `<div class="sheet-section"><span class="sheet-label">${label}</span>${grouped[key].map(preset => {
      const ui = normalizePresetUi(preset);
      return `<button class="workflow-choice${preset.id === current ? " current" : ""}" type="button" data-pick-workflow="${escapeHtml(preset.id)}"><span><strong>${escapeHtml(preset.name)}</strong><small>${escapeHtml(ui.description)}</small></span>${preset.id === current ? icon("check") : icon("chevron")}</button>`;
    }).join("")}</div>` : "";
    openSheet("选择工作流", `${section("video", "视频")}${section("image", "图片")}${section("other", "其他")}<div class="sheet-section"><button class="workflow-choice" type="button" data-manage-workflows><span><strong>管理工作流</strong><small>重命名、启用、禁用或导入</small></span>${icon("settings")}</button></div>`);
    $$('[data-pick-workflow]', $("#sheet-body")).forEach(button => button.addEventListener("click", () => {
      $("#preset-select").value = button.dataset.pickWorkflow;
      $("#preset-select").dispatchEvent(new Event("change", { bubbles: true }));
      closeSheet();
    }));
    $("[data-manage-workflows]", $("#sheet-body"))?.addEventListener("click", () => { closeSheet(); setView("workflows"); showWorkflowManager(); });
  }

  function sourceGeneric(id) { return $(`[data-generic-binding="${id}"]`, $("#job-form")); }

  function alignNumber(value, spec) {
    const step = Number(spec?.step) || 64;
    let next = Math.round(Number(value) / step) * step;
    if (spec?.minimum != null) next = Math.max(next, Number(spec.minimum));
    if (spec?.maximum != null) next = Math.min(next, Number(spec.maximum));
    return Math.max(step, next);
  }

  function applyRatioToGeneric(ratio) {
    const preset = selectedPreset();
    const width = sourceGeneric("width"), height = sourceGeneric("height");
    if (!preset || !width || !height) return;
    const [rw, rh] = ratio.split(":").map(Number);
    const area = Math.max(1, Number(width.value) || 1024) * Math.max(1, Number(height.value) || 1024);
    const nextW = Math.sqrt(area * rw / rh);
    const nextH = nextW * rh / rw;
    width.value = alignNumber(nextW, preset.parameters?.width);
    height.value = alignNumber(nextH, preset.parameters?.height);
    width.dispatchEvent(new Event("input", { bubbles: true }));
    height.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function openGenerationSettings() {
    const preset = selectedPreset();
    if (!preset) return;
    const ui = normalizePresetUi(preset);
    if (ui.family === "fl2va" || ui.family === "ref2va") {
      const aspect = $("select[name=aspect_ratio]");
      const duration = $("input[name=duration_seconds]");
      const mp = $("#megapixels-value");
      const aspectOptions = [...aspect.options].filter(option => !option.disabled && !option.hidden).map(option => `<button type="button" data-sheet-aspect="${escapeHtml(option.value)}" class="${option.value === aspect.value ? "selected" : ""}">${escapeHtml(aspectLabel(option.value))}</button>`).join("");
      const mpValues = ["0.2","0.4","0.6","0.8","0.9","1.0"];
      openSheet("生成设置", `<div class="sheet-section"><span class="sheet-label">画幅</span><div class="aspect-options">${aspectOptions}</div></div><div class="sheet-section"><span class="sheet-label">时长</span><div class="sheet-range"><span>5</span><input id="sheet-duration" type="range" min="5" max="15" step="1" value="${escapeHtml(duration.value)}"><output id="sheet-duration-output">${escapeHtml(duration.value)} 秒</output></div></div><div class="sheet-section"><span class="sheet-label">分辨率</span><div class="mp-options">${mpValues.map(value => `<button type="button" data-sheet-mp="${value}" class="${value === String(mp.value) ? "selected" : ""}">${value}</button>`).join("")}</div></div><button id="sheet-done" class="primary-button" type="button"><span>完成</span>${icon("check")}</button>`);
      $$('[data-sheet-aspect]', $("#sheet-body")).forEach(button => button.addEventListener("click", () => { aspect.value = button.dataset.sheetAspect; aspect.dispatchEvent(new Event("change", { bubbles: true })); $$('[data-sheet-aspect]', $("#sheet-body")).forEach(item => item.classList.toggle("selected", item === button)); updateSettingsSummary(); }));
      const durationSheet = $("#sheet-duration");
      durationSheet.addEventListener("input", () => { duration.value = durationSheet.value; duration.dispatchEvent(new Event("input", { bubbles: true })); $("#sheet-duration-output").textContent = `${durationSheet.value} 秒`; updateSettingsSummary(); });
      $$('[data-sheet-mp]', $("#sheet-body")).forEach(button => button.addEventListener("click", () => { const sourceButton = $(`[data-megapixels="${CSS.escape(button.dataset.sheetMp)}"]`, $("#h3-settings-source")); if (sourceButton) sourceButton.click(); else mp.value = button.dataset.sheetMp; $$('[data-sheet-mp]', $("#sheet-body")).forEach(item => item.classList.toggle("selected", item === button)); updateSettingsSummary(); }));
      $("#sheet-done").addEventListener("click", closeSheet);
      return;
    }

    const width = sourceGeneric("width"), height = sourceGeneric("height"), batch = sourceGeneric("batch_size");
    const ratios = ["1:1","3:4","4:3","9:16","16:9"];
    const currentRatio = width && height ? ratioLabel(width.value, height.value) : "";
    const dimensions = width && height ? `<div class="sheet-section"><span class="sheet-label">画幅</span><div class="aspect-options">${ratios.map(value => `<button type="button" data-generic-ratio="${value}" class="${value === currentRatio ? "selected" : ""}">${value}</button>`).join("")}</div></div><div class="sheet-section"><span class="sheet-label">尺寸</span><div class="dimension-grid"><label class="field"><span>宽度</span><input id="sheet-width" type="number" value="${escapeHtml(width.value)}"></label><label class="field"><span>高度</span><input id="sheet-height" type="number" value="${escapeHtml(height.value)}"></label></div></div>` : "";
    const batchHtml = batch ? `<div class="sheet-section"><span class="sheet-label">生成数量</span><div class="stepper"><button id="batch-minus" type="button">−</button><output id="batch-output">${escapeHtml(batch.value)}</output><button id="batch-plus" type="button">+</button></div></div>` : "";
    openSheet("生成设置", `${dimensions}${batchHtml}<button id="sheet-done" class="primary-button" type="button"><span>完成</span>${icon("check")}</button>`);
    $$('[data-generic-ratio]', $("#sheet-body")).forEach(button => button.addEventListener("click", () => { applyRatioToGeneric(button.dataset.genericRatio); $("#sheet-width").value = width.value; $("#sheet-height").value = height.value; $$('[data-generic-ratio]', $("#sheet-body")).forEach(item => item.classList.toggle("selected", item === button)); updateSettingsSummary(); }));
    if (width && height) {
      $("#sheet-width").addEventListener("input", event => { width.value = alignNumber(event.target.value, preset.parameters?.width); width.dispatchEvent(new Event("input", { bubbles: true })); updateSettingsSummary(); });
      $("#sheet-height").addEventListener("input", event => { height.value = alignNumber(event.target.value, preset.parameters?.height); height.dispatchEvent(new Event("input", { bubbles: true })); updateSettingsSummary(); });
    }
    if (batch) {
      const changeBatch = delta => { const spec = preset.parameters?.batch_size || {}; let next = Number(batch.value || 1) + delta; if (spec.minimum != null) next = Math.max(next, Number(spec.minimum)); if (spec.maximum != null) next = Math.min(next, Number(spec.maximum)); batch.value = String(next); batch.dispatchEvent(new Event("input", { bubbles: true })); $("#batch-output").textContent = String(next); updateSettingsSummary(); };
      $("#batch-minus").addEventListener("click", () => changeBatch(-1));
      $("#batch-plus").addEventListener("click", () => changeBatch(1));
    }
    $("#sheet-done").addEventListener("click", closeSheet);
  }

  function openReferencePicker() {
    openSheet("添加参考", `<div class="sheet-action-row"><button class="sheet-action" type="button" data-reference-kind="image">图片</button><button class="sheet-action" type="button" data-reference-kind="video">视频</button><button class="sheet-action" type="button" data-reference-kind="audio">音频</button></div>`);
    $$('[data-reference-kind]', $("#sheet-body")).forEach(button => button.addEventListener("click", () => { const id = { image: "ref-images", video: "ref-videos", audio: "ref-audios" }[button.dataset.referenceKind]; closeSheet(); $("#" + id)?.click(); }));
  }

  function taskPrompt(job) {
    const values = job.input_values || {};
    return job.prompt || values.positive_prompt || values.prompt || Object.entries(values).find(([key, value]) => /prompt|text/i.test(key) && typeof value === "string")?.[1] || "";
  }

  function taskMeta(job, preset) {
    const ui = normalizePresetUi(preset);
    const values = job.input_values || {};
    if (ui.family === "fl2va" || ui.family === "ref2va") return [aspectLabel(job.aspect_ratio), `${job.duration_seconds} 秒`, `${job.megapixels} MP`].filter(Boolean);
    const meta = [];
    if (values.width && values.height) meta.push(ratioLabel(values.width, values.height), `${values.width}×${values.height}`);
    if (values.batch_size != null) meta.push(`${values.batch_size} 张`);
    return meta;
  }

  jobCard = function(job) {
    const preset = state.presets.get(job.preset_id);
    const ui = normalizePresetUi(preset);
    const displayName = workflowDisplayName(job.preset_id, job.preset_name || job.preset_id);
    const active = ["submitting", "queued", "running"].includes(job.status);
    const terminal = ["failed", "cancelled", "interrupted", "succeeded", "output_missing"].includes(job.status);
    const progress = Math.max(0, Math.min(100, Number(job.progress_percent ?? (job.status === "succeeded" ? 100 : 0)) || 0));
    const queueText = job.status === "queued" && job.queue_position ? ` · 第 ${job.queue_position} 位` : "";
    const preview = job.status === "succeeded" && ui.outputKind === "image" ? `<button class="artifact-preview" type="button" data-artifact-preview="${escapeHtml(job.id)}" data-open-results="${escapeHtml(job.id)}"><span class="artifact-placeholder">读取图片结果…</span></button>` : job.has_video ? `<button class="job-preview" data-action="play" data-id="${escapeHtml(job.id)}" type="button" aria-label="播放视频"><video muted playsinline preload="none"></video><span>▶</span></button>` : "";
    const actions = [];
    if (active) actions.push(`<button data-action="cancel" data-id="${escapeHtml(job.id)}">取消</button>`);
    if (terminal) actions.push(`<button class="primary-action" data-action="retry" data-id="${escapeHtml(job.id)}">再次生成</button>`);
    if (job.status === "succeeded" && ui.outputKind === "image") actions.push(`<button data-open-results="${escapeHtml(job.id)}">查看结果</button>`);
    if (job.has_video) actions.push(`<a href="/api/jobs/${encodeURIComponent(job.id)}/video?download=1">下载</a>`);
    if (terminal) actions.push(`<button class="more-action" data-task-details="${escapeHtml(job.id)}" aria-label="任务详情">${icon("more")}</button>`);
    return `<article class="job-card" data-job="${escapeHtml(job.id)}"><div class="job-top"><div><h3>${escapeHtml(displayName)}</h3><span class="job-time">${formatDate(job.created_at)} · ${formatDuration(job.elapsed_seconds)}</span></div><span class="job-status ${escapeHtml(job.status)}">${statusLabels[job.status] || escapeHtml(job.status)}</span></div>${taskPrompt(job) ? `<p class="job-prompt">${escapeHtml(taskPrompt(job))}</p>` : ""}<div class="job-meta">${taskMeta(job, preset).map(item => `<span>${escapeHtml(item)}</span>`).join("")}</div>${active ? `<div class="job-progress"><div><span>${escapeHtml(job.stage || "等待状态")}${queueText}</span><b>${progress}%</b></div><progress class="progress-track" max="100" value="${progress}"></progress></div>` : ""}${job.error_summary ? `<p class="job-error">${escapeHtml(job.error_summary)}</p>` : ""}${preview}<div class="job-actions">${actions.join("")}</div></article>`;
  };

  async function fetchOutputArtifacts(jobId) {
    const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/artifacts`);
    if (!response.ok) throw new Error("结果列表加载失败");
    const data = await response.json();
    return data.items.filter(item => item.direction === "output");
  }

  async function hydrateArtifactPreviews() {
    for (const preview of $$('[data-artifact-preview]')) {
      const id = preview.dataset.artifactPreview;
      if (!id || state.artifactHydrated.has(id)) continue;
      state.artifactHydrated.add(id);
      try {
        const outputs = (await fetchOutputArtifacts(id)).filter(item => item.kind === "image");
        if (!outputs.length) { preview.innerHTML = `<span class="artifact-placeholder">结果文件仍在写入</span>`; continue; }
        const shown = outputs.slice(0, 4);
        preview.classList.add(shown.length === 1 ? "one" : shown.length === 2 ? "two" : "many");
        preview.innerHTML = shown.map((item, index) => `<span class="artifact-preview-item"><img loading="lazy" src="/api/jobs/${encodeURIComponent(id)}/artifacts/${item.id}" alt="生成图片 ${index + 1}">${index === 3 && outputs.length > 4 ? `<span class="artifact-more">+${outputs.length - 4}</span>` : ""}</span>`).join("");
      } catch (_) {
        state.artifactHydrated.delete(id);
        preview.innerHTML = `<span class="artifact-placeholder">点击查看结果</span>`;
      }
    }
  }

  async function openArtifactViewer(jobId) {
    const modal = $("#artifact-modal");
    const title = $("#artifact-title");
    const body = $("#artifact-body");
    const job = state.jobs.get(jobId);
    title.textContent = workflowDisplayName(job?.preset_id, "生成结果");
    body.innerHTML = `<div class="artifact-placeholder">正在读取结果…</div>`;
    modal.classList.remove("hidden");
    document.body.classList.add("viewer-open");
    try {
      const outputs = await fetchOutputArtifacts(jobId);
      if (!outputs.length) { body.innerHTML = `<div class="empty-state"><h3>暂未找到结果</h3><p>ComfyUI 可能仍在写入文件。</p></div>`; return; }
      const gallery = outputs.every(item => item.kind === "image") ? " gallery" : "";
      body.innerHTML = `<div class="artifact-grid${gallery}">${outputs.map((item, index) => {
        const src = `/api/jobs/${encodeURIComponent(jobId)}/artifacts/${item.id}`;
        const download = `${src}?download=1`;
        if (item.kind === "image") return `<figure class="artifact-item"><img src="${src}" alt="生成结果 ${index + 1}"><figcaption><span>${index + 1} / ${outputs.length}</span><a href="${download}">下载</a></figcaption></figure>`;
        if (item.kind === "video") return `<figure class="artifact-item"><video controls playsinline preload="metadata" src="${src}"></video><figcaption><span>视频结果</span><a href="${download}">下载</a></figcaption></figure>`;
        if (item.kind === "audio") return `<figure class="artifact-item"><audio controls src="${src}"></audio><figcaption><span>音频结果</span><a href="${download}">下载</a></figcaption></figure>`;
        return `<div class="artifact-file"><span>${escapeHtml(item.original_name || `文件 ${index + 1}`)}</span><a href="${download}">下载</a></div>`;
      }).join("")}</div>`;
    } catch (error) { body.innerHTML = `<p class="form-message error">${escapeHtml(error.message)}</p>`; }
  }

  function closeArtifactViewer() {
    const modal = $("#artifact-modal");
    $$('video, audio', modal).forEach(media => { media.pause(); media.removeAttribute("src"); });
    modal.classList.add("hidden");
    document.body.classList.remove("viewer-open");
  }

  function openTaskDetails(jobId) {
    const job = state.jobs.get(jobId);
    if (!job) return;
    const rows = [
      ["工作流", workflowDisplayName(job.preset_id, job.preset_name || job.preset_id)],
      ["Workflow Revision", job.workflow_revision ?? "—"],
      ["状态", statusLabels[job.status] || job.status],
      ["耗时", formatDuration(job.elapsed_seconds)],
      ["Sampler", job.sampler], ["Scheduler", job.scheduler], ["Steps", job.steps], ["Seed", job.seed],
    ].filter(([, value]) => value != null && value !== "custom" && value !== 0 && value !== "0");
    const inputRows = Object.entries(job.input_values || {}).map(([key, value]) => `<div class="settings-row static"><span><strong>${escapeHtml(key)}</strong><small>${escapeHtml(typeof value === "object" ? JSON.stringify(value) : value)}</small></span></div>`).join("");
    openSheet("任务详情", `<div class="settings-list">${rows.map(([label, value]) => `<div class="settings-row static"><span><strong>${escapeHtml(label)}</strong><small>${escapeHtml(value)}</small></span></div>`).join("")}</div>${inputRows ? `<div class="sheet-section" style="margin-top:18px"><span class="sheet-label">输入参数</span><div class="settings-list">${inputRows}</div></div>` : ""}<button id="detail-hide-job" class="secondary-wide" type="button">移出历史</button>`);
    $("#detail-hide-job")?.addEventListener("click", async () => { if (!window.confirm("确认将这个任务移出历史？本地素材和结果文件会保留。")) return; try { await apiAction(`/api/jobs/${encodeURIComponent(jobId)}`, { method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ confirm: true }) }); removeJob(jobId); closeSheet(); } catch (error) { window.alert(error.message); } });
  }

  function workflowFamily(id) { return state.presets.get(id)?.family || state.workflowItems.get(id)?.manifest?.family || "generic"; }

  async function retryGeneric(job) {
    const form = $("#job-form");
    const draft = await apiAction(`/api/jobs/${encodeURIComponent(job.id)}/retry`, { method: "POST" });
    form.reset();
    Object.values(state.mediaFiles).flat().forEach(entry => { if (entry?.url) URL.revokeObjectURL(entry.url); });
    state.mediaFiles = { image: [], video: [], audio: [] };
    state.retryRoles = draft.input_roles || [];
    state.retryKeepRoles = [...state.retryRoles];
    $("#retry-source-id").value = draft.retry_source_id;
    applyPreset(draft.preset_id, draft);
    $("#retry-draft span").textContent = state.retryRoles.length ? "已载入上次参数和参考素材" : "已载入上次任务参数";
    $("#retry-draft").classList.remove("hidden");
    setView("generate");
  }

  function workflowTypeText(item) {
    const manifest = item.manifest || {};
    const outputs = manifest.output_bindings || [];
    const kind = (outputs.find(entry => entry.primary) || outputs[0] || {}).kind;
    if (manifest.family === "fl2va") return "视频 · 首尾帧生成";
    if (manifest.family === "ref2va") return "视频 · 参考生成";
    return kind === "image" ? "图片 · 自定义" : kind === "video" ? "视频 · 自定义" : "自定义工作流";
  }

  loadWorkflows = async function() {
    const items = await fetchWorkflowItems();
    const list = $("#workflow-list");
    if (!list) return;
    const sorted = [...items].sort((a, b) => workflowTypeText(a).localeCompare(workflowTypeText(b)) || a.name.localeCompare(b.name));
    list.innerHTML = sorted.map(item => {
      const builtin = Boolean(item.builtin) || ["fl2va", "ref2va"].includes(item.manifest?.family);
      const enabled = item.status === "enabled";
      return `<article class="workflow-item"><div class="workflow-item-main"><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(workflowTypeText(item))} · r${item.revision}</small></div><button class="toggle-button${enabled ? " on" : ""}" type="button" data-workflow-action="${enabled ? "disable" : "enable"}" data-id="${escapeHtml(item.id)}" aria-label="${enabled ? "禁用" : "启用"} ${escapeHtml(item.name)}"></button><div class="workflow-item-actions"><button type="button" data-workflow-action="rename" data-id="${escapeHtml(item.id)}">重命名</button><button type="button" data-workflow-action="test" data-id="${escapeHtml(item.id)}">测试</button>${builtin ? "" : `<button type="button" data-workflow-action="edit" data-id="${escapeHtml(item.id)}">高级映射</button><button type="button" data-workflow-action="copy" data-id="${escapeHtml(item.id)}">复制</button><a href="/api/workflows/${encodeURIComponent(item.id)}/export?download=1">导出</a><button type="button" data-workflow-action="delete" data-id="${escapeHtml(item.id)}">删除</button>`}</div></article>`;
    }).join("") || `<div class="empty-state"><h3>还没有工作流</h3></div>`;
  };

  function schemaOptions(result, binding) {
    const node = result.nodes.find(item => item.id === String(binding.node));
    if (!node) return {};
    const raw = result.object_info?.[node.class_type];
    const info = raw?.[node.class_type] || raw;
    for (const group of Object.values(info?.input || {})) {
      const spec = group?.[binding.input];
      if (!Array.isArray(spec) || !spec[1] || typeof spec[1] !== "object") continue;
      const options = spec[1];
      return { ...(options.min != null ? { minimum: options.min } : {}), ...(options.max != null ? { maximum: options.max } : {}), ...(options.step != null ? { step: options.step } : {}) };
    }
    return {};
  }

  function extraLiteralInputs(result, knownTargets) {
    const existing = state.workflowEditingDetail?.definition?.manifest?.parameters || {};
    const existingTargets = new Set(Object.values(existing).map(spec => `${spec.node}:${spec.input}`));
    return result.nodes.flatMap(node => node.inputs.filter(input => {
      const target = `${node.id}:${input.name}`;
      if (knownTargets.has(target) || input.connected || input.suggested_control === "unsupported" || input.name === "filename_prefix") return false;
      if (/^Load(Image|Video|Audio)$/i.test(node.class_type)) return false;
      if (/(model|ckpt|lora|vae|file|name)/i.test(input.name)) return false;
      return true;
    }).map(input => ({ ...input, node: node.id, classType: node.class_type, checked: existingTargets.has(`${node.id}:${input.name}`) })));
  }

  renderWorkflowInspection = function(result) {
    state.workflowInspection = result;
    const root = $("#workflow-inspection");
    const basic = result.basic_bindings || { parameters: [], media: { reference_image: [] }, outputs: result.output_candidates || [], warnings: [] };
    const knownTargets = new Set(basic.parameters.map(item => `${item.node}:${item.input}`));
    const imageCandidates = basic.media?.reference_image || [];
    const outputs = basic.outputs || result.output_candidates || [];
    const extras = extraLiteralInputs(result, knownTargets);
    const detected = basic.parameters.map(item => `<div class="semantic-detected"><span>${icon("check")}</span><div><strong>${escapeHtml(item.label || LABELS[item.semantic] || item.semantic)}</strong><small>已自动识别</small></div></div>`).join("");
    const media = imageCandidates.length === 1 ? `<div class="semantic-detected"><span>${icon("check")}</span><div><strong>参考图 · 可选</strong><small>${escapeHtml(imageCandidates[0].class_type || "LoadImage")}</small></div></div><input id="semantic-reference-image" type="hidden" value="0">` : imageCandidates.length > 1 ? `<label class="field"><span>参考图输入 <small>检测到多个候选</small></span><select id="semantic-reference-image">${imageCandidates.map((item, index) => `<option value="${index}">${escapeHtml(item.class_type || "LoadImage")} · ${escapeHtml(item.default || `图片 ${index + 1}`)}</option>`).join("")}</select></label>` : "";
    const output = outputs.length === 1 ? `<div class="semantic-detected"><span>${icon("check")}</span><div><strong>${outputs[0].kind === "image" ? "图片" : outputs[0].kind === "video" ? "视频" : "文件"}输出</strong><small>${escapeHtml(outputs[0].class_type)}</small></div></div><input id="semantic-output" type="hidden" value="0">` : outputs.length > 1 ? `<label class="field"><span>主要输出 <small>检测到多个候选</small></span><select id="semantic-output">${outputs.map((item, index) => `<option value="${index}">${escapeHtml(item.class_type)} · ${escapeHtml(item.kind)}</option>`).join("")}</select></label>` : `<p class="form-message error">未检测到输出节点，请先在 ComfyUI 中加入 SaveImage 或 SaveVideo。</p>`;
    root.innerHTML = `<div class="semantic-summary">${detected || `<div class="semantic-detected muted"><span>!</span><div><strong>未识别基础输入</strong><small>可使用高级映射补充</small></div></div>`}${media}${output}${(basic.warnings || []).length ? `<ul class="semantic-warnings">${basic.warnings.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul>` : ""}</div>${extras.length ? `<details class="semantic-advanced"><summary>高级 · 手动节点映射</summary>${extras.map(input => `<label class="workflow-binding"><input type="checkbox" data-workflow-extra data-node="${escapeHtml(input.node)}" data-input="${escapeHtml(input.name)}" data-current="${escapeHtml(JSON.stringify(input.value))}" data-control="${escapeHtml(input.suggested_control)}"${input.checked ? " checked" : ""}><span>${escapeHtml(input.classType)} · ${escapeHtml(input.name)}</span><small>${escapeHtml(input.value)}</small></label>`).join("")}</details>` : ""}`;
    $("#save-workflow").disabled = outputs.length === 0;
  };

  function slugify(value) {
    const slug = String(value || "").toLowerCase().replace(/\.json$/i, "").replace(/[^a-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 64);
    return slug.length >= 2 ? slug : `workflow-${Date.now().toString(36)}`;
  }

  function parameterFromBinding(result, binding) {
    const type = binding.type || (Number.isInteger(binding.default) ? "integer" : typeof binding.default === "number" ? "number" : "string");
    return { id: binding.semantic, node: binding.node, input: binding.input, type, default: binding.default, ...schemaOptions(result, binding), ui: { label: binding.label || LABELS[binding.semantic] || binding.semantic, control: binding.control || (type === "string" ? "text" : "number"), semantic: binding.semantic } };
  }

  async function saveSemanticWorkflow(event) {
    event.preventDefault(); event.stopImmediatePropagation();
    const message = $("#workflow-message"), result = state.workflowInspection;
    if (!state.workflowDraft || !result) return;
    const name = $("#workflow-name").value.trim();
    if (!name) { message.className = "form-message error"; message.textContent = "请填写显示名称"; return; }
    let workflowId = $("#workflow-id").value.trim().toLowerCase();
    if (!/^[a-z0-9][a-z0-9._-]{1,63}$/.test(workflowId)) { workflowId = slugify(workflowId || name); $("#workflow-id").value = workflowId; }
    const basic = result.basic_bindings || { parameters: [], media: { reference_image: [] }, outputs: result.output_candidates || [] };
    const parameters = basic.parameters.map(item => parameterFromBinding(result, item));
    $$('[data-workflow-extra]:checked').forEach(input => {
      const current = JSON.parse(input.dataset.current);
      const type = typeof current === "boolean" ? "boolean" : Number.isInteger(current) ? "integer" : typeof current === "number" ? "number" : "string";
      const id = `extra_${input.dataset.node}_${input.dataset.input}`.toLowerCase().replace(/[^a-z0-9._-]+/g, "-").slice(0, 64);
      parameters.push({ id, node: input.dataset.node, input: input.dataset.input, type, default: current, ui: { label: input.dataset.input, control: input.dataset.control || "text", semantic: "advanced" } });
    });
    const imageCandidates = basic.media?.reference_image || [];
    const image = imageCandidates[Number($("#semantic-reference-image")?.value || 0)];
    const media = image ? { type: "slots", slots: { image_0: { node: image.node, input: image.input, kind: "image", ui: { label: "参考图", optional: true } } } } : { type: "none" };
    const outputs = basic.outputs || result.output_candidates || [];
    const selectedOutput = outputs[Number($("#semantic-output")?.value || 0)];
    if (!selectedOutput) { message.className = "form-message error"; message.textContent = "请确认主要输出"; return; }
    const output = { id: "primary", node: selectedOutput.node, kind: selectedOutput.kind, history_keys: selectedOutput.kind === "image" ? ["images"] : selectedOutput.kind === "video" ? ["videos","video","files","images"] : ["files"], primary: true };
    const button = $("#save-workflow"); button.disabled = true;
    try {
      const item = await apiAction("/api/workflows", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ workflow: state.workflowDraft, config: { id: workflowId, name, parameters, media, outputs: [output] } }) });
      await apiAction(`/api/workflows/${encodeURIComponent(item.id)}/status`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: "enabled" }) });
      message.className = "form-message"; message.textContent = `${item.name} 已保存并启用`;
      state.workflowEditingDetail = null;
      await Promise.all([loadWorkflows(), loadPresets()]);
    } catch (error) { message.className = "form-message error"; message.textContent = error.message; }
    finally { button.disabled = false; }
  }

  function showSettingsHome() { $("#settings-home").classList.remove("hidden"); $("#workflow-manager").classList.add("hidden"); }
  function showWorkflowManager() { $("#settings-home").classList.add("hidden"); $("#workflow-manager").classList.remove("hidden"); loadWorkflows().catch(() => {}); }

  function installArtifactModal() {
    if ($("#artifact-modal")) return;
    const modal = document.createElement("div");
    modal.id = "artifact-modal"; modal.className = "viewer-modal hidden"; modal.setAttribute("role", "dialog"); modal.setAttribute("aria-modal", "true");
    modal.innerHTML = `<div class="viewer-dialog"><div class="viewer-head"><strong id="artifact-title">生成结果</strong><button id="artifact-close" class="icon-button small" type="button" aria-label="关闭结果">${icon("close")}</button></div><div id="artifact-body"></div></div>`;
    document.body.append(modal);
    $("#artifact-close").addEventListener("click", closeArtifactViewer);
    modal.addEventListener("click", event => { if (event.target === modal) closeArtifactViewer(); });
  }

  function installPromptFocus() {
    const form = $("#job-form");
    form.addEventListener("focusin", event => { if (event.target.matches("textarea")) document.body.classList.add("prompt-focused"); });
    form.addEventListener("focusout", event => { if (!event.target.matches("textarea")) return; window.setTimeout(() => { if (!form.contains(document.activeElement) || !document.activeElement.matches("textarea")) document.body.classList.remove("prompt-focused"); }, 120); });
    window.visualViewport?.addEventListener("resize", () => { document.documentElement.style.setProperty("--visual-height", `${window.visualViewport.height}px`); });
  }

  document.addEventListener("DOMContentLoaded", () => {
    $("#nav-workflows")?.addEventListener("click", () => { closeSheet(); setView("workflows"); showSettingsHome(); });
    $("#settings-close")?.addEventListener("click", () => setView("generate"));
    $("#open-workflow-manager")?.addEventListener("click", showWorkflowManager);
    $("#workflow-manager-back")?.addEventListener("click", showSettingsHome);
    $("#open-workflow-importer")?.addEventListener("click", () => $("#workflow-importer").classList.remove("hidden"));
    $("#close-workflow-importer")?.addEventListener("click", () => $("#workflow-importer").classList.add("hidden"));
    $("#workflow-picker-button")?.addEventListener("click", openWorkflowPicker);
    $("#open-generation-settings")?.addEventListener("click", openGenerationSettings);
    $("#add-reference")?.addEventListener("click", openReferencePicker);
    $("#sheet-close")?.addEventListener("click", closeSheet);
    $("#sheet-backdrop")?.addEventListener("click", event => { if (event.target.id === "sheet-backdrop") closeSheet(); });
    document.addEventListener("keydown", event => { if (event.key === "Escape") { if (!$("#sheet-backdrop").classList.contains("hidden")) closeSheet(); if (!$("#artifact-modal")?.classList.contains("hidden")) closeArtifactViewer(); } });

    $("#job-form")?.addEventListener("input", updateSettingsSummary);
    $("#job-form")?.addEventListener("change", updateSettingsSummary);

    const workflowJson = $("#workflow-json");
    workflowJson?.addEventListener("change", event => {
      state.workflowEditingDetail = null;
      const file = event.target.files?.[0]; if (!file) return;
      if (!$("#workflow-name").value.trim()) $("#workflow-name").value = file.name.replace(/\.json$/i, "").replace(/[_-]+/g, " ");
      if (!$("#workflow-id").value.trim()) $("#workflow-id").value = slugify(file.name);
    }, true);
    $("#save-workflow")?.addEventListener("click", saveSemanticWorkflow, true);

    $("#workflow-list")?.addEventListener("click", async event => {
      const button = event.target.closest("[data-workflow-action]"); if (!button) return;
      const { workflowAction: action, id } = button.dataset;
      if (action === "rename") {
        event.preventDefault(); event.stopImmediatePropagation();
        const item = state.workflowItems.get(id); if (!item) return;
        const name = window.prompt("前端显示名称", item.name); if (!name?.trim() || name.trim() === item.name) return;
        button.disabled = true;
        try { await apiAction(`/api/workflows/${encodeURIComponent(id)}/copy`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id, name: name.trim() }) }); await apiAction(`/api/workflows/${encodeURIComponent(id)}/status`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: item.status }) }); await Promise.all([loadWorkflows(), loadPresets()]); }
        catch (error) { window.alert(error.message); } finally { button.disabled = false; }
        return;
      }
      if (action === "edit") {
        event.preventDefault(); event.stopImmediatePropagation();
        try { const detail = await apiAction(`/api/workflows/${encodeURIComponent(id)}`); state.workflowEditingDetail = detail; state.workflowDraft = detail.definition.workflow; $("#workflow-id").value = detail.id; $("#workflow-name").value = detail.name; const inspection = await apiAction("/api/workflows/inspect", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(state.workflowDraft) }); renderWorkflowInspection(inspection); $("#workflow-importer").classList.remove("hidden"); $("#workflow-message").textContent = `正在编辑 ${detail.name}；保存会创建新 revision。`; $("#workflow-importer").scrollIntoView({ behavior: "smooth", block: "start" }); }
        catch (error) { window.alert(error.message); }
      }
    }, true);

    $("#jobs-list")?.addEventListener("click", async event => {
      const result = event.target.closest("[data-open-results]");
      if (result) { event.preventDefault(); event.stopImmediatePropagation(); await openArtifactViewer(result.dataset.openResults); return; }
      const details = event.target.closest("[data-task-details]");
      if (details) { event.preventDefault(); event.stopImmediatePropagation(); openTaskDetails(details.dataset.taskDetails); return; }
      const retry = event.target.closest('[data-action="retry"]');
      if (!retry) return;
      const job = state.jobs.get(retry.dataset.id);
      if (!job || workflowFamily(job.preset_id) !== "generic") return;
      event.preventDefault(); event.stopImmediatePropagation(); retry.disabled = true;
      try { await retryGeneric(job); } catch (error) { window.alert(error.message); } finally { retry.disabled = false; }
    }, true);

    installArtifactModal();
    installPromptFocus();
    const observer = new MutationObserver(() => hydrateArtifactPreviews());
    observer.observe($("#jobs-list"), { childList: true, subtree: true });
    window.setTimeout(() => { updateSettingsSummary(); hydrateArtifactPreviews(); }, 0);
  });
})();
