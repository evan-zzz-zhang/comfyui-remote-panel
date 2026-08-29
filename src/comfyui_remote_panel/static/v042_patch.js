(() => {
  const STANDARDIZER_SELECTOR = "[data-v042-prompt-standardization]";

  function installStyles() {
    if (document.querySelector("#v042-patch-style")) return;
    const style = document.createElement("style");
    style.id = "v042-patch-style";
    style.textContent = `
      [data-v042-standardizer-field] .v042-switch { display: none !important; }
      [data-v042-standardizer-switch] { justify-self: end; }
      .v042-standardized-prompt { margin: 0 0 10px; padding: 9px 10px; background: #11140f; border: 1px solid var(--border-soft); border-radius: 9px; }
      .v042-standardized-prompt summary { color: var(--accent); font-size: 11px; font-weight: 650; cursor: pointer; }
      .v042-standardized-prompt p { margin: 7px 0 0; color: var(--text-secondary); font-size: 12px; line-height: 1.55; white-space: pre-wrap; word-break: break-word; }
    `;
    document.head.append(style);
  }

  function syncSwitchButton(field) {
    const checkbox = field.querySelector(`input${STANDARDIZER_SELECTOR}`);
    if (!checkbox) return;
    const legacy = checkbox.closest(".v042-switch");
    if (legacy) legacy.style.setProperty("display", "none", "important");

    let button = field.querySelector("[data-v042-standardizer-switch]");
    if (!button) {
      button = document.createElement("button");
      button.type = "button";
      button.className = "toggle-button";
      button.dataset.v042StandardizerSwitch = "true";
      button.setAttribute("role", "switch");
      button.setAttribute("aria-label", "使用 H3 提示词标准化");
      field.append(button);
      button.addEventListener("click", event => {
        event.preventDefault();
        event.stopPropagation();
        checkbox.checked = !checkbox.checked;
        checkbox.dispatchEvent(new Event("change", { bubbles: true }));
        syncSwitchButton(field);
      });
    }

    const enabled = Boolean(checkbox.checked);
    button.classList.toggle("on", enabled);
    button.setAttribute("aria-checked", enabled ? "true" : "false");
  }

  function syncStandardizerControls() {
    document.querySelectorAll("[data-v042-standardizer-field]").forEach(syncSwitchButton);
  }

  const baseJobCardV042Patch = jobCard;
  jobCard = function(job) {
    const html = baseJobCardV042Patch(job);
    const standardized = typeof job?.standardized_prompt === "string"
      ? job.standardized_prompt.trim()
      : "";
    if (!standardized) return html;
    const block = `<details class="v042-standardized-prompt" open><summary>标准化提示词</summary><p>${escapeHtml(standardized)}</p></details>`;
    return html.replace(/(<p class="job-prompt">[\s\S]*?<\/p>)/, `$1${block}`);
  };

  document.addEventListener("change", event => {
    const checkbox = event.target?.matches?.(`input${STANDARDIZER_SELECTOR}`) ? event.target : null;
    if (checkbox) syncSwitchButton(checkbox.closest("[data-v042-standardizer-field]"));
  });

  document.addEventListener("DOMContentLoaded", () => {
    installStyles();
    syncStandardizerControls();
    const advanced = document.querySelector("#advanced-settings");
    if (advanced) {
      new MutationObserver(() => queueMicrotask(syncStandardizerControls))
        .observe(advanced, { childList: true, subtree: true });
    }
  });
})();
