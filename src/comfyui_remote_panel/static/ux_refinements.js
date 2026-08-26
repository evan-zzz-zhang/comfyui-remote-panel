(() => {
  const baseApplyPreset = applyPreset;
  const baseLoadWorkflows = loadWorkflows;
  const visibilitySync = new Map();

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
  }

  function syncAspectControls() {
    const select = $('select[name="aspect_ratio"]');
    if (!select) return;
    for (const option of select.options) {
      if (option.value === "2:3" || option.value === "3:2") option.hidden = true;
    }
    const image = $("#reference-aspect-image-option");
    const video = $("#reference-aspect-video-option");
    if (image) image.textContent = "参考图";
    if (video) video.textContent = "参考视频";
  }

  function workflowIsShown(item) {
    return item?.status === "enabled";
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
  }

  function visibleFallback(excludeId) {
    const candidates = [...state.presets.values()].filter(preset => {
      if (preset.id === excludeId) return false;
      const item = state.workflowItems.get(preset.id);
      return !item || workflowIsShown(item);
    });
    return candidates.find(preset => preset.id === "h3-fl2va-v4step600") || candidates[0] || null;
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

    $("#preset-select")?.addEventListener("change", () => queueMicrotask(syncCompactCopy));
    $("#clear-retry")?.addEventListener("click", () => queueMicrotask(syncCompactCopy));

    const generic = $("#generic-parameters");
    if (generic) new MutationObserver(() => queueMicrotask(syncCompactCopy)).observe(generic, { childList: true });
    const sheet = $("#sheet-body");
    if (sheet) new MutationObserver(() => queueMicrotask(filterPickerChoices)).observe(sheet, { childList: true });
  });
})();
