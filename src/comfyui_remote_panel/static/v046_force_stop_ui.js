(() => {
  if (typeof renderControl !== "function") return;

  const baseRenderControlV046ForceStop = renderControl;

  function stopButton() {
    return document.querySelector('[data-control="stop"], [data-v046-force-stop]');
  }

  function restoreNormalStopButton() {
    const button = stopButton();
    if (!button) return null;
    delete button.dataset.v046ForceStop;
    button.dataset.control = "stop";
    button.textContent = "关闭";
    return button;
  }

  renderControl = function(comfy) {
    restoreNormalStopButton();
    baseRenderControlV046ForceStop(comfy);

    const control = comfy?.control || { enabled: false };
    if (control.operation === "force_stop") {
      const stateLabel = document.querySelector("#control-state");
      const message = document.querySelector("#control-message");
      if (stateLabel) stateLabel.textContent = "正在强制关闭";
      if (message) {
        message.className = "control-message";
        message.textContent = "正在强制关闭 ComfyUI，请不要重复操作…";
      }
    }

    const button = stopButton();
    if (!button) return;

    const verifiedUnmanaged = Boolean(control.verified_process_alive) && !control.managed_process_alive;
    if (!verifiedUnmanaged) return;

    delete button.dataset.control;
    button.dataset.v046ForceStop = "true";
    button.textContent = "强制关闭";
    button.disabled = !control.enabled || Boolean(control.operation) || !control.can_force_stop;

    const message = document.querySelector("#control-message");
    if (message && !control.last_error && !control.operation) {
      message.className = "control-message";
      message.textContent = comfy?.online
        ? "当前 ComfyUI 没有 Panel 进程记录；已安全识别监听进程，可强制关闭。"
        : "ComfyUI API 无响应，但已安全识别监听进程，可强制关闭。";
    }
  };

  document.addEventListener("click", async event => {
    const button = event.target.closest?.("[data-v046-force-stop]");
    if (!button) return;
    event.preventDefault();
    event.stopImmediatePropagation();

    const activeJobs = [...(state.jobs?.values?.() || [])]
      .filter(job => ["submitting", "queued", "running"].includes(job.status)).length;
    const warning = `确认强制关闭 ComfyUI？${activeJobs ? ` 当前有 ${activeJobs} 个未完成任务，会被中断。` : ""} 面板只会结束与当前启动配置匹配、且正在监听当前 ComfyUI 端口的唯一进程及其子进程。`;
    if (!window.confirm(warning)) return;

    button.disabled = true;
    try {
      await apiAction("/api/comfyui/control/force_stop", {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({confirm: true}),
      });
      await loadMetrics();
      startDeviceMonitor();
    } catch (error) {
      const message = document.querySelector("#control-message");
      if (message) {
        message.className = "control-message error";
        message.textContent = error.message;
      }
      button.disabled = false;
    }
  }, true);
})();