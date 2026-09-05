(() => {
  const baseApplyPreset = applyPreset;
  const baseLoadWorkflows = loadWorkflows;
  const visibilitySync = new Map();
  let workflowFilter = "all";

  const compactAspectLabel = value => ({
    reference: "参考图",
    reference_image: "参考图",
    reference_video: "参考视频",
  })[value] || value;
  aspectLabel = compactAspectLabel;

  function presetFromWorkflowItem(item) {
    const manifest = item?.manifest || {};
    const family = manifest.family || "generic";
    const parameters = {};
    for (const [name, spec] of Object.entries(manifest.parameters || {})) {
      if (family !== "generic" && (name === "prompt" || name === "seed")) continue;
      parameters[name] = { ...spec };
    }
    const runtime = state.metrics?.presets?.[item.id] || {};
    return {
      id: item.id,
      revision: item.revision,
      name: item.name,
      family,
      description: manifest.description || "",
      available: runtime.available ?? true,
      diagnostics: runtime.diagnostics || [],
      parameters,
      reference_media: manifest.reference_media || null,
      input_bindings: manifest.input_bindings || { media: { type: "none" } },
      output_bindings: manifest.output_bindings || [],
    };
  }

  function ensurePreset(id) {
    if (state.presets.has(id)) return state.presets.get(id);
    const item = state.workflowItems.get(id);
    if (!item || item.status === "draft") return null;
    const preset = presetFromWorkflowItem(item);
    state.presets.set(id, preset);
    const select = $("#preset-select");
    if (select && !select.querySelector(`option[value="${CSS.escape(id)}"]`)) {
      const option = document.createElement("option");
      option.value = id;
      option.textContent = item.name;
      select.append(option);
    }
    return preset;
  }

  function syncCompactCopy() {
    const workflowMeta = $("#workflow-picker-button small");
    if (workflowMeta) workflowMeta.textContent = "";
    const activeLabel = $("#active-preset-label");
    if (activeLabel) activeLabel.textContent = "";
    for (const selector of ["#reference-section-hint", "#prompt-hint", "#first-frame-hint", "#last-frame-hint", "#preset-description"]) {
      const node = $(selector);
      if (node) node.textContent = "";
    }
    const prompt = $('textarea[name="prompt"]');
    if (prompt) prompt.placeholder = "输入提示词……";
    $$('[data-generic-binding="positive_prompt"], [data-generic-binding="prompt"]').forEach(input => {
      if (input.tagName === "TEXTAREA") input.placeholder = "输入提示词……";
    });
    $$('[data-generic-binding="negative_prompt"]').forEach(input => {
      if (input.tagName === "TEXTAREA") input.placeholder = "输入负面提示词……";
    });
    $$(".generic-reference-card small").forEach(node => {
      node.textContent = node.textContent.includes("沿用") ? "沿用上次" : "";
    });
    $$(".negative-prompt summary span").forEach(node => {
      node.textContent = node.textContent.includes("已使用") ? "负面提示词 · 已使用默认值" : "负面提示词";
    });
    syncAspectControls();
    syncGenericAdvancedOrder();
  }

  function syncAspectControls() {
    const select = $('select[name="aspect_ratio"]');
    if (!select) return;
    const image = $("#reference-aspect-image-option");
    const video = $("#reference-aspect-video-option");
    if (image) image.textContent = "参考图";
    if (video) video.textContent = "参考视频";

    const order = ["9:16", "16:9", "1:1", "3:4", "4:3", "21:9"];
    for (const value of order) {
      const option = [...select.options].find(item => item.value === value);
      if (option) select.append(option);
    }
    if (image) select.append(image);
    if (video) select.append(video);
    for (const option of select.options) {
      if (option.value === "2:3" || option.value === "3:2") {
        option.hidden = true;
        select.append(option);
      }
    }
  }

  function genericHasAdvanced(preset) {
    if (!preset || preset.family !== "generic") return false;
    const basic = new Set(["prompt", "positive_prompt", "negative_prompt", "width", "height", "batch_size"]);
    return Object.keys(preset.parameters || {}).some(name => !basic.has(name));
  }

  function syncGenericAdvancedOrder() {
    const root = $("#generic-parameters");
    const basic = $("#basic-settings");
    if (!root || !basic) return;
    const preset = selectedPreset();
    const moved = $(".generic-advanced[data-refined-order='true']");
    if (!preset || preset.family !== "generic") {
      moved?.remove();
      return;
    }
    const fresh = $(".generic-advanced", root);
    if (fresh) {
      if (moved && moved !== fresh) moved.remove();
      fresh.dataset.refinedOrder = "true";
      basic.insertAdjacentElement("afterend", fresh);
      return;
    }
    if (!genericHasAdvanced(preset)) moved?.remove();
  }

  function workflowIsShown(item) {
    return item?.status === "enabled";
  }

  function workflowCategory(item) {
    const manifest = item?.manifest || {};
    if (manifest.family === "fl2va" || manifest.family === "ref2va") return "video";
    const outputs = manifest.output_bindings || [];
    const kind = (outputs.find(output => output.primary) || outputs[0] || {}).kind;
    if (kind === "image") return "image";
    if (kind === "video") return "video";
    return "other";
  }

  function applyWorkflowFilter() {
    for (const card of $$("#workflow-list .workflow-item")) {
      const id = card.querySelector("[data-id]")?.dataset.id;
      const item = id ? state.workflowItems.get(id) : null;
      const category = workflowCategory(item);
      card.hidden = workflowFilter !== "all" && category !== workflowFilter;
    }
  }

  function setupWorkflowFilters() {
    const tabs = $(".workflow-manager-tabs");
    if (!tabs || tabs.dataset.ready === "true") return;
    tabs.dataset.ready = "true";
    tabs.removeAttribute("aria-hidden");
    tabs.setAttribute("role", "tablist");
    tabs.innerHTML = [
      ["all", "全部"],
      ["video", "视频"],
      ["image", "图片"],
    ].map(([value, label], index) => `<button type="button" role="tab" data-workflow-filter="${value}" aria-selected="${index === 0}" class="${index === 0 ? "active" : ""}">${label}</button>`).join("");
    tabs.addEventListener("click", event => {
      const button = event.target.closest("[data-workflow-filter]");
      if (!button) return;
      workflowFilter = button.dataset.workflowFilter;
      for (const tab of $$('[data-workflow-filter]', tabs)) {
        const active = tab === button;
        tab.classList.toggle("active", active);
        tab.setAttribute("aria-selected", String(active));
      }
      applyWorkflowFilter();
    });
  }

  function updateToggle(button, item) {
    if (!button || !item) return;
    const shown = workflowIsShown(item);
    button.classList.toggle("on", shown);
    button.dataset.workflowAction = shown ? "hide" : "show";
    button.setAttribute("aria-pressed", String(shown));
    button.setAttribute("aria-label", `${shown ? "从创作页隐藏" : "在创作页显示"} ${item.name}`);
    button.title = "显示在创作页";
  }

  function refineWorkflowList() {
    for (const button of $$("#workflow-list .toggle-button")) {
      const item = state.workflowItems.get(button.dataset.id);
      if (item) updateToggle(button, item);
    }
    applyWorkflowFilter();
  }

  function visibleFallback(excludeId) {
    const candidates = [...state.presets.values()].filter(preset => {
      if (preset.id === excludeId) return false;
      const item = state.workflowItems.get(preset.id);
      return !item || workflowIsShown(item);
    });
    return candidates.find(preset => preset.id === "h3-fl2va-group") || candidates[0] || null;
  }

  function setLocalWorkflowStatus(id, status) {
    const item = state.workflowItems.get(id);
    if (!item) return;
    item.status = status;
    state.workflowItems.set(id, item);
    const shown = workflowIsShown(item);
    if (shown) ensurePreset(id);

    const selectedId = $("#preset-select")?.value;
    if (!shown && selectedId === id) {
      const fallback = visibleFallback(id);
      if (fallback) applyPreset(fallback.id);
      else {
        $("#preset-select").value = "";
        const picker = $("#workflow-picker-button strong");
        if (picker) picker.textContent = "未选择工作流";
        const submit = $("#submit-button");
        if (submit) submit.disabled = true;
      }
    } else if (shown && !selectedId) {
      applyPreset(id);
    }

    refineWorkflowList();
    filterPickerChoices();
  }

  function syncRecord(id) {
    let record = visibilitySync.get(id);
    if (!record) {
      const item = state.workflowItems.get(id);
      record = { persisted: item?.status || "disabled", desired: item?.status || "disabled", running: false };
      visibilitySync.set(id, record);
    }
    return record;
  }

  async function flushVisibility(id) {
    const record = syncRecord(id);
    if (record.running) return;
    record.running = true;
    for (const button of $$(`#workflow-list .toggle-button[data-id="${CSS.escape(id)}"]`)) button.classList.add("syncing");
    try {
      while (record.persisted !== record.desired) {
        const target = record.desired;
        try {
          const saved = await apiAction(`/api/workflows/${encodeURIComponent(id)}/status`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ status: target }),
            keepalive: true,
          });
          record.persisted = saved.status;
        } catch (error) {
          record.desired = record.persisted;
          setLocalWorkflowStatus(id, record.persisted);
          window.alert(`显示设置保存失败：${error.message}`);
          break;
        }
      }
    } finally {
      record.running = false;
      for (const button of $$(`#workflow-list .toggle-button[data-id="${CSS.escape(id)}"]`)) button.classList.remove("syncing");
    }
  }

  function requestVisibility(id, shown) {
    const item = state.workflowItems.get(id);
    if (!item) return;
    const record = syncRecord(id);
    record.desired = shown ? "enabled" : "disabled";
    setLocalWorkflowStatus(id, record.desired);
    void flushVisibility(id);
  }

  function filterPickerChoices() {
    const root = $("#sheet-body");
    if (!root) return;
    const current = $("#preset-select")?.value;
    for (const button of $$('[data-pick-workflow]', root)) {
      const item = state.workflowItems.get(button.dataset.pickWorkflow);
      if (item && !workflowIsShown(item) && button.dataset.pickWorkflow !== current) button.remove();
    }
  }

  function taskPrompt(job) {
    const values = job?.input_values || job?.values || {};
    return values.positive_prompt ?? values.prompt ?? job?.prompt ?? "";
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

  function addCopyAction(row, value) {
    if (!row || !value || row.querySelector(".detail-copy-button")) return;
    row.classList.add("detail-prompt-row");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "detail-copy-button";
    button.textContent = "复制";
    row.append(button);
    button.addEventListener("click", async () => {
      try {
        await copyText(value);
        button.textContent = "已复制";
      } catch (_) {
        button.textContent = "复制失败";
      }
      window.setTimeout(() => { button.textContent = "复制"; }, 1200);
    });
  }

  function inputParameterSection(body) {
    return [...$$(".sheet-section", body)].find(section => $(".sheet-label", section)?.textContent.trim() === "输入参数") || null;
  }

  function enhanceTaskDetails(jobId) {
    const job = state.jobs.get(jobId);
    const body = $("#sheet-body");
    if (!job || !body) return;

    const promptLabels = {
      prompt: "提示词",
      positive_prompt: "正面提示词",
      negative_prompt: "负面提示词",
    };
    const duplicateLabels = {
      scheduler: "Scheduler",
      sampler: "Sampler",
      steps: "Steps",
      seed: "Seed",
    };
    const summaryLabels = new Set([...$$("#sheet-body > .settings-list:first-child .settings-row strong")].map(node => node.textContent.trim()));
    let promptFound = false;
    const inputSection = inputParameterSection(body);

    if (inputSection) {
      for (const row of [...$$(".settings-row.static", inputSection)]) {
        const strong = $("strong", row);
        const small = $("small", row);
        if (!strong) continue;
        const key = strong.textContent.trim();
        if (promptLabels[key]) {
          promptFound = true;
          strong.textContent = promptLabels[key];
          addCopyAction(row, small?.textContent || "");
          continue;
        }
        const summaryLabel = duplicateLabels[key];
        if (summaryLabel && summaryLabels.has(summaryLabel)) row.remove();
      }
    }

    if (!promptFound) {
      const prompt = taskPrompt(job);
      if (prompt) {
        let section = inputSection;
        let list = section?.querySelector(".settings-list");
        if (!section || !list) {
          section = document.createElement("section");
          section.className = "sheet-section";
          section.innerHTML = '<span class="sheet-label">输入参数</span><div class="settings-list"></div>';
          list = section.querySelector(".settings-list");
          const hideButton = $("#detail-hide-job", body);
          if (hideButton) body.insertBefore(section, hideButton);
          else body.append(section);
        }
        const row = document.createElement("div");
        row.className = "settings-row static detail-prompt-row";
        row.innerHTML = "<span><strong>提示词</strong><small></small></span>";
        row.querySelector("small").textContent = prompt;
        list.prepend(row);
        addCopyAction(row, prompt);
      }
    }

    const section = inputParameterSection(body);
    if (section && !section.querySelector(".settings-row")) section.remove();
  }

  function refreshJobsFromTab() {
    const nav = $("#nav-jobs");
    if (!nav || nav.classList.contains("nav-refreshing")) return;
    nav.classList.add("nav-refreshing");
    Promise.resolve(loadJobs(true)).finally(() => nav.classList.remove("nav-refreshing"));
  }

  applyPreset = function(presetId, overrides = {}) {
    ensurePreset(presetId);
    const result = baseApplyPreset(presetId, overrides);
    queueMicrotask(syncCompactCopy);
    return result;
  };

  loadWorkflows = async function(...args) {
    const result = await baseLoadWorkflows(...args);
    for (const [id, record] of visibilitySync) {
      if (!record.running) continue;
      const item = state.workflowItems.get(id);
      if (item) item.status = record.desired;
    }
    refineWorkflowList();
    return result;
  };

  document.addEventListener("DOMContentLoaded", () => {
    syncCompactCopy();
    setupWorkflowFilters();
    refineWorkflowList();

    document.addEventListener("click", event => {
      const button = event.target.closest("#workflow-list [data-workflow-action]");
      if (!button) return;
      const action = button.dataset.workflowAction;
      if (!["show", "hide", "enable", "disable"].includes(action)) return;
      event.preventDefault();
      event.stopPropagation();
      const shown = action === "show" || action === "enable";
      requestVisibility(button.dataset.id, shown);
    }, true);

    document.addEventListener("click", event => {
      const details = event.target.closest("[data-task-details]");
      if (!details) return;
      window.setTimeout(() => enhanceTaskDetails(details.dataset.taskDetails), 0);
    }, true);

    $("#nav-jobs")?.addEventListener("click", refreshJobsFromTab, true);
    $("#preset-select")?.addEventListener("change", () => queueMicrotask(syncCompactCopy));
    $("#clear-retry")?.addEventListener("click", () => queueMicrotask(syncCompactCopy));

    const generic = $("#generic-parameters");
    if (generic) new MutationObserver(() => queueMicrotask(syncCompactCopy)).observe(generic, { childList: true });
    const sheet = $("#sheet-body");
    if (sheet) new MutationObserver(() => queueMicrotask(filterPickerChoices)).observe(sheet, { childList: true });
    const workflowList = $("#workflow-list");
    if (workflowList) new MutationObserver(() => queueMicrotask(refineWorkflowList)).observe(workflowList, { childList: true });
  });
})();
