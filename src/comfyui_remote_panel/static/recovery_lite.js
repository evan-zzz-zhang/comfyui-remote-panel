(() => {
  const baseRenderMetricsRecoveryLite = renderMetrics;
  const baseJobCardRecoveryLite = jobCard;
  const recoveryStateLabels = {
    online: "在线",
    offline: "离线",
    unresponsive: "无响应",
    starting: "启动中",
    stopping: "停止中",
    start_failed: "启动失败",
  };
  const operationLabels = {
    start: "正在启动",
    stop: "正在关闭",
    restart: "正在重启",
    force_restart: "正在强制重启",
  };
  const failureLabels = {
    cuda_oom: "显存不足（CUDA OOM）。可降低分辨率或时长后重试。",
    missing_model: "工作流缺少所需模型，请在本机检查模型文件。",
    missing_node: "工作流缺少所需自定义节点，请在本机检查 ComfyUI 节点。",
    output_missing: "任务已结束，但未找到预期输出文件。",
    comfyui_disconnected: "ComfyUI 连接异常，当前任务状态无法可靠确认。",
  };
  let buildInfoRecoveryLite = null;

  function stateLabel(comfy) {
    const value = comfy?.state || (comfy?.online ? "online" : "offline");
    return recoveryStateLabels[value] || "离线";
  }

  function ensureForceRestartButton() {
    const actions = $("#device-actions");
    if (!actions) return null;
    let button = actions.querySelector('[data-recovery-control="force_restart"]');
    if (!button) {
      button = document.createElement("button");
      button.type = "button";
      button.className = "danger hidden";
      button.dataset.recoveryControl = "force_restart";
      button.textContent = "强制重启";
      actions.append(button);
    }
    return button;
  }

  function aboutRow() {
    return $("#open-about") || $$("#settings-home .settings-row").find(row =>
      row.querySelector("strong")?.textContent.trim() === "关于"
    ) || null;
  }

  function ensureAboutPage() {
    let page = $("#about-page");
    if (page) return page;
    const view = $("#view-workflows");
    if (!view) return null;
    page = document.createElement("div");
    page.id = "about-page";
    page.className = "hidden";
    page.innerHTML = `
      <div class="page-heading">
        <button id="about-back" class="icon-button back-button" type="button" aria-label="返回设置">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 18-6-6 6-6"/></svg>
        </button>
        <h2>关于</h2>
      </div>
      <div id="about-build-info" class="settings-list">
        <div class="settings-row static"><span><strong>版本</strong><small>正在读取…</small></span></div>
        <div class="settings-row static"><span><strong>分支</strong><small>正在读取…</small></span></div>
        <div class="settings-row static"><span><strong>提交</strong><small>正在读取…</small></span></div>
        <div class="settings-row static"><span><strong>工作区</strong><small>正在读取…</small></span></div>
      </div>`;
    view.append(page);
    $("#about-back", page)?.addEventListener("click", closeAboutPage);
    return page;
  }

  function installAboutEntry() {
    const current = aboutRow();
    if (!current || current.id === "open-about") return current;
    const button = document.createElement("button");
    button.id = "open-about";
    button.type = "button";
    button.className = "settings-row";
    button.innerHTML = `
      <span><strong>关于</strong><small>Comfy Remote 构建与版本信息</small></span>
      <svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg>`;
    current.replaceWith(button);
    button.addEventListener("click", openAboutPage);
    return button;
  }

  function buildIdentity(info) {
    const commit = info?.commit ? String(info.commit).slice(0, 12) : null;
    const branch = info?.branch || (info?.source === "git" ? "detached" : "release");
    return { branch, commit };
  }

  function renderBuildInfo(info) {
    if (!info) return;
    buildInfoRecoveryLite = info;
    const row = installAboutEntry();
    const identity = buildIdentity(info);
    const summary = row?.querySelector("small");
    if (summary) {
      const commitText = identity.commit ? ` · ${identity.commit}` : "";
      summary.textContent = `v${info.version || "未知"} · ${identity.branch}${commitText}`;
    }

    const page = ensureAboutPage();
    const list = $("#about-build-info", page || document);
    if (!list) return;
    const dirty = info.tracked_dirty === true
      ? "本地有已跟踪修改"
      : info.tracked_dirty === false
        ? "干净"
        : "不可用";
    list.innerHTML = `
      <div class="settings-row static"><span><strong>版本</strong><small>Comfy Remote v${escapeHtml(info.version || "未知")}</small></span><span class="row-value">验收版本</span></div>
      <div class="settings-row static"><span><strong>分支</strong><small>${escapeHtml(identity.branch)}</small></span></div>
      <div class="settings-row static"><span><strong>提交</strong><small title="${escapeHtml(info.commit || "")}">${escapeHtml(identity.commit || "Git 提交信息不可用")}</small></span></div>
      <div class="settings-row static"><span><strong>工作区</strong><small>${escapeHtml(dirty)}</small></span></div>`;
  }

  async function loadBuildInfo() {
    try {
      const response = await fetch("/api/about");
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      renderBuildInfo(await response.json());
    } catch (_) {
      const row = installAboutEntry();
      const summary = row?.querySelector("small");
      if (summary) summary.textContent = "构建信息读取失败";
      const page = ensureAboutPage();
      const list = $("#about-build-info", page || document);
      if (list) list.innerHTML = '<p class="form-message error">无法读取当前构建信息。</p>';
    }
  }

  function openAboutPage() {
    const home = $("#settings-home");
    const page = ensureAboutPage();
    if (!home || !page) return;
    home.classList.add("hidden");
    page.classList.remove("hidden");
    if (buildInfoRecoveryLite) renderBuildInfo(buildInfoRecoveryLite);
    else loadBuildInfo();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  function closeAboutPage() {
    $("#about-page")?.classList.add("hidden");
    $("#settings-home")?.classList.remove("hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  jobCard = function jobCardRecoveryLite(job) {
    const friendly = failureLabels[job?.error_category]
      || (job?.error_category === "interrupted" && job?.status === "interrupted"
        ? "任务执行过程中被中断。"
        : null);
    return baseJobCardRecoveryLite(friendly ? { ...job, error_summary: friendly } : job);
  };

  renderControl = function renderControlRecoveryLite(comfy) {
    const control = comfy.control || { enabled: false };
    const stateValue = comfy.state || control.state || (comfy.online ? "online" : "offline");
    const operation = control.operation;
    const forceButton = ensureForceRestartButton();

    $("#control-state").textContent = operation
      ? (operationLabels[operation] || "处理中")
      : stateLabel({ ...comfy, state: stateValue });

    $$('[data-control]', $("#device-actions")).forEach(button => {
      const action = button.dataset.control;
      button.disabled = !control.enabled || Boolean(operation) || !control[`can_${action}`];
    });

    if (forceButton) {
      const forceVisible = Boolean(control.can_force_restart)
        || stateValue === "unresponsive"
        || operation === "force_restart";
      forceButton.classList.toggle("hidden", !forceVisible);
      forceButton.disabled = !control.enabled || Boolean(operation) || !control.can_force_restart;
    }

    const message = $("#control-message");
    if (control.last_error) {
      message.className = "control-message error";
      message.textContent = control.last_error;
    } else if (operation) {
      message.className = "control-message";
      message.textContent = `${operationLabels[operation] || "正在处理"}，请不要重复操作…`;
    } else if (!control.enabled) {
      message.className = "control-message";
      message.textContent = "需要在本机配置固定启动命令后才能使用。";
    } else if (stateValue === "unresponsive") {
      message.className = "control-message error";
      message.textContent = "ComfyUI 进程仍在运行，但 API 无法正常响应。可以尝试强制重启。";
    } else if (stateValue === "online") {
      message.className = "control-message";
      message.textContent = "ComfyUI 在线，可正常使用。";
    } else {
      message.className = "control-message";
      message.textContent = "ComfyUI 离线，可以远程启动。";
    }
  };

  renderMetrics = function renderMetricsRecoveryLite(metrics) {
    baseRenderMetricsRecoveryLite(metrics);
    if (!metrics) return;
    const panel = metrics.panel || { online: true, state: "online" };
    const comfy = metrics.comfyui || {};
    const pill = $("#connection-pill");
    pill.className = `status-pill ${panel.online === false ? "status-offline" : "status-online"}`;
    pill.innerHTML = `<span></span>${panel.online === false ? "Panel 离线" : "Panel 在线"}`;

    const comfyState = comfy.state || (comfy.online ? "online" : "offline");
    const comfyClass = comfyState === "online" ? "online" : "";
    const version = comfy.online && comfy.version ? ` · ${escapeHtml(comfy.version)}` : "";
    $("#device-overview").innerHTML = `
      <div class="device-chip online"><small>REMOTE PANEL</small><strong>在线</strong></div>
      <div class="device-chip ${comfyClass}"><small>COMFYUI</small><strong>${escapeHtml(recoveryStateLabels[comfyState] || "离线")}${version}</strong></div>
      <div class="device-chip"><small>队列任务</small><strong>${comfy.queue_count ?? "—"}</strong></div>`;
  };

  document.addEventListener("DOMContentLoaded", () => {
    ensureForceRestartButton();
    installAboutEntry();
    ensureAboutPage();
    loadBuildInfo();
    $("#device-actions")?.addEventListener("click", async event => {
      const control = event.target.closest('[data-recovery-control="force_restart"]');
      if (!control) return;
      const activeJobs = [...state.jobs.values()].filter(job =>
        ["submitting", "queued", "running"].includes(job.status)
      ).length;
      const jobWarning = activeJobs
        ? ` 当前有 ${activeJobs} 个未完成任务，这些任务会被中断。`
        : "";
      const warning = `强制重启会结束已安全确认的 ComfyUI 进程及其子进程。${jobWarning} 确认继续？`;
      if (!window.confirm(warning)) return;

      control.disabled = true;
      const message = $("#control-message");
      message.className = "control-message";
      message.textContent = "正在安全确认并强制重启 ComfyUI…";
      try {
        await apiAction("/api/comfyui/control/force_restart", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ confirm: true }),
        });
        await loadMetrics();
        startDeviceMonitor();
      } catch (error) {
        message.className = "control-message error";
        message.textContent = error.message;
        control.disabled = false;
      }
    });
  });
})();
