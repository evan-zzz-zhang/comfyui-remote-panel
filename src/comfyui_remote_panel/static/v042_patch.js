(() => {
  const STANDARDIZER_SELECTOR = "[data-v042-prompt-standardization]";

  function installStyles() {
    if (document.querySelector("#v042-patch-style")) return;
    const style = document.createElement("style");
    style.id = "v042-patch-style";
    style.textContent = `
      [data-v042-standardizer-field] .v042-switch { display: none !important; }
      [data-v042-standardizer-switch] { justify-self: end; }
      .v042-standardized-prompt-row small { white-space: pre-wrap; word-break: break-word; }
    `;
    document.head.append(style);
  }

  function syncSwitchButton(field) {
    const checkbox = field?.querySelector?.(`input${STANDARDIZER_SELECTOR}`);
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

  async function copyText(value) {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value);
      return;
    }
    const input = document.createElement("textarea");
    input.value = value;
    input.style.position = "fixed";
    input.style.opacity = "0";
    document.body.append(input);
    input.select();
    document.execCommand("copy");
    input.remove();
  }

  function inputParameterSection(body) {
    return [...body.querySelectorAll(".sheet-section")].find(section =>
      section.querySelector(".sheet-label")?.textContent.trim() === "输入参数"
    ) || null;
  }

  function ensureInputParameterList(body) {
    let section = inputParameterSection(body);
    let list = section?.querySelector(".settings-list");
    if (section && list) return list;

    section = document.createElement("section");
    section.className = "sheet-section";
    section.innerHTML = '<span class="sheet-label">输入参数</span><div class="settings-list"></div>';
    list = section.querySelector(".settings-list");
    const hideButton = body.querySelector("#detail-hide-job");
    if (hideButton) body.insertBefore(section, hideButton);
    else body.append(section);
    return list;
  }

  function addStandardizedPromptToTaskDetails(jobId) {
    const job = state.jobs.get(jobId);
    const body = document.querySelector("#sheet-body");
    const standardized = typeof job?.standardized_prompt === "string"
      ? job.standardized_prompt.trim()
      : "";
    if (!body || !standardized || body.querySelector("[data-v042-standardized-prompt-row]")) return;

    const list = ensureInputParameterList(body);
    const row = document.createElement("div");
    row.className = "settings-row static detail-prompt-row v042-standardized-prompt-row";
    row.dataset.v042StandardizedPromptRow = "true";
    row.innerHTML = "<span><strong>标准化提示词</strong><small></small></span>";
    row.querySelector("small").textContent = standardized;

    const button = document.createElement("button");
    button.type = "button";
    button.className = "detail-copy-button";
    button.textContent = "复制";
    row.append(button);
    button.addEventListener("click", async () => {
      try {
        await copyText(standardized);
        button.textContent = "已复制";
      } catch (_) {
        button.textContent = "复制失败";
      }
      window.setTimeout(() => { button.textContent = "复制"; }, 1200);
    });

    const promptRow = [...list.querySelectorAll(".settings-row.static")].find(item =>
      item.querySelector("strong")?.textContent.trim() === "提示词"
    );
    if (promptRow) promptRow.insertAdjacentElement("afterend", row);
    else list.prepend(row);
  }

  function syncGenerationSettingsSummary() {
    const preset = selectedPreset();
    if (!preset || !["fl2va", "ref2va"].includes(preset.family)) return;
    const root = document.querySelector("#settings-chips");
    const aspect = document.querySelector('select[name="aspect_ratio"]')?.value;
    const duration = document.querySelector('input[name="duration_seconds"]')?.value;
    const megapixels = document.querySelector("#megapixels-value")?.value;
    if (!root || !aspect || !duration || !megapixels) return;
    root.innerHTML = [aspectLabel(aspect), `${duration} 秒`, `${megapixels} MP`]
      .map(value => `<span class="settings-chip">${escapeHtml(value)}</span>`)
      .join("");
  }

  const baseApiActionV042Patch = apiAction;
  apiAction = async function(path, options = {}) {
    const result = await baseApiActionV042Patch(path, options);
    const method = String(options.method || "GET").toUpperCase();
    if (method === "POST" && /^\/api\/jobs\/[^/]+\/retry$/.test(path)) {
      // The base retry handler restores aspect/duration/MP after applyPreset().
      // Refresh the compact summary on the next task so it reads final values,
      // not the transient reset/default state.
      window.setTimeout(syncGenerationSettingsSummary, 0);
    }
    return result;
  };

  document.addEventListener("change", event => {
    const checkbox = event.target?.matches?.(`input${STANDARDIZER_SELECTOR}`) ? event.target : null;
    if (checkbox) syncSwitchButton(checkbox.closest("[data-v042-standardizer-field]"));
  });

  document.addEventListener("click", event => {
    const details = event.target.closest?.("[data-task-details]");
    if (!details) return;
    const jobId = details.dataset.taskDetails;
    // ux_refinements opens and normalizes the task-detail sheet first.
    // Append the standardized prompt only after that existing structure is ready.
    window.setTimeout(() => addStandardizedPromptToTaskDetails(jobId), 0);
  }, true);

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
