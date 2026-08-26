(() => {
  const baseApplyPreset = applyPreset;
  const baseJobCard = jobCard;
  const baseLoadPresets = loadPresets;

  state.workflowItems = new Map();
  state.workflowInspection = null;
  state.workflowEditingDetail = null;

  const BASIC_LABELS = {
    positive_prompt: "正面提示词",
    negative_prompt: "负面提示词",
    width: "宽度",
    height: "高度",
    batch_size: "批次数量",
  };

  function workflowFamily(id) {
    return state.workflowItems.get(id)?.manifest?.family || state.presets.get(id)?.family || "generic";
  }

  function workflowDisplayName(id, fallback = id) {
    return state.workflowItems.get(id)?.name || state.presets.get(id)?.name || fallback;
  }

  function builtinLike(item) {
    return Boolean(item?.builtin) || ["fl2va", "ref2va"].includes(item?.manifest?.family);
  }

  function mergedOverrides(overrides) {
    if (overrides?.values && typeof overrides.values === "object") return { ...overrides, ...overrides.values };
    return overrides || {};
  }

  function toggleGenerationSections(generic) {
    const prompt = $("#job-form > .prompt-field");
    const h3Grid = $$("#job-form > .parameter-grid").find(node => node.id !== "generic-parameters");
    const advanced = $("#job-form > .advanced");
    prompt?.classList.toggle("hidden", generic);
    h3Grid?.classList.toggle("hidden", generic);
    advanced?.classList.toggle("hidden", generic);
    $("#load-warning")?.classList.toggle("hidden", generic || $("#load-warning").classList.contains("hidden"));
    $("#generic-parameters")?.classList.toggle("hidden", !generic);
  }

  function numberAttrs(spec) {
    return `${spec.minimum != null ? ` min="${escapeHtml(spec.minimum)}"` : ""}${spec.maximum != null ? ` max="${escapeHtml(spec.maximum)}"` : ""}${spec.step != null ? ` step="${escapeHtml(spec.step)}"` : ""}`;
  }

  function renderSimpleGenericField(id, spec, value, extraClass = "") {
    const label = escapeHtml(spec.ui?.label || BASIC_LABELS[id] || id);
    if (spec.type === "boolean") {
      return `<label class="field ${extraClass}"><span>${label}</span><input type="checkbox" name="generic_${escapeHtml(id)}" data-generic-binding="${escapeHtml(id)}" data-value-type="boolean"${value ? " checked" : ""}></label>`;
    }
    if (spec.type === "enum") {
      return `<label class="field ${extraClass}"><span>${label}</span><select name="generic_${escapeHtml(id)}" data-generic-binding="${escapeHtml(id)}" data-value-type="enum">${optionKeys(spec).map(option => `<option value="${escapeHtml(option)}"${String(option) === String(value) ? " selected" : ""}>${escapeHtml(option)}</option>`).join("")}</select></label>`;
    }
    const type = ["integer", "number"].includes(spec.type) ? "number" : "text";
    return `<label class="field ${extraClass}"><span>${label}</span><input type="${type}" name="generic_${escapeHtml(id)}" data-generic-binding="${escapeHtml(id)}" data-value-type="${escapeHtml(spec.type)}" value="${escapeHtml(value ?? "")}"${type === "number" ? numberAttrs(spec) : ""}></label>`;
  }

  function renderGenericForm(preset, overrides = {}) {
    const container = $("#generic-parameters");
    if (!container) return;
    const parameters = preset.parameters || {};
    const values = mergedOverrides(overrides);
    const valueFor = id => values[id] ?? parameters[id]?.default ?? "";
    let html = `<div class="generic-intro wide"><strong>${escapeHtml(preset.name)}</strong><span>${escapeHtml(preset.description || "仅显示这个工作流需要的基础输入，其他参数沿用 ComfyUI 工作流原值。")}</span></div>`;

    for (const id of ["positive_prompt", "negative_prompt"]) {
      const spec = parameters[id];
      if (!spec) continue;
      const label = escapeHtml(spec.ui?.label || BASIC_LABELS[id]);
      const rows = id === "positive_prompt" ? 6 : 4;
      html += `<label class="field wide semantic-prompt"><span>${label}</span><textarea name="generic_${id}" rows="${rows}" data-generic-binding="${id}" data-value-type="string" placeholder="${id === "positive_prompt" ? "描述想生成的内容……" : "不希望出现的内容，可留空……"}">${escapeHtml(valueFor(id))}</textarea></label>`;
    }

    if (parameters.width && parameters.height) {
      html += `<div class="wide semantic-resolution"><div class="semantic-section-title"><strong>画幅与分辨率</strong><small>默认沿用工作流尺寸，可直接修改或快速切换画幅</small></div><div class="semantic-resolution-grid">${renderSimpleGenericField("width", parameters.width, valueFor("width"))}${renderSimpleGenericField("height", parameters.height, valueFor("height"))}</div><div class="semantic-aspects" role="group" aria-label="快速画幅"><button type="button" data-generic-aspect="1:1">1:1</button><button type="button" data-generic-aspect="3:4">3:4</button><button type="button" data-generic-aspect="4:3">4:3</button><button type="button" data-generic-aspect="9:16">9:16</button><button type="button" data-generic-aspect="16:9">16:9</button></div></div>`;
    } else {
      if (parameters.width) html += renderSimpleGenericField("width", parameters.width, valueFor("width"));
      if (parameters.height) html += renderSimpleGenericField("height", parameters.height, valueFor("height"));
    }

    if (parameters.batch_size) html += renderSimpleGenericField("batch_size", parameters.batch_size, valueFor("batch_size"), "wide");

    const media = preset.input_bindings?.media;
    if (media?.type === "slots") {
      for (const [role, slot] of Object.entries(media.slots || {})) {
        const kind = slot.kind || mediaKindFromRole(role) || "file";
        const accept = kind === "image" ? "image/jpeg,image/png,image/webp" : (kind === "video" ? "video/mp4,video/quicktime,video/webm" : (kind === "audio" ? ".wav,.mp3,.flac,.ogg,.m4a" : ""));
        const retained = state.retryRoles.includes(role);
        const label = slot.ui?.label || (kind === "image" ? "参考图" : (kind === "video" ? "参考视频" : (kind === "audio" ? "参考音频" : role)));
        html += `<label class="media-picker generic-media-picker wide"><input type="file" name="${escapeHtml(role)}" accept="${accept}"><span>＋</span><div><strong>${escapeHtml(label)}</strong><small>${retained ? "未重新选择时沿用原任务素材" : "可选；不上传时沿用工作流当前输入"}</small></div><b>选择</b></label>`;
      }
    }

    const basicIds = new Set(["positive_prompt", "negative_prompt", "width", "height", "batch_size"]);
    const extraEntries = Object.entries(parameters).filter(([id]) => !basicIds.has(id));
    if (extraEntries.length) {
      html += `<details class="generic-advanced wide"><summary>高级参数 <span>⌄</span></summary><div class="generic-advanced-grid">${extraEntries.map(([id, spec]) => renderSimpleGenericField(id, spec, valueFor(id))).join("")}</div><p>这些参数来自旧版或手动映射。通常无需修改。</p></details>`;
    }

    container.innerHTML = html;
    const widthInput = $('[data-generic-binding="width"]', container);
    const heightInput = $('[data-generic-binding="height"]', container);
    if (widthInput && heightInput) {
      $$('[data-generic-aspect]', container).forEach(button => button.addEventListener("click", () => {
        const [rw, rh] = button.dataset.genericAspect.split(":").map(Number);
        const currentWidth = Math.max(1, Number(widthInput.value) || Number(parameters.width.default) || 1024);
        const currentHeight = Math.max(1, Number(heightInput.value) || Number(parameters.height.default) || 1024);
        const area = currentWidth * currentHeight;
        const widthStep = Number(parameters.width.step) || 64;
        const heightStep = Number(parameters.height.step) || 64;
        let nextWidth = Math.sqrt(area * rw / rh);
        let nextHeight = nextWidth * rh / rw;
        nextWidth = Math.max(widthStep, Math.round(nextWidth / widthStep) * widthStep);
        nextHeight = Math.max(heightStep, Math.round(nextHeight / heightStep) * heightStep);
        if (parameters.width.minimum != null) nextWidth = Math.max(nextWidth, Number(parameters.width.minimum));
        if (parameters.width.maximum != null) nextWidth = Math.min(nextWidth, Number(parameters.width.maximum));
        if (parameters.height.minimum != null) nextHeight = Math.max(nextHeight, Number(parameters.height.minimum));
        if (parameters.height.maximum != null) nextHeight = Math.min(nextHeight, Number(parameters.height.maximum));
        widthInput.value = String(nextWidth);
        heightInput.value = String(nextHeight);
      }));
    }
  }

  applyPreset = function(presetId, overrides = {}) {
    const merged = mergedOverrides(overrides);
    baseApplyPreset(presetId, merged);
    const preset = selectedPreset();
    const generic = preset?.family === "generic";
    toggleGenerationSections(generic);
    if (generic && preset) renderGenericForm(preset, merged);
  };

  function applyWorkflowDisplayNames() {
    for (const [id, item] of state.workflowItems) {
      const preset = state.presets.get(id);
      if (preset) preset.name = item.name;
    }
    const select = $("#preset-select");
    if (select) {
      [...select.options].forEach(option => {
        const item = state.workflowItems.get(option.value);
        if (item) option.textContent = item.name;
      });
      const selected = state.presets.get(select.value);
      if (selected) $("#active-preset-label").textContent = selected.name;
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

  loadPresets = async function() {
    await baseLoadPresets();
    try {
      if (!state.workflowItems.size) await fetchWorkflowItems();
      else applyWorkflowDisplayNames();
    } catch (_) {}
  };

  loadWorkflows = async function() {
    const items = await fetchWorkflowItems();
    const list = $("#workflow-list");
    if (!list) return;
    const statusText = { enabled: "已启用", disabled: "已禁用", draft: "草稿" };
    list.innerHTML = items.map(item => {
      const manifest = item.manifest || {};
      const builtin = builtinLike(item);
      const toggle = `<button data-workflow-action="${item.status === "enabled" ? "disable" : "enable"}" data-id="${escapeHtml(item.id)}">${item.status === "enabled" ? "禁用" : "启用"}</button>`;
      const rename = `<button data-workflow-action="rename" data-id="${escapeHtml(item.id)}">重命名</button>`;
      const edit = builtin ? "" : `<button data-workflow-action="edit" data-id="${escapeHtml(item.id)}">高级映射</button>`;
      const remove = builtin ? "" : `<button data-workflow-action="delete" data-id="${escapeHtml(item.id)}">删除</button>`;
      const exportLink = builtin ? "" : `<a class="secondary-button" href="/api/workflows/${encodeURIComponent(item.id)}/export?download=1">导出</a>`;
      return `<article class="job-card workflow-card"><div class="job-top"><div><span class="job-time">${builtin ? "内置 H3" : "自定义工作流"} · r${item.revision}</span><h3>${escapeHtml(item.name)}</h3></div><span class="job-status ${item.status === "enabled" ? "succeeded" : "cancelled"}">${statusText[item.status] || escapeHtml(item.status)}</span></div><p class="job-prompt">${escapeHtml(manifest.description || (builtin ? "内置工作流，可修改前端显示名称和启用状态。" : "导入的 ComfyUI API Workflow"))}</p><div class="job-actions">${toggle}${rename}${edit}${exportLink}${remove}</div></article>`;
    }).join("") || `<div class="empty-state"><span>◇</span><h3>还没有工作流</h3></div>`;
  };

  function schemaOptions(result, binding) {
    const node = result.nodes.find(item => item.id === String(binding.node));
    if (!node) return {};
    const raw = result.object_info?.[node.class_type];
    const info = raw?.[node.class_type] || raw;
    const groups = info?.input || {};
    for (const group of Object.values(groups)) {
      const spec = group?.[binding.input];
      if (!Array.isArray(spec) || !spec[1] || typeof spec[1] !== "object") continue;
      const options = spec[1];
      return {
        ...(options.min != null ? { minimum: options.min } : {}),
        ...(options.max != null ? { maximum: options.max } : {}),
        ...(options.step != null ? { step: options.step } : {}),
      };
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

    const parameterRows = basic.parameters.map(item => `<div class="semantic-detected"><span>✓</span><div><strong>${escapeHtml(item.label || BASIC_LABELS[item.semantic] || item.semantic)}</strong><small>已自动识别</small></div></div>`).join("");
    let mediaRow = `<div class="semantic-detected muted"><span>—</span><div><strong>参考图</strong><small>未检测到可替换图片输入</small></div></div>`;
    if (imageCandidates.length === 1) {
      mediaRow = `<div class="semantic-detected"><span>✓</span><div><strong>参考图（可选）</strong><small>${escapeHtml(imageCandidates[0].class_type || "LoadImage")}</small></div></div><input id="semantic-reference-image" type="hidden" value="0">`;
    } else if (imageCandidates.length > 1) {
      mediaRow = `<label class="field semantic-choice"><span>参考图输入 <small>检测到多个候选，请确认</small></span><select id="semantic-reference-image">${imageCandidates.map((item, index) => `<option value="${index}">${escapeHtml(item.class_type || "LoadImage")} · ${escapeHtml(item.default || `图片输入 ${index + 1}`)}</option>`).join("")}</select></label>`;
    }

    let outputRow = `<p class="form-message error">没有检测到 SaveImage / SaveVideo 等输出节点，暂不能保存。</p>`;
    if (outputs.length === 1) {
      outputRow = `<div class="semantic-detected"><span>✓</span><div><strong>主要输出</strong><small>${escapeHtml(outputs[0].class_type)} · ${escapeHtml(outputs[0].kind)}</small></div></div><input id="semantic-output" type="hidden" value="0">`;
    } else if (outputs.length > 1) {
      outputRow = `<label class="field semantic-choice"><span>主要输出 <small>检测到多个输出，请确认</small></span><select id="semantic-output">${outputs.map((item, index) => `<option value="${index}">${escapeHtml(item.class_type)} · ${escapeHtml(item.kind)}</option>`).join("")}</select></label>`;
    }

    const warnings = (basic.warnings || []).map(text => `<li>${escapeHtml(text)}</li>`).join("");
    root.innerHTML = `<div class="semantic-summary"><div class="semantic-section-title"><strong>已识别的基础输入</strong><small>默认只把这些内容放到手机生成页</small></div>${parameterRows || `<div class="semantic-detected muted"><span>!</span><div><strong>未识别到基础文字或尺寸输入</strong><small>可展开高级映射手动补充</small></div></div>`}${mediaRow}${outputRow}${warnings ? `<ul class="semantic-warnings">${warnings}</ul>` : ""}</div>${extras.length ? `<details class="semantic-advanced"><summary>高级：手动追加参数 <span>⌄</span></summary><p>通常不需要修改。这里保留旧版的节点级映射能力。</p>${extras.map(input => `<label class="workflow-binding"><input type="checkbox" data-workflow-extra data-node="${escapeHtml(input.node)}" data-input="${escapeHtml(input.name)}" data-current="${escapeHtml(JSON.stringify(input.value))}" data-control="${escapeHtml(input.suggested_control)}"${input.checked ? " checked" : ""}><span>${escapeHtml(input.classType)} · ${escapeHtml(input.name)}</span><small>${escapeHtml(input.value)}</small></label>`).join("")}</details>` : ""}`;
    $("#save-workflow").disabled = outputs.length === 0;
    $("#save-workflow").textContent = "保存并启用";
  };

  function slugify(value) {
    const slug = String(value || "").toLowerCase().replace(/\.json$/i, "").replace(/[^a-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 64);
    return slug.length >= 2 ? slug : `workflow-${Date.now().toString(36)}`;
  }

  function parameterFromBinding(result, binding) {
    const type = binding.type || (Number.isInteger(binding.default) ? "integer" : (typeof binding.default === "number" ? "number" : "string"));
    return {
      id: binding.semantic,
      node: binding.node,
      input: binding.input,
      type,
      default: binding.default,
      ...schemaOptions(result, binding),
      ui: { label: binding.label || BASIC_LABELS[binding.semantic] || binding.semantic, control: binding.control || (type === "string" ? "text" : "number"), semantic: binding.semantic },
    };
  }

  async function saveSemanticWorkflow(event) {
    event.preventDefault();
    event.stopImmediatePropagation();
    const message = $("#workflow-message");
    const result = state.workflowInspection;
    if (!state.workflowDraft || !result) return;
    const name = $("#workflow-name").value.trim();
    if (!name) {
      message.className = "form-message error";
      message.textContent = "请先填写工作流名称";
      return;
    }
    let workflowId = $("#workflow-id").value.trim().toLowerCase();
    if (!/^[a-z0-9][a-z0-9._-]{1,63}$/.test(workflowId)) {
      workflowId = slugify(workflowId || name);
      $("#workflow-id").value = workflowId;
    }
    const basic = result.basic_bindings || { parameters: [], media: { reference_image: [] }, outputs: result.output_candidates || [] };
    const parameters = basic.parameters.map(item => parameterFromBinding(result, item));
    $$('[data-workflow-extra]:checked').forEach(input => {
      const current = JSON.parse(input.dataset.current);
      const type = typeof current === "boolean" ? "boolean" : (Number.isInteger(current) ? "integer" : (typeof current === "number" ? "number" : "string"));
      const id = `extra_${input.dataset.node}_${input.dataset.input}`.toLowerCase().replace(/[^a-z0-9._-]+/g, "-").slice(0, 64);
      parameters.push({ id, node: input.dataset.node, input: input.dataset.input, type, default: current, ui: { label: input.dataset.input, control: input.dataset.control || "text", semantic: "advanced" } });
    });

    const imageCandidates = basic.media?.reference_image || [];
    const mediaIndex = Number($("#semantic-reference-image")?.value || 0);
    const image = imageCandidates[mediaIndex];
    const media = image ? { type: "slots", slots: { image_0: { node: image.node, input: image.input, kind: "image", ui: { label: "参考图", optional: true } } } } : { type: "none" };
    const outputs = basic.outputs || result.output_candidates || [];
    const outputIndex = Number($("#semantic-output")?.value || 0);
    const selectedOutput = outputs[outputIndex];
    if (!selectedOutput) {
      message.className = "form-message error";
      message.textContent = "请先确认主要输出";
      return;
    }
    const output = {
      id: "primary",
      node: selectedOutput.node,
      kind: selectedOutput.kind,
      history_keys: selectedOutput.kind === "image" ? ["images"] : (selectedOutput.kind === "video" ? ["videos", "video", "files", "images"] : ["files"]),
      primary: true,
    };
    const config = { id: workflowId, name, parameters, media, outputs: [output] };
    const button = $("#save-workflow");
    button.disabled = true;
    try {
      const item = await apiAction("/api/workflows", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ workflow: state.workflowDraft, config }) });
      await apiAction(`/api/workflows/${encodeURIComponent(item.id)}/status`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: "enabled" }) });
      message.className = "form-message";
      message.textContent = `${item.name} 已保存并启用；现在可直接到生成页使用。`;
      state.workflowEditingDetail = null;
      await Promise.all([loadWorkflows(), loadPresets()]);
    } catch (error) {
      message.className = "form-message error";
      message.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }

  jobCard = function(job) {
    const family = workflowFamily(job.preset_id);
    const displayName = workflowDisplayName(job.preset_id, job.preset_name || job.preset_id);
    if (family !== "generic") return baseJobCard({ ...job, preset_name: displayName });

    const active = ["submitting", "queued", "running"].includes(job.status);
    const progress = job.progress_percent ?? (job.status === "succeeded" ? 100 : 0);
    const progressValue = Math.max(0, Math.min(100, Number(progress) || 0));
    const queueText = job.status === "queued" && job.queue_position ? ` · 第 ${job.queue_position} 位` : "";
    const values = job.input_values || {};
    const prompt = values.positive_prompt || values.prompt || Object.entries(values).find(([key, value]) => /prompt|text/i.test(key) && typeof value === "string")?.[1] || "";
    const meta = [];
    if (values.width && values.height) meta.push(`${values.width} × ${values.height}`);
    if (values.batch_size != null) meta.push(`批次 ${values.batch_size}`);
    meta.push(displayName);
    const actions = [];
    if (active) actions.push(`<button data-action="cancel" data-id="${job.id}">取消任务</button>`);
    if (job.status === "succeeded") actions.push(`<button class="play" data-generic-results data-id="${job.id}">查看结果</button>`);
    if (["failed", "cancelled", "interrupted", "succeeded", "output_missing"].includes(job.status)) actions.push(`<button data-action="retry" data-id="${job.id}">载入原参数</button>`);
    if (["failed", "cancelled", "interrupted", "succeeded", "output_missing"].includes(job.status)) actions.push(`<button data-action="delete" data-id="${job.id}">移出历史</button>`);
    return `<article class="job-card" data-job="${job.id}"><div class="job-top"><div><span class="job-time">${formatDate(job.created_at)}</span><h3>${escapeHtml(displayName)}</h3></div><span class="job-status ${job.status}">${statusLabels[job.status] || job.status}</span></div>${prompt ? `<p class="job-prompt">${escapeHtml(prompt)}</p>` : ""}<div class="job-meta">${meta.map(value => `<span>${escapeHtml(value)}</span>`).join("")}</div>${active || ["succeeded", "failed", "cancelled", "interrupted", "output_missing"].includes(job.status) ? `<div class="job-progress"><div><span>${escapeHtml(job.stage || "等待状态")} ${queueText}</span><b>${progressValue}% · ${formatDuration(job.elapsed_seconds)}</b></div><progress class="progress-track" max="100" value="${progressValue}" aria-label="进度 ${progressValue}%"></progress></div>` : ""}${job.error_summary ? `<p class="job-error">${escapeHtml(job.error_summary)}</p>` : ""}<div class="job-actions">${actions.join("")}</div></article>`;
  };

  async function openArtifactViewer(jobId) {
    const modal = $("#artifact-modal");
    const body = $("#artifact-body");
    const title = $("#artifact-title");
    const job = state.jobs.get(jobId);
    title.textContent = workflowDisplayName(job?.preset_id, "生成结果");
    body.innerHTML = `<p class="metric-note">正在读取结果…</p>`;
    modal.classList.remove("hidden");
    document.body.classList.add("video-open");
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(jobId)}/artifacts`);
      if (!response.ok) throw new Error("结果列表加载失败");
      const data = await response.json();
      const outputs = data.items.filter(item => item.direction === "output");
      if (!outputs.length) {
        body.innerHTML = `<div class="empty-state"><span>◎</span><h3>暂未找到结果文件</h3><p>ComfyUI 可能仍在写入结果，可稍后再打开。</p></div>`;
        return;
      }
      body.innerHTML = `<div class="artifact-grid">${outputs.map(item => {
        const src = `/api/jobs/${encodeURIComponent(jobId)}/artifacts/${item.id}`;
        const download = `${src}?download=1`;
        if (item.kind === "image") return `<figure class="artifact-item"><img src="${src}" alt="生成结果"><figcaption><span>${escapeHtml(item.original_name || `图片 ${item.ordinal + 1}`)}</span><a href="${download}">下载</a></figcaption></figure>`;
        if (item.kind === "video") return `<figure class="artifact-item"><video controls playsinline preload="metadata" src="${src}"></video><figcaption><span>${escapeHtml(item.original_name || `视频 ${item.ordinal + 1}`)}</span><a href="${download}">下载</a></figcaption></figure>`;
        if (item.kind === "audio") return `<figure class="artifact-item"><audio controls src="${src}"></audio><figcaption><span>${escapeHtml(item.original_name || `音频 ${item.ordinal + 1}`)}</span><a href="${download}">下载</a></figcaption></figure>`;
        return `<div class="artifact-file"><span>${escapeHtml(item.original_name || `文件 ${item.ordinal + 1}`)}</span><a href="${download}">下载</a></div>`;
      }).join("")}</div>`;
    } catch (error) {
      body.innerHTML = `<p class="form-message error">${escapeHtml(error.message)}</p>`;
    }
  }

  function closeArtifactViewer() {
    const modal = $("#artifact-modal");
    $$('video, audio', modal).forEach(media => { media.pause(); media.removeAttribute("src"); });
    modal.classList.add("hidden");
    document.body.classList.remove("video-open");
  }

  function installStyles() {
    const style = document.createElement("style");
    style.textContent = `
      .topbar-actions{display:flex;align-items:center;gap:8px}.settings-entry{flex:none;cursor:pointer}.top-nav{grid-column:1/-1}.workflow-picker-main{margin:0 0 14px;padding:12px;background:#151812;border:1px solid var(--line);border-radius:14px}.workflow-picker-main>span{color:var(--lime)}
      .generic-intro{display:flex;flex-direction:column;gap:5px;padding:12px 13px;background:rgba(200,243,106,.06);border:1px solid rgba(200,243,106,.16);border-radius:13px}.generic-intro strong{font-size:13px}.generic-intro span{color:var(--muted);font-size:10px;line-height:1.5}.semantic-section-title{display:flex;align-items:flex-end;justify-content:space-between;gap:10px;margin-bottom:10px}.semantic-section-title strong{font-size:12px}.semantic-section-title small{color:var(--muted);font-size:9px;text-align:right}.semantic-resolution{padding:12px;background:#151812;border:1px solid var(--line);border-radius:14px}.semantic-resolution-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.semantic-aspects{display:grid;grid-template-columns:repeat(5,1fr);gap:6px;margin-top:9px}.semantic-aspects button{padding:8px 3px;color:var(--muted);background:#121510;border:1px solid #3a4033;border-radius:9px;font-size:10px;cursor:pointer}.generic-advanced,.semantic-advanced{padding:12px;background:#151812;border:1px solid var(--line);border-radius:13px}.generic-advanced summary,.semantic-advanced summary{display:flex;justify-content:space-between;font-size:11px;font-weight:800;cursor:pointer}.generic-advanced-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px}.generic-advanced p,.semantic-advanced p{margin:8px 0;color:var(--muted);font-size:9px;line-height:1.5}
      .semantic-summary{display:grid;gap:8px;margin-top:12px}.semantic-detected{display:grid;grid-template-columns:28px 1fr;align-items:center;gap:9px;padding:10px 11px;background:#151812;border:1px solid rgba(200,243,106,.16);border-radius:11px}.semantic-detected>span{display:grid;width:24px;height:24px;place-items:center;color:var(--lime);background:var(--lime-dark);border-radius:50%;font-size:11px;font-weight:900}.semantic-detected strong,.semantic-detected small{display:block}.semantic-detected strong{font-size:11px}.semantic-detected small{margin-top:2px;color:var(--muted);font-size:9px}.semantic-detected.muted{border-color:var(--line)}.semantic-detected.muted>span{color:var(--muted);background:var(--surface-2)}.semantic-choice{margin-top:4px}.semantic-warnings{margin:2px 0 0;padding-left:18px;color:var(--amber);font-size:9px;line-height:1.6}.workflow-card .secondary-button{display:inline-flex;align-items:center;min-height:auto;text-decoration:none}.workflow-settings-back{cursor:pointer}
      .artifact-grid{display:grid;gap:12px}.artifact-item{margin:0;padding:8px;background:#0f110d;border:1px solid var(--line);border-radius:12px}.artifact-item img,.artifact-item video{display:block;width:100%;max-height:70vh;object-fit:contain;background:#000;border-radius:8px}.artifact-item audio{width:100%}.artifact-item figcaption,.artifact-file{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:9px 3px 2px;color:var(--muted);font-size:10px}.artifact-item a,.artifact-file a{color:var(--lime);text-decoration:none}.artifact-file{padding:12px;background:#151812;border-radius:10px}
      @media(max-width:430px){.semantic-aspects{grid-template-columns:repeat(3,1fr)}.generic-advanced-grid{grid-template-columns:1fr}.topbar-actions .status-pill{max-width:130px;overflow:hidden;white-space:nowrap}.settings-entry{width:36px;height:36px}}
    `;
    document.head.append(style);
  }

  document.addEventListener("DOMContentLoaded", () => {
    installStyles();

    const nav = $("#nav-workflows");
    const pill = $("#connection-pill");
    if (nav && pill) {
      const actions = document.createElement("div");
      actions.className = "topbar-actions";
      pill.parentNode.insertBefore(actions, pill);
      actions.append(pill, nav);
      nav.className = "icon-button settings-entry";
      nav.innerHTML = "⚙";
      nav.setAttribute("aria-label", "工作流设置");
      nav.title = "工作流设置";
    }

    const selector = $("#preset-select")?.closest("label");
    const form = $("#job-form");
    if (selector && form) {
      selector.id = "workflow-picker-main";
      selector.className = "field workflow-picker-main";
      const label = $("span", selector);
      if (label) label.textContent = "工作流";
      form.insertBefore(selector, $("#fl2va-media"));
    }

    const heading = $("#view-workflows .page-heading");
    if (heading && !$("#workflow-settings-back")) {
      const back = document.createElement("button");
      back.id = "workflow-settings-back";
      back.className = "icon-button workflow-settings-back";
      back.type = "button";
      back.textContent = "←";
      back.setAttribute("aria-label", "返回生成页");
      back.addEventListener("click", () => setView("generate"));
      heading.append(back);
    }

    const idField = $("#workflow-id")?.closest("label");
    idField?.classList.add("hidden");
    const workflowJson = $("#workflow-json");
    workflowJson?.addEventListener("change", event => {
      state.workflowEditingDetail = null;
      const file = event.target.files?.[0];
      if (!file) return;
      if (!$("#workflow-name").value.trim()) $("#workflow-name").value = file.name.replace(/\.json$/i, "").replace(/[_-]+/g, " ");
      if (!$("#workflow-id").value.trim()) $("#workflow-id").value = slugify(file.name);
    }, true);

    $("#save-workflow")?.addEventListener("click", saveSemanticWorkflow, true);

    $("#workflow-list")?.addEventListener("click", async event => {
      const button = event.target.closest("[data-workflow-action]");
      if (!button) return;
      const action = button.dataset.workflowAction;
      const id = button.dataset.id;
      if (action === "rename") {
        event.preventDefault(); event.stopImmediatePropagation();
        const item = state.workflowItems.get(id);
        if (!item) return;
        const name = window.prompt("前端显示名称", item.name);
        if (!name?.trim() || name.trim() === item.name) return;
        button.disabled = true;
        try {
          await apiAction(`/api/workflows/${encodeURIComponent(id)}/copy`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id, name: name.trim() }) });
          await apiAction(`/api/workflows/${encodeURIComponent(id)}/status`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ status: item.status }) });
          await Promise.all([loadWorkflows(), loadPresets()]);
        } catch (error) { window.alert(error.message); }
        finally { button.disabled = false; }
        return;
      }
      if (action === "edit") {
        event.preventDefault(); event.stopImmediatePropagation();
        try {
          const detail = await apiAction(`/api/workflows/${encodeURIComponent(id)}`);
          state.workflowEditingDetail = detail;
          state.workflowDraft = detail.definition.workflow;
          $("#workflow-id").value = detail.id;
          $("#workflow-name").value = detail.name;
          const inspection = await apiAction("/api/workflows/inspect", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(state.workflowDraft) });
          renderWorkflowInspection(inspection);
          $("#workflow-message").className = "form-message";
          $("#workflow-message").textContent = `正在编辑 ${detail.name}；默认仍只暴露基础输入。`;
          $("#workflow-name").scrollIntoView({ behavior: "smooth", block: "center" });
        } catch (error) { window.alert(error.message); }
      }
    }, true);

    $("#jobs-list")?.addEventListener("click", async event => {
      const resultButton = event.target.closest("[data-generic-results]");
      if (resultButton) {
        event.preventDefault(); event.stopImmediatePropagation();
        await openArtifactViewer(resultButton.dataset.id);
        return;
      }
      const retryButton = event.target.closest('[data-action="retry"]');
      if (!retryButton) return;
      const job = state.jobs.get(retryButton.dataset.id);
      if (!job || workflowFamily(job.preset_id) !== "generic") return;
      event.preventDefault(); event.stopImmediatePropagation();
      retryButton.disabled = true;
      try {
        const draft = await apiAction(`/api/jobs/${encodeURIComponent(job.id)}/retry`, { method: "POST" });
        $("#job-form").reset();
        Object.values(state.mediaFiles).flat().forEach(entry => { if (entry?.url) URL.revokeObjectURL(entry.url); });
        state.mediaFiles = { image: [], video: [], audio: [] };
        state.retryRoles = draft.input_roles || [];
        state.retryKeepRoles = [...state.retryRoles];
        $("#retry-source-id").value = draft.retry_source_id;
        applyPreset(draft.preset_id, draft);
        $("#retry-draft span").textContent = state.retryRoles.length ? "已载入原参数；未重新选择的参考素材会沿用" : "已载入原任务参数";
        $("#retry-draft").classList.remove("hidden");
        setView("generate");
      } catch (error) { window.alert(error.message); }
      finally { retryButton.disabled = false; }
    }, true);

    if (!$("#artifact-modal")) {
      const modal = document.createElement("div");
      modal.id = "artifact-modal";
      modal.className = "video-modal hidden";
      modal.setAttribute("role", "dialog");
      modal.setAttribute("aria-modal", "true");
      modal.innerHTML = `<div class="video-dialog"><div class="video-dialog-head"><strong id="artifact-title">生成结果</strong><button id="artifact-close" type="button" aria-label="关闭结果">×</button></div><div id="artifact-body"></div></div>`;
      document.body.append(modal);
      $("#artifact-close").addEventListener("click", closeArtifactViewer);
      modal.addEventListener("click", event => { if (event.target === modal) closeArtifactViewer(); });
    }
  });
})();
