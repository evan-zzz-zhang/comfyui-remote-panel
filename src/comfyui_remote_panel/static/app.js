const state = { jobs: new Map(), presets: new Map(), metrics: null, eventSource: null, retryRoles: [], retryKeepRoles: [], mediaFiles: { image: [], video: [], audio: [] }, isSubmitting: false, jobsPage: 1, jobsHasMore: false, pollTimer: null, pollDelay: 2000, deviceTimer: null, deviceChecks: 0, thumbnailStarted: new Set(), thumbnailObserver: null, workflowDraft: null };
const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

const statusLabels = {
  submitting: "提交中", queued: "排队中", running: "生成中", succeeded: "已完成",
  failed: "失败", cancelled: "已取消", interrupted: "意外中断", output_missing: "输出缺失", deleting: "删除中"
};

function formatBytes(value) {
  if (value == null) return "—";
  const units = ["B", "KB", "MB", "GB", "TB"];
  let amount = Number(value), index = 0;
  while (amount >= 1024 && index < units.length - 1) { amount /= 1024; index += 1; }
  return `${amount.toFixed(index > 1 ? 1 : 0)} ${units[index]}`;
}
function formatDuration(seconds) {
  if (seconds == null) return "—";
  const value = Math.max(0, Number(seconds));
  if (value < 60) return `${value}秒`;
  return `${Math.floor(value / 60)}分${value % 60}秒`;
}
function formatDate(timestamp) {
  return new Date(Number(timestamp) * 1000).toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}
