(() => {
  const baseRenderMetricsRecoveryLite = renderMetrics;
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
      const forceVisible = stateValue === "unresponsive" || operation === "force_restart";
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
