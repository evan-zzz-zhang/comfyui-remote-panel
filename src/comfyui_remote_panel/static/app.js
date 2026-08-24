const state = { jobs: new Map(), presets: new Map(), metrics: null, eventSource: null, retryRoles: [], previewUrls: [], isSubmitting: false, jobsPage: 1, jobsHasMore: false, pollTimer: null, pollDelay: 2000, deviceTimer: null, deviceChecks: 0 };
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
function aspectLabel(value) { return value === "reference" ? "参考图比例" : value; }
function mediaKindFromRole(role) {
  if (role === "first" || role === "last" || role.startsWith("image_")) return "image";
  if (role.startsWith("video_")) return "video";
  if (role.startsWith("audio_")) return "audio";
  return null;
}

function setView(name) {
  $$(".view").forEach(view => view.classList.toggle("active", view.id === `view-${name}`));
  $$(".bottom-nav button").forEach(button => button.classList.toggle("active", button.dataset.view === name));
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
  updateSubmitAvailability();
}

function renderJobs() {
  const jobs = [...state.jobs.values()].sort((a, b) => b.created_at - a.created_at);
  $("#jobs-empty").classList.toggle("hidden", jobs.length > 0);
  $("#jobs-list").innerHTML = jobs.map(jobCard).join("");
  updateJobsSummary();
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
  const wrapper = document.createElement("div");
  wrapper.innerHTML = jobCard(job).trim();
  const card = wrapper.firstElementChild;
  if (existing) existing.replaceWith(card);
  else list.prepend(card);
  updateJobsSummary();
}

function removeJob(id) {
  state.jobs.delete(id);
  $("#jobs-list").querySelector(`[data-job="${CSS.escape(id)}"]`)?.remove();
  updateJobsSummary();
}

