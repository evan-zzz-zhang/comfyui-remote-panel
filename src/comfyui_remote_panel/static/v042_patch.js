(() => {
  const PROMPT_ROW_LABELS = new Set(["提示词", "正面提示词", "prompt", "positive_prompt"]);

  function installStyles() {
    if (document.querySelector("#v042-patch-style")) return;
    const style = document.createElement("style");
    style.id = "v042-patch-style";
    style.textContent = `
      .v042-standardized-prompt-row small { white-space: pre-wrap; word-break: break-word; }
    `;
    document.head.append(style);
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

  function findPromptRow(list) {
    return [...list.querySelectorAll(".settings-row.static")].find(item => {
      const label = item.querySelector("strong")?.textContent.trim();
      return Boolean(label && PROMPT_ROW_LABELS.has(label));
    }) || null;
  }

  function positionStandardizedPromptRow(body) {
    const row = body?.querySelector?.("[data-v042-standardized-prompt-row]");
    const list = row?.closest?.(".settings-list") || inputParameterSection(body)?.querySelector(".settings-list");
    if (!row || !list) return;
    const promptRow = findPromptRow(list);
    if (promptRow && promptRow.nextElementSibling !== row) promptRow.insertAdjacentElement("afterend", row);
  }

  function addStandardizedPromptToTaskDetails(jobId) {
    const job = state.jobs.get(jobId);
    const body = document.querySelector("#sheet-body");
    const standardized = typeof job?.standardized_prompt === "string"
      ? job.standardized_prompt.trim()
      : "";
    if (!body || !standardized) return;

    let row = body.querySelector("[data-v042-standardized-prompt-row]");
    if (!row) {
      const list = ensureInputParameterList(body);
      row = document.createElement("div");
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
      list.prepend(row);
    }

    positionStandardizedPromptRow(body);
    queueMicrotask(() => positionStandardizedPromptRow(body));
    window.requestAnimationFrame(() => positionStandardizedPromptRow(body));
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
      window.setTimeout(syncGenerationSettingsSummary, 0);
    }
    return result;
  };

  document.addEventListener("click", event => {
    const details = event.target.closest?.("[data-task-details]");
    if (!details) return;
    const jobId = details.dataset.taskDetails;
    window.setTimeout(() => addStandardizedPromptToTaskDetails(jobId), 0);
  }, true);

  document.addEventListener("DOMContentLoaded", () => {
    installStyles();
  });
})();