function escapeHtml(value) {
  return String(value ?? "").replace(/[&<>'"]/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;","'":"&#39;",'"':"&quot;"}[char]));
}
function parseWorkflowFile(text) {
  let cleaned = String(text ?? "").replace(/^\uFEFF/, "").trim();
  const fenced = cleaned.match(/^```(?:json)?\s*([\s\S]*?)\s*```$/i);
  if (fenced) cleaned = fenced[1].trim();
  let value;
  try { value = JSON.parse(cleaned); }
  catch (_) { throw new Error("无法解析工作流 JSON。请使用 ComfyUI 的“导出（API）”，不要选择网页、日志或带说明文字的文件。"); }
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("工作流 JSON 顶层必须是对象。");
  return value;
}
function aspectLabel(value) {
  return ({ reference: "参考图 1 画幅", reference_image: "参考图 1 画幅", reference_video: "参考视频 1 画幅" })[value] || value;
}
function mediaKindFromRole(role) {
  if (role === "first" || role === "last" || role.startsWith("image_")) return "image";
  if (role.startsWith("video_")) return "video";
  if (role.startsWith("audio_")) return "audio";
  return null;
}

function setView(name) {
  $$(".view").forEach(view => view.classList.toggle("active", view.id === `view-${name}`));
  $$(".top-nav button").forEach(button => button.classList.toggle("active", button.dataset.view === name));
  window.scrollTo({ top: 0, behavior: "smooth" });
}

function selectedPreset() { return state.presets.get($("#preset-select")?.value); }
function optionKeys(spec) { return Object.keys(spec?.values || {}); }
function fillSelect(select, values, selected) {
  select.innerHTML = values.map(value => `<option value="${escapeHtml(value)}">${escapeHtml(value)}</option>`).join("");
  if (values.includes(String(selected))) select.value = String(selected);
}
function updateSubmitAvailability() {
  const preset = selectedPreset();
  const runtime = state.metrics?.presets?.[preset?.id];
  $("#submit-button").disabled = state.isSubmitting || !preset || !(runtime ? runtime.available : preset.available);
}
function applyPreset(presetId, overrides = {}) {
  const preset = state.presets.get(presetId) || [...state.presets.values()][0];
  if (!preset) return;
  $("#preset-select").value = preset.id;
  const parameters = preset.parameters;
  const generic = preset.family === "generic";
  const genericContainer = $("#generic-parameters");
  genericContainer.classList.toggle("hidden", !generic);
  genericContainer.innerHTML = generic ? Object.entries(parameters).map(([name, spec]) => {
    const label = escapeHtml(spec.ui?.label || name), value = overrides[name] ?? spec.default ?? "";
    if (spec.type === "enum") return `<label class="field"><span>${label}</span><select name="generic_${escapeHtml(name)}" data-generic-binding="${escapeHtml(name)}" data-value-type="enum">${optionKeys(spec).map(option => `<option value="${escapeHtml(option)}"${String(option) === String(value) ? " selected" : ""}>${escapeHtml(option)}</option>`).join("")}</select></label>`;
    if (spec.type === "boolean") return `<label class="field"><span>${label}</span><input type="checkbox" name="generic_${escapeHtml(name)}" data-generic-binding="${escapeHtml(name)}" data-value-type="boolean"${value ? " checked" : ""}></label>`;
    const type = ["integer", "number"].includes(spec.type) ? "number" : "text";
    return `<label class="field"><span>${label}</span><input type="${type}" name="generic_${escapeHtml(name)}" data-generic-binding="${escapeHtml(name)}" data-value-type="${escapeHtml(spec.type)}" value="${escapeHtml(value)}"${spec.minimum != null ? ` min="${spec.minimum}"` : ""}${spec.maximum != null ? ` max="${spec.maximum}"` : ""}${spec.step != null ? ` step="${spec.step}"` : ""}></label>`;
  }).join("") : "";
  if (generic && preset.input_bindings?.media?.type === "slots") {
    genericContainer.innerHTML += Object.entries(preset.input_bindings.media.slots).map(([role, slot]) => {
      const kind = slot.kind || mediaKindFromRole(role) || "file";
      const accept = kind === "image" ? "image/jpeg,image/png,image/webp" : (kind === "video" ? "video/mp4,video/quicktime,video/webm" : (kind === "audio" ? ".wav,.mp3,.flac,.ogg,.m4a" : ""));
      return `<label class="field"><span>${escapeHtml(slot.ui?.label || role)}</span><input type="file" name="${escapeHtml(role)}" accept="${accept}"></label>`;
    }).join("");
  }
  if (generic) {
    $("#active-preset-label").textContent = preset.name;
    $("#preset-description").textContent = `${preset.description || "通用 ComfyUI 工作流"}。仅修改工作流明确暴露的参数。`;
    $("#fl2va-media").classList.add("hidden"); $("#ref2va-media").classList.add("hidden");
    $$("#fl2va-media input, #ref2va-media input").forEach(input => { input.disabled = true; });
    updateSubmitAvailability(); return;
  }
  fillSelect($("select[name=scheduler]"), optionKeys(parameters.scheduler), overrides.scheduler ?? parameters.scheduler.default);
  fillSelect($("select[name=sampler]"), optionKeys(parameters.sampler), overrides.sampler ?? parameters.sampler.default);
  const steps = $("input[name=steps]");
  steps.min = parameters.steps.minimum; steps.max = parameters.steps.maximum;
  steps.value = overrides.steps ?? parameters.steps.default;
  $("#active-preset-label").textContent = preset.name;
  $("#preset-description").textContent = `${preset.description}。种子留空时随机；任务会保存实际使用的全部参数。`;
  const referenceWorkflow = preset.family === "ref2va";
  $("#fl2va-media").classList.toggle("hidden", referenceWorkflow);
  $("#ref2va-media").classList.toggle("hidden", !referenceWorkflow);
  $$("#fl2va-media input").forEach(input => { input.disabled = referenceWorkflow; });
  $$("#ref2va-media input").forEach(input => { input.disabled = !referenceWorkflow; });
  $("#first-frame-label").textContent = referenceWorkflow ? "参考图 1" : "首帧";
  $("#last-frame-label").textContent = referenceWorkflow ? "参考图 2" : "尾帧";
  $("#first-frame-hint").textContent = referenceWorkflow ? "主要参考" : "镜头起点 · 可选";
  $("#last-frame-hint").textContent = referenceWorkflow ? "补充参考" : "镜头终点 · 可选";
  const imageAspect = $("#reference-aspect-image-option");
  const videoAspect = $("#reference-aspect-video-option");
  imageAspect.value = referenceWorkflow ? "reference_image" : "reference";
  imageAspect.textContent = referenceWorkflow ? "参考图 1 画幅（需参考图）" : "参考图比例（需参考图）";
  videoAspect.hidden = !referenceWorkflow;
  $("#follow-video-duration").classList.toggle("hidden", !referenceWorkflow);
  updateSubmitAvailability();
}

function renderJobs() {
  const jobs = [...state.jobs.values()].sort((a, b) => b.created_at - a.created_at);
  state.thumbnailObserver?.disconnect();
  $("#jobs-empty").classList.toggle("hidden", jobs.length > 0);
  $("#jobs-list").innerHTML = jobs.map(jobCard).join("");
  updateJobsSummary();
  observeThumbnails();
}

function updateJobsSummary() {
  const jobs = [...state.jobs.values()];
  $("#jobs-empty").classList.toggle("hidden", jobs.length > 0);
  const active = jobs.filter(job => ["submitting", "queued", "running"].includes(job.status)).length;
  $("#job-badge").textContent = active;
  $("#job-badge").classList.toggle("hidden", !active);
  $("#load-more-jobs").classList.toggle("hidden", !state.jobsHasMore);
}

function upsertJob(job) {
  state.jobs.set(job.id, job);
  const list = $("#jobs-list");
  const existing = list.querySelector(`[data-job="${CSS.escape(job.id)}"]`);
  const oldThumbnail = existing?.querySelector(".job-preview video");
  const oldPreview = existing?.querySelector(".job-preview");
  if (oldPreview) state.thumbnailObserver?.unobserve(oldPreview);
  const wrapper = document.createElement("div");
  wrapper.innerHTML = jobCard(job).trim();
  const card = wrapper.firstElementChild;
  if (existing) existing.replaceWith(card);
  else list.prepend(card);
  const newThumbnail = card.querySelector(".job-preview video");
  if (newThumbnail && oldThumbnail?.src) newThumbnail.src = oldThumbnail.src;
  updateJobsSummary();
  observeThumbnails();
}

function removeJob(id) {
  state.jobs.delete(id);
  $("#jobs-list").querySelector(`[data-job="${CSS.escape(id)}"]`)?.remove();
  updateJobsSummary();
}

function observeThumbnails() {
  if (!state.thumbnailObserver) return;
  $$(".job-preview").forEach(preview => {
    if (!preview.querySelector("video")?.src && !state.thumbnailStarted.has(preview.dataset.id)) state.thumbnailObserver.observe(preview);
  });
}

function jobCard(job) {
  const active = ["submitting", "queued", "running"].includes(job.status);
  const progress = job.progress_percent ?? (job.status === "succeeded" ? 100 : 0);
  const progressValue = Math.max(0, Math.min(100, Number(progress) || 0));
  const queueText = job.status === "queued" && job.queue_position ? ` · 第 ${job.queue_position} 位` : "";
  const video = job.has_video ? `<button class="job-preview" data-action="play" data-id="${job.id}" type="button" aria-label="播放视频"><video muted playsinline preload="none"></video><span>▶</span></button>` : "";
  const actions = [];
  if (active) actions.push(`<button data-action="cancel" data-id="${job.id}">取消任务</button>`);
  if (["failed", "cancelled", "interrupted", "succeeded", "output_missing"].includes(job.status)) actions.push(`<button data-action="retry" data-id="${job.id}">载入原参数</button>`);
  if (job.has_video) {
    actions.unshift(`<button class="play" data-action="play" data-id="${job.id}">播放视频</button>`);
    actions.push(`<a href="/api/jobs/${job.id}/video?download=1">下载</a>`);
  }
  if (["failed", "cancelled", "interrupted", "succeeded", "output_missing"].includes(job.status)) actions.push(`<button data-action="delete" data-id="${job.id}">移出历史</button>`);
  return `<article class="job-card" data-job="${job.id}">
    <div class="job-top"><div><span class="job-time">${formatDate(job.created_at)}</span><h3>${escapeHtml(job.mode)} · ${escapeHtml(aspectLabel(job.aspect_ratio))}</h3></div><span class="job-status ${job.status}">${statusLabels[job.status] || job.status}</span></div>
    <p class="job-prompt">${escapeHtml(job.prompt)}</p>
    <div class="job-meta"><span>${escapeHtml(job.preset_name || job.preset_id)}</span><span>${job.duration_seconds} 秒</span><span>${job.megapixels} MP</span><span>${escapeHtml(job.scheduler)}</span><span>${escapeHtml(job.sampler)}</span><span>${job.steps} 步</span><span>种子 ${job.seed}</span><span>${formatBytes(job.size_bytes)}</span></div>
    ${active || ["succeeded", "failed", "cancelled", "interrupted", "output_missing"].includes(job.status) ? `<div class="job-progress"><div><span>${escapeHtml(job.stage || "等待状态")} ${queueText}</span><b>${progressValue}% · ${formatDuration(job.elapsed_seconds)}</b></div><progress class="progress-track" max="100" value="${progressValue}" aria-label="进度 ${progressValue}%"></progress></div>` : ""}
    ${job.error_summary ? `<p class="job-error">${escapeHtml(job.error_summary)}</p>` : ""}
    ${video}<div class="job-actions">${actions.join("")}</div>
  </article>`;
}

function openPlayer(id) {
  const job = state.jobs.get(id);
  const modal = $("#video-modal"), player = $("#video-player");
  $("#video-title").textContent = job ? `${job.mode} · ${aspectLabel(job.aspect_ratio)}` : "视频预览";
  modal.classList.remove("hidden");
  document.body.classList.add("video-open");
  player.src = `/api/jobs/${id}/video#t=0.01`;
  player.load();
  const playback = player.play();
  if (playback) playback.catch(() => {});
}
function closePlayer() {
  const modal = $("#video-modal"), player = $("#video-player");
  player.pause(); player.removeAttribute("src"); player.load();
  modal.classList.add("hidden"); document.body.classList.remove("video-open");
}

function renderMetrics(metrics) {
  if (!metrics) return;
  state.metrics = metrics;
  const comfy = metrics.comfyui || {};
  const pill = $("#connection-pill");
  pill.className = `status-pill ${comfy.online ? "status-online" : "status-offline"}`;
  pill.innerHTML = `<span></span>${comfy.online ? "工作站在线" : "工作站离线"}`;
  $("#device-overview").innerHTML = `<div class="device-chip ${comfy.online ? "online" : ""}"><small>COMFYUI</small><strong>${comfy.online ? `在线 · ${escapeHtml(comfy.version || "")}` : "离线"}</strong></div><div class="device-chip"><small>队列任务</small><strong>${comfy.queue_count ?? "—"}</strong></div>`;
  renderControl(comfy);
  const gpu = metrics.gpus?.[0];
  $("#gpu-name").textContent = gpu?.name || "暂不可用";
  $("#gpu-util").textContent = gpu?.utilization_percent != null ? Math.round(gpu.utilization_percent) : "—";
  $("#gpu-bar").style.width = `${Math.min(100, gpu?.utilization_percent || 0)}%`;
  $("#gpu-memory").textContent = gpu ? `${formatBytes(gpu.memory_used_bytes)} / ${formatBytes(gpu.memory_total_bytes)}` : "—";
  $("#gpu-temp").textContent = gpu?.temperature_c != null ? `${gpu.temperature_c} °C` : "—";
  $("#gpu-power").textContent = gpu?.power_w != null ? `${Number(gpu.power_w).toFixed(0)} W` : "—";
  const memory = metrics.memory || {};
  $("#ram-percent").textContent = memory.percent != null ? `${memory.percent}%` : "—";
  $("#ram-bar").style.width = `${memory.percent || 0}%`;
  $("#ram-memory").textContent = memory.total_bytes ? `${formatBytes(memory.used_bytes)} / ${formatBytes(memory.total_bytes)}` : "暂不可用";
  $("#disk-free").textContent = `${formatBytes(metrics.disk?.free_bytes)} 可用`;
  $("#tracked-size").textContent = formatBytes(metrics.disk?.tracked_bytes);
  $("#uptime").textContent = formatDuration(metrics.uptime_seconds);
  const unavailable = [...state.presets.values()].filter(preset => metrics.presets?.[preset.id]?.available === false);
  $("#preset-diagnostics").textContent = unavailable.map(preset => `${preset.name}：${(metrics.presets[preset.id].diagnostics || ["不可用"]).join("；")}`).join("\n");
  updateSubmitAvailability();
}

function renderControl(comfy) {
  const control = comfy.control || { enabled: false };
  const labels = { start: "正在启动", stop: "正在关闭", restart: "正在重启" };
  $("#control-state").textContent = control.operation ? labels[control.operation] : (control.enabled ? "已就绪" : "未配置");
  $$('[data-control]').forEach(button => {
    const action = button.dataset.control;
    button.disabled = !control.enabled || Boolean(control.operation) || !control[`can_${action}`];
  });
  const message = $("#control-message");
  if (control.last_error) {
    message.className = "control-message error";
    message.textContent = control.last_error;
  } else if (control.operation) {
    message.className = "control-message";
    message.textContent = `${labels[control.operation]}，请不要重复操作…`;
  } else if (!control.enabled) {
    message.className = "control-message";
    message.textContent = "需要在本机配置固定启动命令后才能使用。";
  } else {
    message.className = "control-message";
    message.textContent = comfy.online ? "服务在线，可关闭或重启。" : "服务离线，可以远程启动。";
  }
}

async function loadPresets() {
  const response = await fetch("/api/presets");
  if (!response.ok) throw new Error("工作流列表加载失败");
  const result = await response.json();
  state.presets = new Map(result.items.map(preset => [preset.id, preset]));
  const select = $("#preset-select");
  select.innerHTML = result.items.map(preset => `<option value="${escapeHtml(preset.id)}">${escapeHtml(preset.name)}</option>`).join("");
  applyPreset(state.presets.has("h3-fl2va-group") ? "h3-fl2va-group" : result.items[0]?.id);
}

async function loadWorkflows() {
  const response = await fetch("/api/workflows");
  if (!response.ok) throw new Error("无法加载工作流管理列表");
  const data = await response.json();
  const list = $("#workflow-list");
  if (!list) return;
  list.innerHTML = data.items.map(item => {
    const manifest = item.manifest || {};
    const customActions = item.builtin ? "" : `<button data-workflow-action="edit" data-id="${escapeHtml(item.id)}">编辑</button><button data-workflow-action="delete" data-id="${escapeHtml(item.id)}">删除</button>`;
    return `<article class="job-card"><div class="job-card-head"><div><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.id)} · r${item.revision}</small></div><span class="job-status">${escapeHtml(item.status)}</span></div><p>${escapeHtml(manifest.description || (item.builtin ? "内置工作流" : "自定义工作流"))}</p><div class="job-actions"><button data-workflow-action="${item.status === "enabled" ? "disable" : "enable"}" data-id="${escapeHtml(item.id)}">${item.status === "enabled" ? "禁用" : "启用"}</button><button data-workflow-action="test" data-id="${escapeHtml(item.id)}">测试</button><button data-workflow-action="copy" data-id="${escapeHtml(item.id)}">复制</button>${customActions}<a class="secondary-button" href="/api/workflows/${encodeURIComponent(item.id)}/export?download=1">导出</a></div></article>`;
  }).join("") || `<div class="empty-state"><span>◇</span><h3>还没有工作流</h3></div>`;
}

function renderWorkflowInspection(result) {
  const root = $("#workflow-inspection");
  const inputs = result.nodes.flatMap(node => node.inputs.filter(input => !/^Load(Image|Video|Audio)$/i.test(node.class_type) && !input.connected && input.suggested_control !== "unsupported" && input.name !== "filename_prefix").map(input => ({...input, node: node.id, classType: node.class_type})));
  const media = result.nodes.flatMap(node => {
    const match = /^Load(Image|Video|Audio)$/i.exec(node.class_type); if (!match) return [];
    const kind = match[1].toLowerCase(), input = node.inputs.find(value => !value.connected && ["image","file","video","audio"].includes(value.name));
    return input ? [{node:node.id, input:input.name, kind, classType:node.class_type}] : [];
  });
  const outputs = result.output_candidates;
  root.innerHTML = `<h3>选择手机端可修改参数</h3>${inputs.map((input, index) => `<label class="workflow-binding"><input type="checkbox" data-workflow-input data-node="${escapeHtml(input.node)}" data-input="${escapeHtml(input.name)}" data-current="${escapeHtml(JSON.stringify(input.value))}" data-control="${escapeHtml(input.suggested_control)}"${index < 4 && !/(model|ckpt|lora|vae|file|name)/i.test(input.name) ? " checked" : ""}><span>Node ${escapeHtml(input.node)} · ${escapeHtml(input.classType)} · ${escapeHtml(input.name)}</span><small>${escapeHtml(input.value)}</small></label>`).join("") || "<p>没有可安全暴露的字面输入。</p>"}<h3>选择媒体上传槽位</h3>${media.map(item => `<label class="workflow-binding"><input type="checkbox" data-workflow-media data-node="${escapeHtml(item.node)}" data-input="${escapeHtml(item.input)}" data-kind="${escapeHtml(item.kind)}"><span>Node ${escapeHtml(item.node)} · ${escapeHtml(item.classType)}</span><small>${escapeHtml(item.kind)}</small></label>`).join("") || "<p>没有检测到固定媒体加载节点。</p>"}<h3>选择主要输出</h3>${outputs.map((output, index) => `<label class="workflow-binding"><input type="radio" name="workflow-output" data-workflow-output data-node="${escapeHtml(output.node)}" data-kind="${escapeHtml(output.kind)}"${index === 0 ? " checked" : ""}><span>Node ${escapeHtml(output.node)} · ${escapeHtml(output.class_type)}</span><small>${escapeHtml(output.kind)}</small></label>`).join("") || "<p class=\"form-message error\">未自动找到输出节点，请在 ComfyUI 中加入 SaveImage 或 SaveVideo。</p>"}`;
  $("#save-workflow").disabled = outputs.length === 0;
}
async function loadJobs(reset = true) {
  try {
    const page = reset ? 1 : state.jobsPage + 1;
    const response = await fetch(`/api/jobs?page=${page}&page_size=20`);
    if (!response.ok) throw new Error("任务列表加载失败");
    const result = await response.json();
    if (reset) state.jobs = new Map();
    result.items.forEach(job => state.jobs.set(job.id, job));
    state.jobsPage = page; state.jobsHasMore = result.pagination.has_more; renderJobs();
  } catch (_) {}
}
async function reconcileLoadedJobs() {
  const ids = [...state.jobs.keys()];
  if (!ids.length) return;
  const existing = new Set();
  try {
    for (let index = 0; index < ids.length; index += 100) {
      const batch = ids.slice(index, index + 100);
      const response = await fetch(`/api/jobs/existence?ids=${encodeURIComponent(batch.join(","))}`);
      if (!response.ok) return;
      const result = await response.json();
      (result.ids || []).forEach(id => existing.add(id));
    }
    ids.forEach(id => { if (!existing.has(id)) state.jobs.delete(id); });
    renderJobs();
  } catch (_) {}
}
async function loadMetrics() {
  try { const response = await fetch("/api/metrics"); if (response.ok) renderMetrics(await response.json()); } catch (_) {}
}
async function loadNewestJobs() {
  try {
    const response = await fetch("/api/jobs?page=1&page_size=20");
    if (!response.ok) return;
    const result = await response.json();
    result.items.forEach(job => state.jobs.set(job.id, job));
    await reconcileLoadedJobs();
    state.jobsHasMore = state.jobs.size < result.pagination.total;
    renderJobs();
  } catch (_) {}
}
function connectEvents() {
  state.eventSource?.close();
  const source = new EventSource("/api/events"); state.eventSource = source;
  source.onopen = () => { stopPolling(); state.pollDelay = 2000; };
  source.onerror = () => startPolling();
  source.addEventListener("snapshot", event => {
    const snapshot = JSON.parse(event.data);
    snapshot.jobs.forEach(job => state.jobs.set(job.id, job)); renderJobs(); renderMetrics(snapshot.metrics); void reconcileLoadedJobs();
  });
  source.addEventListener("job", event => upsertJob(JSON.parse(event.data)));
  source.addEventListener("job_deleted", event => removeJob(JSON.parse(event.data).id));
  source.addEventListener("metrics", event => renderMetrics(JSON.parse(event.data)));
}
function stopPolling() {
  if (state.pollTimer) window.clearTimeout(state.pollTimer);
  state.pollTimer = null;
}
function startPolling() {
  if (state.pollTimer) return;
  const poll = async () => {
    state.pollTimer = null;
    if (state.eventSource?.readyState === EventSource.OPEN) { state.pollDelay = 2000; return; }
    await Promise.all([loadNewestJobs(), loadMetrics()]);
    state.pollDelay = Math.min(30000, state.pollDelay * 2);
    state.pollTimer = window.setTimeout(poll, state.pollDelay);
  };
  state.pollTimer = window.setTimeout(poll, state.pollDelay);
}
function stopDeviceMonitor() {
  if (state.deviceTimer) window.clearTimeout(state.deviceTimer);
  state.deviceTimer = null; state.deviceChecks = 0;
}
function startDeviceMonitor() {
  stopDeviceMonitor();
  const check = async () => {
    await loadMetrics(); state.deviceChecks += 1;
    if (!state.metrics?.comfyui?.control?.operation || state.deviceChecks >= 150 || document.hidden || state.eventSource?.readyState === EventSource.OPEN) {
      stopDeviceMonitor(); return;
    }
    state.deviceTimer = window.setTimeout(check, 1000);
  };
  state.deviceTimer = window.setTimeout(check, 1000);
}
async function apiAction(path, options = {}) {
  const response = await fetch(path, options);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.error?.message || `请求失败（${response.status}）`);
  }
  return response.status === 204 ? null : response.json();
}