function jobCard(job) {
  const active = ["submitting", "queued", "running"].includes(job.status);
  const progress = job.progress_percent ?? (job.status === "succeeded" ? 100 : 0);
  const queueText = job.status === "queued" && job.queue_position ? ` · 第 ${job.queue_position} 位` : "";
  const video = job.has_video ? `<button class="job-preview" data-action="play" data-id="${job.id}" type="button" aria-label="播放视频"><span>▶</span></button>` : "";
  const actions = [];
  if (active) actions.push(`<button data-action="cancel" data-id="${job.id}">取消任务</button>`);
  if (["failed", "cancelled", "interrupted", "succeeded", "output_missing"].includes(job.status)) actions.push(`<button data-action="retry" data-id="${job.id}">载入原参数</button>`);
  if (job.has_video) {
    actions.unshift(`<button class="play" data-action="play" data-id="${job.id}">播放视频</button>`);
    actions.push(`<a href="/api/jobs/${job.id}/video?download=1">下载</a>`);
  }
  if (["failed", "cancelled", "interrupted", "succeeded", "output_missing"].includes(job.status)) actions.push(`<button data-action="delete" data-id="${job.id}">删除</button>`);
  return `<article class="job-card" data-job="${job.id}">
    <div class="job-top"><div><span class="job-time">${formatDate(job.created_at)}</span><h3>${escapeHtml(job.mode)} · ${escapeHtml(aspectLabel(job.aspect_ratio))}</h3></div><span class="job-status ${job.status}">${statusLabels[job.status] || job.status}</span></div>
    <p class="job-prompt">${escapeHtml(job.prompt)}</p>
    <div class="job-meta"><span>${escapeHtml(job.preset_name || job.preset_id)}</span><span>${job.duration_seconds} 秒</span><span>${job.megapixels} MP</span><span>${escapeHtml(job.scheduler)}</span><span>${escapeHtml(job.sampler)}</span><span>${job.steps} 步</span><span>种子 ${job.seed}</span><span>${formatBytes(job.size_bytes)}</span></div>
    ${active || job.status === "succeeded" ? `<div class="job-progress"><div><span>${escapeHtml(job.stage || "等待状态")} ${queueText}</span><b>${progress}% · ${formatDuration(job.elapsed_seconds)}</b></div><div class="progress-track"><i style="width:${Math.min(100, progress)}%"></i></div></div>` : ""}
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
  applyPreset(state.presets.has("h3-fl2va-v4step600") ? "h3-fl2va-v4step600" : result.items[0]?.id);
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
async function loadMetrics() {
  try { const response = await fetch("/api/metrics"); if (response.ok) renderMetrics(await response.json()); } catch (_) {}
}
async function loadNewestJobs() {
  try {
    const response = await fetch("/api/jobs?page=1&page_size=20");
    if (!response.ok) return;
    const result = await response.json();
    result.items.forEach(job => state.jobs.set(job.id, job));
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
    snapshot.jobs.forEach(job => state.jobs.set(job.id, job)); renderJobs(); renderMetrics(snapshot.metrics);
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

document.addEventListener("DOMContentLoaded", async () => {
  const form = $("#job-form"), duration = $("select[name=duration_seconds]"), aspect = $("select[name=aspect_ratio]");
  const firstFrame = $("#first-frame"), lastFrame = $("#last-frame"), referenceOption = $("#reference-aspect-option");
  const refImages = $("#ref-images"), refVideos = $("#ref-videos"), refAudios = $("#ref-audios");
  for (let value = 5; value <= 15; value += 1) duration.insertAdjacentHTML("beforeend", `<option value="${value}">${value} 秒</option>`);
  const updateReferenceAspect = () => {
    const retryHasImage = state.retryRoles.some(role => mediaKindFromRole(role) === "image");
    const available = selectedPreset()?.family === "ref2va"
      ? Boolean(refImages.files.length || retryHasImage)
      : Boolean(firstFrame.files.length || lastFrame.files.length || state.retryRoles.some(role => role === "first" || role === "last"));
    referenceOption.disabled = !available;
    if (!available && aspect.value === "reference") aspect.value = "9:16";
  };
  const clearMediaPreviews = () => {
    state.previewUrls.forEach(url => URL.revokeObjectURL(url)); state.previewUrls = [];
    for (const selector of ("#ref-image-preview #ref-video-preview #ref-audio-preview").split(" ")) {
      const container = $(selector); container.innerHTML = ""; container.classList.add("hidden");
    }
  };
  const renderReferenceFiles = (input, kind, maximum) => {
    const files = [...input.files];
    if (files.length > maximum) {
      input.value = ""; window.alert(`最多选择 ${maximum} 个${kind === "image" ? "图片" : kind === "video" ? "视频" : "音频"}`); return;
    }
    const container = $(`#ref-${kind}-preview`);
    if (kind === "image") {
      state.previewUrls.forEach(url => URL.revokeObjectURL(url)); state.previewUrls = [];
      container.innerHTML = files.map((file, index) => {
        const url = URL.createObjectURL(file); state.previewUrls.push(url);
        return `<div class="media-preview"><img src="${url}" alt="参考图片 ${index + 1}"><span>&lt;Picture ${index + 1}&gt;</span></div>`;
      }).join("");
    } else {
      const tag = kind === "video" ? "Video" : "Audio";
      container.innerHTML = files.map((file, index) => `<div class="media-file-item"><span>${escapeHtml(file.name)}</span><b>&lt;${tag} ${index + 1}&gt; · ${formatBytes(file.size)}</b></div>`).join("");
    }
    container.classList.toggle("hidden", files.length === 0);
    updateReferenceAspect();
  };
  const clearRetry = () => {
    state.retryRoles = []; $("#retry-source-id").value = ""; $("#retry-draft").classList.add("hidden");
    $("#first-frame-hint").textContent = selectedPreset()?.family === "ref2va" ? "主要参考" : "镜头起点 · 可选";
    $("#last-frame-hint").textContent = selectedPreset()?.family === "ref2va" ? "补充参考" : "镜头终点 · 可选";
    updateReferenceAspect();
  };
  $$(".bottom-nav button").forEach(button => button.addEventListener("click", () => setView(button.dataset.view)));
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
  refImages.addEventListener("change", () => renderReferenceFiles(refImages, "image", 9));
  refVideos.addEventListener("change", () => renderReferenceFiles(refVideos, "video", 3));
  refAudios.addEventListener("change", () => renderReferenceFiles(refAudios, "audio", 3));
  const range = $("input[name=megapixels]");
  const updateLoad = () => {
    $("#mp-value").textContent = `${range.value} MP`;
    $("#load-warning").classList.toggle("hidden", Number(range.value) < .8 && Number(duration.value) < 12);
  };
  range.addEventListener("input", updateLoad); duration.addEventListener("change", updateLoad); updateLoad();
  $("#preset-select").addEventListener("change", event => { applyPreset(event.target.value); updateReferenceAspect(); });

  form.addEventListener("submit", async event => {
    event.preventDefault();
    if (state.isSubmitting) return;
    const message = $("#form-message"), button = $("#submit-button");
    const hasReferenceImage = selectedPreset()?.family === "ref2va"
      ? Boolean(refImages.files.length || state.retryRoles.some(role => mediaKindFromRole(role) === "image"))
      : Boolean(firstFrame.files.length || lastFrame.files.length || state.retryRoles.some(role => role === "first" || role === "last"));
    if (aspect.value === "reference" && !hasReferenceImage) {
      message.className = "form-message error"; message.textContent = "参考图比例需要先上传参考图"; return;
    }
    state.isSubmitting = true;
    message.className = "form-message"; message.textContent = "正在安全上传并提交…"; button.disabled = true;
    try {
      const currentPreset = $("#preset-select").value;
      const job = await apiAction("/api/jobs", { method: "POST", body: new FormData(form) });
      upsertJob(job); message.textContent = "任务已加入队列";
      form.reset(); $$(".upload-card").forEach(card => card.classList.remove("has-image"));
      $$(".upload-card img").forEach(image => image.removeAttribute("src"));
      clearMediaPreviews(); clearRetry(); applyPreset(currentPreset); updateLoad(); setView("jobs");
    } catch (error) { message.className = "form-message error"; message.textContent = error.message; }
    finally { state.isSubmitting = false; updateSubmitAvailability(); }
  });

  $("#jobs-list").addEventListener("click", async event => {
    const control = event.target.closest("[data-action]"); if (!control) return;
    const { action, id } = control.dataset;
    if (action === "play") { openPlayer(id); return; }
    if (action === "delete" && !window.confirm("确认删除这个任务的输入、视频和面板记录？此操作无法撤销。")) return;
    control.disabled = true;
    try {
      if (action === "cancel") upsertJob(await apiAction(`/api/jobs/${id}/cancel`, { method: "POST" }));
      if (action === "retry") {
        const draft = await apiAction(`/api/jobs/${id}/retry`, { method: "POST" });
        form.reset(); $$(".upload-card").forEach(card => card.classList.remove("has-image"));
        clearMediaPreviews();
        applyPreset(draft.preset_id, draft);
        form.elements.prompt.value = draft.prompt; form.elements.duration_seconds.value = draft.duration_seconds;
        form.elements.aspect_ratio.value = draft.aspect_ratio; form.elements.megapixels.value = draft.megapixels;
        form.elements.seed.value = draft.seed; $("#retry-source-id").value = draft.retry_source_id;
        state.retryRoles = draft.input_roles || [];
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
    } catch (error) { window.alert(error.message); control.disabled = false; }
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
  await Promise.all([loadJobs(), loadMetrics()]); connectEvents();
});
