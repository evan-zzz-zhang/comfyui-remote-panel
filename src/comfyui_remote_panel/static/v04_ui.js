(() => {
  // i18n.js owns dynamic translation with a page-wide MutationObserver. Its
  // language status controls used to be updated from inside that observer,
  // which made the observer trigger itself forever on mobile browsers.
  // Detach those two controls from the legacy observer-owned selectors before
  // DOMContentLoaded, then manage them explicitly here.
  const languageToggle = document.querySelector("#language-toggle");
  const languageValue = document.querySelector("#language-value");
  if (languageToggle) languageToggle.id = "language-toggle-v04";
  if (languageValue) languageValue.id = "language-value-v04";

  function t(text) {
    return window.ComfyI18n?.t?.(text) || text;
  }

  function syncLanguageUi() {
    const language = window.ComfyI18n?.language || "zh-CN";
    const value = document.querySelector("#language-value-v04");
    const toggle = document.querySelector("#language-toggle-v04");
    const valueText = language === "zh-CN" ? "简体中文" : "English";
    const labelText = language === "zh-CN" ? "切换到 English" : "Switch to 简体中文";
    if (value && value.textContent !== valueText) value.textContent = valueText;
    if (toggle && toggle.getAttribute("aria-label") !== labelText) toggle.setAttribute("aria-label", labelText);
  }

  document.addEventListener("DOMContentLoaded", () => {
    const toggle = document.querySelector("#language-toggle-v04");
    syncLanguageUi();
    toggle?.addEventListener("click", () => {
      const current = window.ComfyI18n?.language || "zh-CN";
      window.ComfyI18n?.setLanguage?.(current === "zh-CN" ? "en" : "zh-CN");
    });
    window.addEventListener("comfy-language-changed", syncLanguageUi);
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