function uploadForm(path, formData, onProgress) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    const startedAt = performance.now();
    request.open("POST", path);
    request.upload.addEventListener("progress", event => {
      if (!event.lengthComputable) return;
      onProgress({ loaded: event.loaded, total: event.total, elapsed: (performance.now() - startedAt) / 1000 });
    });
    request.addEventListener("load", () => {
      let body = {};
      try { body = request.responseText ? JSON.parse(request.responseText) : {}; } catch (_) {}
      if (request.status >= 200 && request.status < 300) resolve(body);
      else {
        const error = new Error(body.error?.message || `请求失败（${request.status}）`);
        error.status = request.status; error.code = body.error?.code;
        reject(error);
      }
    });
    request.addEventListener("error", () => reject(new Error("上传连接失败，请检查网络后重试")));
    request.addEventListener("abort", () => reject(new Error("上传已取消")));
    request.send(formData);
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  const form = $("#job-form"), duration = $("input[name=duration_seconds]"), aspect = $("select[name=aspect_ratio]");
  const firstFrame = $("#first-frame"), lastFrame = $("#last-frame");
  const imageAspect = $("#reference-aspect-image-option"), videoAspect = $("#reference-aspect-video-option");
  const refImages = $("#ref-images"), refVideos = $("#ref-videos"), refAudios = $("#ref-audios");
  const mediaInputs = { image: refImages, video: refVideos, audio: refAudios };
  const mediaMaximums = { image: 9, video: 3, audio: 3 };
  const mediaLabels = { image: "图片", video: "视频", audio: "音频" };
  const mediaTags = { image: "Picture", video: "Video", audio: "Audio" };
  state.thumbnailObserver = "IntersectionObserver" in window ? new IntersectionObserver(entries => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      const preview = entry.target;
      const id = preview.dataset.id;
      const player = preview.querySelector("video");
      if (!id || !player || state.thumbnailStarted.has(id)) continue;
      state.thumbnailStarted.add(id);
      player.src = `/api/jobs/${encodeURIComponent(id)}/video#t=0.01`;
      player.addEventListener("loadeddata", () => player.pause(), { once: true });
      player.load();
      state.thumbnailObserver.unobserve(preview);
    }
  }, { rootMargin: "160px 0px" }) : null;
  const revokeEntry = entry => { if (entry?.url) { URL.revokeObjectURL(entry.url); entry.url = null; } };
  const clearMediaPreviews = () => {
    Object.values(state.mediaFiles).flat().forEach(revokeEntry);
    state.mediaFiles = { image: [], video: [], audio: [] };
    for (const kind of Object.keys(mediaInputs)) {
      mediaInputs[kind].value = "";
      const container = $(`#ref-${kind}-preview`);
      container.innerHTML = "";
      container.classList.add("hidden");
    }
  };
  const sortMedia = kind => state.mediaFiles[kind].sort((a, b) => String(a.role).localeCompare(String(b.role), undefined, { numeric: true }));
  const renderReferenceFiles = kind => {
    const container = $(`#ref-${kind}-preview`);
    const entries = sortMedia(kind);
    const tag = mediaTags[kind];
    container.innerHTML = entries.map((entry, index) => {
      const label = `&lt;${tag} ${index + 1}&gt;`;
      const replace = `<button type="button" data-media-action="replace" data-kind="${kind}" data-index="${index}">替换</button>`;
      const remove = `<button type="button" data-media-action="remove" data-kind="${kind}" data-index="${index}">删除</button>`;
      if (kind === "image") {
        const visual = entry.url ? `<img src="${entry.url}" alt="参考图片 ${index + 1}">` : `<span>已保留素材</span>`;
        return `<div class="media-preview">${visual}<span>${label}</span><div class="media-preview-actions">${replace}${remove}</div></div>`;
      }
      const name = entry.file ? escapeHtml(entry.file.name) : "已保留素材";
      const video = kind === "video" && entry.url ? `<video controls muted playsinline preload="metadata" src="${entry.url}"></video>` : "";
      return `<div class="media-file-item">${video}<span>${name}</span><b>${label} · ${entry.file ? formatBytes(entry.file.size) : "已保留"}</b><div>${replace}${remove}</div></div>`;
    }).join("");
    container.classList.toggle("hidden", entries.length === 0);
  };
  const renderAllReferenceFiles = () => { Object.keys(mediaInputs).forEach(renderReferenceFiles); updateReferenceAspect(); updateFollowButton(); };
  const addSelectedFiles = (kind, input) => {
    const selected = [...input.files];
    const current = state.mediaFiles[kind];
    const slots = new Set(current.map(entry => Number(String(entry.role).split("_").pop())));
    const available = mediaMaximums[kind] - current.length;
    if (selected.length > available) { input.value = ""; window.alert(`最多选择 ${mediaMaximums[kind]} 个${mediaLabels[kind]}`); return; }
    for (const file of selected) {
      let slot = 0; while (slots.has(slot)) slot += 1;
      slots.add(slot);
      current.push({ file, role: `${kind}_${slot}`, url: URL.createObjectURL(file), source: "local" });
    }
    input.value = "";
    renderAllReferenceFiles();
  };
  const replaceMedia = (kind, index) => {
    const chooser = document.createElement("input");
    chooser.type = "file"; chooser.accept = mediaInputs[kind].accept;
    chooser.addEventListener("change", () => {
      const file = chooser.files[0];
      if (!file) { chooser.remove(); return; }
      const entry = state.mediaFiles[kind][index];
      revokeEntry(entry);
      state.mediaFiles[kind][index] = { ...entry, file, url: URL.createObjectURL(file), source: "local" };
      chooser.remove(); renderAllReferenceFiles();
    }, { once: true });
    document.body.append(chooser); chooser.click();
  };
  const removeMedia = (kind, index) => {
    const [entry] = state.mediaFiles[kind].splice(index, 1); revokeEntry(entry); renderAllReferenceFiles();
  };
  const updateReferenceAspect = () => {
    const referenceWorkflow = selectedPreset()?.family === "ref2va";
    const imageAvailable = referenceWorkflow
      ? state.mediaFiles.image.length > 0
      : Boolean(firstFrame.files.length || lastFrame.files.length || state.retryRoles.some(role => role === "first" || role === "last"));
    const videoAvailable = referenceWorkflow && state.mediaFiles.video.length > 0;
    imageAspect.disabled = !imageAvailable;
    videoAspect.hidden = !referenceWorkflow;
    videoAspect.disabled = !videoAvailable;
    const invalid = (aspect.value === "reference" || aspect.value === "reference_image") && !imageAvailable || aspect.value === "reference_video" && !videoAvailable;
    if (invalid) aspect.value = "9:16";
  };
  const updateFollowButton = () => {
    const button = $("#follow-video-duration"), entry = state.mediaFiles.video[0];
    const available = selectedPreset()?.family === "ref2va" && Boolean(entry?.file);
    button.disabled = !available;
    button.title = available ? "按参考视频 1 时长取整并限制在 5–15 秒" : "请先选择参考视频 1";
  };
  const clearRetry = () => {
    state.retryRoles = []; state.retryKeepRoles = []; $("#retry-source-id").value = ""; $("#retry-draft").classList.add("hidden"); clearMediaPreviews();
    $("#first-frame-hint").textContent = selectedPreset()?.family === "ref2va" ? "主要参考" : "镜头起点 · 可选";
    $("#last-frame-hint").textContent = selectedPreset()?.family === "ref2va" ? "补充参考" : "镜头终点 · 可选";
    updateReferenceAspect(); updateFollowButton();
  };
  $$(".top-nav button").forEach(button => button.addEventListener("click", () => setView(button.dataset.view)));
  $("#workflow-json").addEventListener("change", async event => {
    const file = event.target.files[0], message = $("#workflow-message");
    if (!file) return;
    try {
      const text = await file.text();
      state.workflowDraft = parseWorkflowFile(text);
      const result = await apiAction("/api/workflows/inspect", { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify(state.workflowDraft) });
      renderWorkflowInspection(result);
      message.className = "form-message"; message.textContent = `已读取 ${result.nodes.length} 个节点，请选择参数和输出。`;
    } catch (error) {
      state.workflowDraft = null; $("#save-workflow").disabled = true;
      message.className = "form-message error"; message.textContent = error.message;
    }
  });
  $("#save-workflow").addEventListener("click", async () => {
    const message = $("#workflow-message"), workflowId = $("#workflow-id").value.trim().toLowerCase(), name = $("#workflow-name").value.trim();
    const parameters = $$('[data-workflow-input]:checked').map(input => {
      const current = JSON.parse(input.dataset.current), control = input.dataset.control;
      let type = typeof current === "boolean" ? "boolean" : (Number.isInteger(current) ? "integer" : (typeof current === "number" ? "number" : "string"));
      const id = `${input.dataset.node}_${input.dataset.input}`.toLowerCase().replace(/[^a-z0-9._-]+/g, "-");
      return { id, node: input.dataset.node, input: input.dataset.input, type, default: current, ui: { label: input.dataset.input, control } };
    });
    const selectedOutput = $('[data-workflow-output]:checked');
    if (!state.workflowDraft || !selectedOutput) return;
    const kind = selectedOutput.dataset.kind, counters = {image:0,video:0,audio:0}, slots = {};
    $$('[data-workflow-media]:checked').forEach(input => { const mediaKind=input.dataset.kind, role=`${mediaKind}_${counters[mediaKind]++}`; slots[role]={node:input.dataset.node,input:input.dataset.input,kind:mediaKind}; });
    const media = Object.keys(slots).length ? {type:"slots",slots} : {type:"none"};
    const config = { id: workflowId, name, parameters, media, outputs: [{ id:"primary", node:selectedOutput.dataset.node, kind, history_keys: kind === "image" ? ["images"] : (kind === "video" ? ["videos","video","files","images"] : ["files"]), primary:true }] };
    try {
      const item = await apiAction("/api/workflows", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({workflow:state.workflowDraft, config}) });
      message.className = "form-message"; message.textContent = `${item.name} 已保存为草稿 r${item.revision}`;
      await loadWorkflows();
    } catch (error) { message.className = "form-message error"; message.textContent = error.message; }
  });
  $("#workflow-package").addEventListener("change", async event => {
    const file = event.target.files[0], message = $("#workflow-message"); if (!file) return;
    try {
      const result = await apiAction("/api/workflows/import", { method:"POST", headers:{"Content-Type":"application/zip"}, body:file });
      message.className = "form-message"; message.textContent = `${result.name} 已导入为草稿`;
      await loadWorkflows();
    } catch (error) { message.className = "form-message error"; message.textContent = error.message; }
  });
  $("#workflow-list").addEventListener("click", async event => {
    const button = event.target.closest("[data-workflow-action]"); if (!button) return;
    const id = button.dataset.id, action = button.dataset.workflowAction;
    try {
      if (action === "enable" || action === "disable") {
        await apiAction(`/api/workflows/${encodeURIComponent(id)}/status`, { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({status: action === "enable" ? "enabled" : "disabled"}) });
        await Promise.all([loadWorkflows(), loadPresets()]);
      } else if (action === "test") {
        if (!window.confirm("测试会真实提交一次 ComfyUI 任务并消耗 GPU，确认继续？")) return;
        const detail = await apiAction(`/api/workflows/${encodeURIComponent(id)}`);
        const values = Object.fromEntries(Object.entries(detail.definition.manifest.parameters || {}).map(([key, spec]) => [key, spec.default]));
        const job = await apiAction(`/api/workflows/${encodeURIComponent(id)}/test`, { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(values) });
        upsertJob(job); setView("jobs");
      } else if (action === "edit") {
        const detail = await apiAction(`/api/workflows/${encodeURIComponent(id)}`);
        state.workflowDraft = detail.definition.workflow;
        $("#workflow-id").value = detail.id;
        $("#workflow-name").value = detail.name;
        const inspection = await apiAction("/api/workflows/inspect", { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(state.workflowDraft) });
        renderWorkflowInspection(inspection);
        $("#workflow-message").className = "form-message";
        $("#workflow-message").textContent = `正在编辑 ${detail.name}；保存会创建新 revision，旧任务仍使用原快照。`;
        $("#workflow-name").scrollIntoView({behavior:"smooth", block:"center"});
      } else if (action === "copy") {
        const newId = window.prompt("新工作流 ID（小写字母、数字、点、下划线或连字符）", `${id}-copy`);
        if (!newId) return;
        const newName = window.prompt("新工作流名称", `${id} 副本`);
        if (!newName) return;
        await apiAction(`/api/workflows/${encodeURIComponent(id)}/copy`, { method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify({id:newId.trim().toLowerCase(), name:newName.trim()}) });
        await loadWorkflows();
      } else if (action === "delete") {
        if (!window.confirm(`删除 ${id}？历史任务不会受影响。`)) return;
        await apiAction(`/api/workflows/${encodeURIComponent(id)}`, {method:"DELETE"});
        await Promise.all([loadWorkflows(), loadPresets()]);
      }
    } catch (error) { window.alert(error.message); }
  });
  $("#refresh-jobs").addEventListener("click", () => loadJobs(true));
  $("#load-more-jobs").addEventListener("click", () => loadJobs(false));
  $("#clear-retry").addEventListener("click", clearRetry);
  $$(".upload-card input").forEach(input => input.addEventListener("change", () => {
    const card = input.closest(".upload-card"), image = $("img", card), file = input.files[0];
    if (image.dataset.objectUrl) URL.revokeObjectURL(image.dataset.objectUrl);
    card.classList.toggle("has-image", Boolean(file));
    if (file) { image.dataset.objectUrl = URL.createObjectURL(file); image.src = image.dataset.objectUrl; } else image.removeAttribute("src");
    updateReferenceAspect();
  }));
  Object.entries(mediaInputs).forEach(([kind, input]) => input.addEventListener("change", () => addSelectedFiles(kind, input)));
  $("#ref2va-media").addEventListener("click", event => {
    const action = event.target.closest("[data-media-action]");
    if (!action) return;
    event.preventDefault(); event.stopPropagation();
    const kind = action.dataset.kind, index = Number(action.dataset.index);
    if (action.dataset.mediaAction === "replace") replaceMedia(kind, index);
    if (action.dataset.mediaAction === "remove") removeMedia(kind, index);
  });
  const durationValue = $("#duration-value"), megapixels = $("#megapixels-value");
  const setDurationValue = () => { durationValue.textContent = `${duration.value} 秒`; };
  duration.addEventListener("input", () => { setDurationValue(); updateLoad(); });
  const updateResolution = value => {
    megapixels.value = value;
    $$("[data-megapixels]").forEach(button => button.setAttribute("aria-pressed", button.dataset.megapixels === String(value)));
    updateLoad();
  };
  $$("[data-megapixels]").forEach(button => button.addEventListener("click", () => updateResolution(button.dataset.megapixels)));
  const updateLoad = () => {
    $("#mp-value").textContent = `${megapixels.value} MP`;
    $("#load-warning").classList.toggle("hidden", Number(megapixels.value) < .8 && Number(duration.value) < 12);
  };
  setDurationValue(); updateResolution(megapixels.value);
  $("#follow-video-duration").addEventListener("click", () => {
    const file = state.mediaFiles.video[0]?.file, message = $("#form-message");
    if (!file) return;
    const probe = document.createElement("video"), url = URL.createObjectURL(file);
    probe.preload = "metadata";
    probe.onloadedmetadata = () => {
      const value = Math.min(15, Math.max(5, Math.round(probe.duration)));
      duration.value = String(value); setDurationValue(); updateLoad(); URL.revokeObjectURL(url); probe.remove();
      message.className = "form-message"; message.textContent = `已按参考视频 1 时长设置为 ${value} 秒`;
    };
    probe.onerror = () => { URL.revokeObjectURL(url); probe.remove(); message.className = "form-message error"; message.textContent = "无法读取参考视频时长，请手动选择 5–15 秒"; };
    probe.src = url; probe.load();
  });
  $("#preset-select").addEventListener("change", event => { applyPreset(event.target.value); updateReferenceAspect(); updateFollowButton(); });

  const buildFormData = () => {
    const data = new FormData(form), retry = Boolean($("#retry-source-id").value);
    if (selectedPreset()?.family === "generic") {
      const values = {};
      $$('[data-generic-binding]', form).forEach(input => {
        let value = input.type === "checkbox" ? input.checked : input.value;
        if (input.dataset.valueType === "integer") value = Number.parseInt(value, 10);
        if (input.dataset.valueType === "number") value = Number(value);
        values[input.dataset.genericBinding] = value;
        data.delete(input.name);
      });
      data.set("values_json", JSON.stringify(values));
      ["prompt", "duration_seconds", "aspect_ratio", "megapixels", "seed", "scheduler", "sampler", "steps"].forEach(name => data.delete(name));
      return data;
    }
    ["ref_images", "ref_videos", "ref_audios", "retry_keep_roles", "image_0", "image_1", "image_2", "image_3", "image_4", "image_5", "image_6", "image_7", "image_8", "video_0", "video_1", "video_2", "audio_0", "audio_1", "audio_2"].forEach(name => data.delete(name));
    const keepRoles = [];
    if (retry) {
      if (selectedPreset()?.family === "ref2va") {
        Object.values(state.mediaFiles).flat().forEach(entry => {
          if (entry.source === "retained") keepRoles.push(entry.role);
          else if (entry.file) data.append(entry.role, entry.file, entry.file.name);
        });
      } else {
        if (!firstFrame.files.length && state.retryRoles.includes("first")) keepRoles.push("first");
        if (!lastFrame.files.length && state.retryRoles.includes("last")) keepRoles.push("last");
      }
      const originalRoles = new Set(state.retryKeepRoles);
      const retryRolesChanged = keepRoles.length !== originalRoles.size || keepRoles.some(role => !originalRoles.has(role));
      const retryUploads = Object.values(state.mediaFiles).flat().some(entry => entry.file);
      if (retryRolesChanged || retryUploads) data.set("retry_keep_roles", JSON.stringify(keepRoles));
    } else {
      for (const [kind, inputName] of [["image", "ref_images"], ["video", "ref_videos"], ["audio", "ref_audios"]]) {
        state.mediaFiles[kind].filter(entry => entry.file).forEach(entry => data.append(inputName, entry.file, entry.file.name));
      }
    }
    return data;
  };

  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (state.isSubmitting) return;
    const message = $("#form-message"), button = $("#submit-button");
    const referenceWorkflow = selectedPreset()?.family === "ref2va";
    const hasImage = referenceWorkflow ? state.mediaFiles.image.length > 0 : Boolean(firstFrame.files.length || lastFrame.files.length || state.retryRoles.some(role => role === "first" || role === "last"));
    const hasVideo = referenceWorkflow && state.mediaFiles.video.length > 0;
    if ((aspect.value === "reference" || aspect.value === "reference_image") && !hasImage || aspect.value === "reference_video" && !hasVideo) {
      message.className = "form-message error"; message.textContent = aspect.value === "reference_video" ? "参考视频 1 画幅需要先上传参考视频" : "参考图 1 画幅需要先上传参考图"; return;
    }
    state.isSubmitting = true;
    message.className = "form-message"; message.textContent = "准备上传…"; button.disabled = true;
    try {
      const currentPreset = $("#preset-select").value;
      const job = await uploadForm("/api/jobs", buildFormData(), progress => {
        const percent = Math.round(progress.loaded * 100 / progress.total);
        message.textContent = `上传中 ${formatBytes(progress.loaded)} / ${formatBytes(progress.total)}（${percent}%） · ${formatDuration(Math.round(progress.elapsed))}`;
      });
      upsertJob(job);
      if (job.status === "failed") { message.className = "form-message error"; message.textContent = `上传完成，但 ComfyUI 提交失败：${job.error_summary || "请检查工作站状态"}`; }
      else { message.textContent = "上传完成，任务已加入生成队列"; }
      form.reset(); $$(".upload-card").forEach(card => card.classList.remove("has-image"));
      $$(".upload-card img").forEach(image => { if (image.dataset.objectUrl) URL.revokeObjectURL(image.dataset.objectUrl); image.removeAttribute("src"); delete image.dataset.objectUrl; });
      clearMediaPreviews(); clearRetry(); applyPreset(currentPreset); setDurationValue(); updateResolution(megapixels.value); updateLoad(); setView("jobs");
    } catch (error) {
      message.className = "form-message error";
      if (error.code === "validation_error") message.textContent = `参数或素材校验失败：${error.message}`;
      else if (error.code === "comfyui_unavailable") message.textContent = `ComfyUI 提交失败：${error.message}`;
      else message.textContent = error.message.includes("上传") || error.message.includes("网络") ? error.message : `提交失败：${error.message}`;
    }
    finally { state.isSubmitting = false; updateSubmitAvailability(); }
  });

  $("#jobs-list").addEventListener("click", async event => {
    const control = event.target.closest("[data-action]"); if (!control) return;
    const { action, id } = control.dataset;
    if (action === "play") { openPlayer(id); return; }
    if (action === "delete" && !window.confirm("确认将这个任务移出历史？本地输入素材和生成视频会保留。")) return;
    control.disabled = true;
    try {
      if (action === "cancel") upsertJob(await apiAction(`/api/jobs/${id}/cancel`, { method: "POST" }));
      if (action === "retry") {
        const draft = await apiAction(`/api/jobs/${id}/retry`, { method: "POST" });
        form.reset(); $$(".upload-card").forEach(card => card.classList.remove("has-image"));
        clearMediaPreviews();
        applyPreset(draft.preset_id, draft);
        form.elements.prompt.value = draft.prompt; form.elements.duration_seconds.value = draft.duration_seconds; setDurationValue();
        form.elements.aspect_ratio.value = draft.aspect_ratio; form.elements.megapixels.value = draft.megapixels;
        updateResolution(String(draft.megapixels));
        form.elements.seed.value = draft.seed; $("#retry-source-id").value = draft.retry_source_id;
        state.retryRoles = draft.input_roles || [];
        state.retryKeepRoles = [...state.retryRoles];
        if (selectedPreset()?.family === "ref2va") {
          state.retryRoles.forEach(role => {
            const kind = mediaKindFromRole(role);
            if (kind) state.mediaFiles[kind].push({ role, source: "retained", file: null, url: null });
          });
          renderAllReferenceFiles();
        }
        const retained = { image: 0, video: 0, audio: 0 };
        state.retryRoles.forEach(role => { const kind = mediaKindFromRole(role); if (kind) retained[kind] += 1; });
        const retainedText = [["image", "图"], ["video", "视频"], ["audio", "音频"]].filter(([kind]) => retained[kind]).map(([kind, label]) => `${retained[kind]}${label}`).join("、");
        $("#retry-draft span").textContent = retainedText ? `已载入原参数，并沿用 ${retainedText}` : "已载入原任务参数";
        $("#retry-draft").classList.remove("hidden");
        if (state.retryRoles.includes("first")) $("#first-frame-hint").textContent = "沿用原任务图片";
        if (state.retryRoles.includes("last")) $("#last-frame-hint").textContent = "沿用原任务图片";
        updateReferenceAspect(); updateLoad(); setView("generate");
      }
      if (action === "delete") { await apiAction(`/api/jobs/${id}`, { method: "DELETE", headers: {"Content-Type":"application/json"}, body: JSON.stringify({confirm:true}) }); removeJob(id); }
    } catch (error) { window.alert(error.message); }
    finally { control.disabled = false; }
  });

  $("#device-actions").addEventListener("click", async event => {
    const control = event.target.closest("[data-control]"); if (!control) return;
    const action = control.dataset.control;
    const activeJobs = [...state.jobs.values()].filter(job => ["submitting", "queued", "running"].includes(job.status)).length;
    const actionLabel = { start: "启动", stop: "关闭", restart: "重启" }[action];
    const warning = action === "start" ? "确认远程启动 ComfyUI？" : `确认${actionLabel} ComfyUI？${activeJobs ? ` 当前有 ${activeJobs} 个未完成任务，操作会中断它们。` : ""}`;
    if (!window.confirm(warning)) return;
    control.disabled = true;
    try {
      await apiAction(`/api/comfyui/control/${action}`, { method: "POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({confirm:true}) });
      await loadMetrics();
      startDeviceMonitor();
    } catch (error) {
      $("#control-message").className = "control-message error";
      $("#control-message").textContent = error.message;
      control.disabled = false;
    }
  });

  $("#video-close").addEventListener("click", closePlayer);
  $("#video-modal").addEventListener("click", event => { if (event.target.id === "video-modal") closePlayer(); });
  document.addEventListener("keydown", event => { if (event.key === "Escape" && !$("#video-modal").classList.contains("hidden")) closePlayer(); });
  document.addEventListener("visibilitychange", () => { if (document.hidden) stopDeviceMonitor(); });

  try { await loadPresets(); } catch (error) { $("#form-message").className = "form-message error"; $("#form-message").textContent = error.message; }
  await Promise.all([loadJobs(), loadMetrics(), loadWorkflows()]); connectEvents();
});
