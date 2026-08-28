(() => {
  function t(text) {
    return window.ComfyI18n?.t?.(text) || text;
  }

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
