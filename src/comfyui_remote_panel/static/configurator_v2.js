(() => {
  const confidenceLabel = value => ({ HIGH: "高", MEDIUM: "中", LOW: "低" })[value] || value || "—";
  const kindLabel = value => ({ image: "图片", video: "视频", audio: "音频", file: "文件" })[value] || value || "未知";
  const modeLabel = value => ({ txt2img: "Text-to-Image", img2img: "Image-to-Image", video: "Video", generic: "通用", unknown: "待确认" })[value] || value;
  const sizeLabel = value => ({ configurable: "可配置", inherit_input: "跟随输入素材", workflow_fixed: "由工作流决定", unknown: "待确认" })[value] || value;
  const batchLabel = value => ({ configurable: "可配置", workflow_fixed: "由工作流决定", unknown: "待确认" })[value] || value;
  const statusClass = value => value === "FAIL" ? "error" : value === "WARN" ? "warning" : "pass";
  const basicSemantics = new Set(["prompt", "positive_prompt", "negative_prompt", "width", "height", "batch_size", "duration", "duration_seconds", "aspect_ratio", "resolution", "megapixels"]);

  function profileForPreset(preset) {
    return state.workflowItems?.get(preset?.id)?.manifest?.capability_profile || null;
  }

  function slugify(value) {
    const slug = String(value || "").toLowerCase().replace(/\.json$/i, "").replace(/[^a-z0-9._-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 64);
    return slug.length >= 2 ? slug : `workflow-${Date.now().toString(36)}`;
  }

  function renderProfile(result) {
    const caps = result.capabilities || {};
    const output = kindLabel(caps.output_type);
    const required = Object.entries(caps.required_media_inputs || {}).map(([kind, count]) => `${count} × ${kindLabel(kind)}`).join("、") || "无";
    return `<section class="v2-analysis-section"><div class="section-heading"><span>基础能力</span><small>置信度 ${escapeHtml(confidenceLabel(result.confidence))}</small></div><div class="settings-list">
      <div class="settings-row static"><span><strong>输出</strong><small>${escapeHtml(output)}</small></span></div>
      <div class="settings-row static"><span><strong>生成模式</strong><small>${escapeHtml(modeLabel(caps.generation_mode))}</small></span></div>
      <div class="settings-row static"><span><strong>必需素材</strong><small>${escapeHtml(required)}</small></span></div>
      <div class="settings-row static"><span><strong>尺寸</strong><small>${escapeHtml(sizeLabel(caps.size_strategy))}</small></span></div>
      <div class="settings-row static"><span><strong>生成数量</strong><small>${escapeHtml(batchLabel(caps.batch_strategy))}</small></span></div>
    </div></section>`;
  }

  function parameterRow(item, manual = false) {
    const confidence = confidenceLabel(item.confidence);
    const source = item.source === "graph" ? "Graph" : item.source === "schema" ? "Schema" : "Heuristic";
    if (manual) {
      return `<label class="workflow-binding v2-manual-binding"><input type="checkbox" data-v2-manual-parameter="${escapeHtml(item.id)}"><span>${escapeHtml(item.label || item.semantic || item.id)}</span><small>${escapeHtml(`${source} · ${confidence}置信度 · ${item.node}.${item.input}`)}</small></label>`;
    }
    return `<div class="semantic-detected"><span>✓</span><div><strong>${escapeHtml(item.label || item.semantic || item.id)}</strong><small>${escapeHtml(`${source} · ${confidence}置信度`)}</small></div></div>`;
  }

  function renderParameters(result) {
    const automatic = (result.parameters || []).filter(item => item.confidence !== "LOW");
    const basics = automatic.filter(item => !item.advanced || basicSemantics.has(item.semantic));
    const advanced = automatic.filter(item => item.advanced && !basicSemantics.has(item.semantic));
    const manual = (result.parameters || []).filter(item => item.confidence === "LOW");
    const basicHtml = basics.length ? basics.map(item => parameterRow(item)).join("") : '<p class="form-message">没有需要暴露的基础参数。</p>';
    const advancedHtml = advanced.length ? advanced.map(item => parameterRow(item)).join("") : '<p class="form-message">没有自动识别的高级参数。</p>';
    const manualHtml = manual.length ? `<details class="semantic-advanced"><summary>高级手动映射 · ${manual.length} 个低置信度候选</summary>${manual.map(item => parameterRow(item, true)).join("")}</details>` : "";
    return `<section class="v2-analysis-section"><div class="section-heading"><span>基础参数</span><small>有才显示</small></div><div class="semantic-summary">${basicHtml}</div></section>
      <section class="v2-analysis-section"><div class="section-heading"><span>高级参数</span><small>Schema 可编辑项</small></div><div class="semantic-summary">${advancedHtml}</div>${manualHtml}</section>`;
  }

  function renderMedia(result) {
    const media = result.media_inputs || [];
    if (!media.length) return `<section class="v2-analysis-section"><div class="section-heading"><span>素材输入</span></div><p class="form-message">该工作流没有远程素材输入。</p></section>`;
    return `<section class="v2-analysis-section"><div class="section-heading"><span>素材输入</span><small>中置信度项请确认用途</small></div>${media.map(item => {
      const locked = item.required ? " checked disabled" : " checked";
      const requirement = item.required ? "必需" : "可选";
      return `<label class="workflow-binding"><input type="checkbox" data-v2-media="${escapeHtml(item.id)}"${locked}><span>${escapeHtml(item.label)} · ${escapeHtml(requirement)}</span><small>${escapeHtml(`${item.class_type} · ${confidenceLabel(item.confidence)}置信度 · ${item.node}.${item.input}`)}</small></label>`;
    }).join("")}</section>`;
  }

  function renderOutputs(result) {
    const outputs = result.outputs || [];
    if (!outputs.length) return `<section class="v2-analysis-section"><div class="section-heading"><span>输出</span></div><p class="form-message error">没有检测到可运行输出。</p></section>`;
    if (outputs.length === 1) return `<section class="v2-analysis-section"><div class="section-heading"><span>输出</span></div><div class="semantic-detected"><span>✓</span><div><strong>${escapeHtml(kindLabel(outputs[0].kind))}输出</strong><small>${escapeHtml(outputs[0].class_type)}</small></div></div><input id="v2-primary-output" type="hidden" value="0"></section>`;
    return `<section class="v2-analysis-section"><label class="field"><span>主要输出 <small>检测到多个候选</small></span><select id="v2-primary-output">${outputs.map((item, index) => `<option value="${index}">${escapeHtml(`${kindLabel(item.kind)} · ${item.class_type}`)}</option>`).join("")}</select></label></section>`;
  }

  function renderPreflight(result) {
    const order = ["json", "nodes", "inputs", "parameters", "outputs", "runtime"];
    const labels = { json: "JSON", nodes: "Nodes", inputs: "Inputs", parameters: "Parameters", outputs: "Outputs", runtime: "Runtime" };
    return `<section class="v2-analysis-section"><div class="section-heading"><span>Workflow Preflight</span></div><div class="settings-list">${order.map(key => {
      const item = result.preflight?.[key] || { status: "WARN", message: "未检查", details: [] };
      const details = (item.details || []).join("；");
      return `<div class="settings-row static v2-preflight ${statusClass(item.status)}"><span><strong>${labels[key]} · ${escapeHtml(item.status)}</strong><small>${escapeHtml(details || item.message || "")}</small></span></div>`;
    }).join("")}</div></section>`;
  }

  function renderConfigurator(result) {
    state.workflowInspection = result;
    const persistedRuntime = state.workflowEditingDetail?.definition?.manifest?.preflight?.runtime;
    const displayResult = persistedRuntime ? {
      ...result,
      preflight: { ...(result.preflight || {}), runtime: persistedRuntime },
    } : result;
    const root = $("#workflow-inspection");
    if (!root) return;
    root.innerHTML = `${renderProfile(displayResult)}${renderMedia(displayResult)}${renderParameters(displayResult)}${renderOutputs(displayResult)}${renderPreflight(displayResult)}`;
    const fatal = Object.entries(result.preflight || {}).some(([key, item]) => key !== "runtime" && item?.status === "FAIL");
    const button = $("#save-workflow");
    if (button) button.disabled = fatal || !(result.outputs || []).length;
  }

  // workflow_ux intentionally exposes this hook globally. Replace only the
  // renderer; file parsing/edit flows keep using the established v0.2 plumbing.
  renderWorkflowInspection = renderConfigurator;

  function selectedParameters(result) {
    const manual = new Set($$("[data-v2-manual-parameter]:checked").map(input => input.dataset.v2ManualParameter));
    return (result.parameters || []).filter(item => item.confidence !== "LOW" || manual.has(item.id));
  }

  function selectedMedia(result) {
    const selected = new Set($$("[data-v2-media]:checked").map(input => input.dataset.v2Media));
    const slots = {};
    for (const item of result.media_inputs || []) {
      if (!selected.has(item.id) && !item.required) continue;
      slots[item.id] = {
        node: item.node,
        input: item.input,
        kind: item.kind,
        required: Boolean(item.required),
        semantic: item.semantic,
        confidence: item.confidence,
        ui: { label: item.label, optional: !item.required, semantic: item.semantic, confidence: item.confidence },
      };
    }
    return Object.keys(slots).length ? { type: "slots", slots } : { type: "none" };
  }

  function selectedOutputs(result) {
    const index = Number($("#v2-primary-output")?.value || 0);
    const item = (result.outputs || [])[index];
    if (!item) return [];
    return [{
      id: "primary", node: item.node, kind: item.kind, primary: true,
      history_keys: item.kind === "image" ? ["images"] : item.kind === "video" ? ["videos", "video", "files", "images"] : item.kind === "audio" ? ["audio", "files"] : ["files"],
    }];
  }

  async function saveConfigurator(event) {
    const button = event.target.closest("#save-workflow");
    if (!button) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    const message = $("#workflow-message");
    const result = state.workflowInspection;
    if (!result || !state.workflowDraft) return;
    const name = $("#workflow-name")?.value.trim();
    if (!name) {
      message.className = "form-message error";
      message.textContent = "请填写显示名称";
      return;
    }
    let id = $("#workflow-id")?.value.trim().toLowerCase() || slugify(name);
    if (!/^[a-z0-9][a-z0-9._-]{1,63}$/.test(id)) id = slugify(id || name);
    $("#workflow-id").value = id;
    const outputs = selectedOutputs(result);
    if (!outputs.length) {
      message.className = "form-message error";
      message.textContent = "请确认主要输出";
      return;
    }
    button.disabled = true;
    try {
      const config = {
        id, name,
        parameters: selectedParameters(result),
        media: selectedMedia(result),
        outputs,
        analysis: {
          capabilities: result.capabilities,
          confidence: result.confidence,
          preflight: result.preflight,
        },
      };
      const item = await apiAction("/api/workflows", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ workflow: state.workflowDraft, config }),
      });
      await apiAction(`/api/workflows/${encodeURIComponent(item.id)}/status`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: "enabled" }),
      });
      message.className = "form-message";
      message.textContent = `${item.name} 已保存并启用`;
      state.workflowEditingDetail = null;
      await Promise.all([loadWorkflows(), loadPresets()]);
    } catch (error) {
      message.className = "form-message error";
      message.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }

  function requiredGenericRoles(preset) {
    if (!preset || preset.family !== "generic") return [];
    const media = preset.input_bindings?.media;
    if (media?.type !== "slots") return [];
    return Object.entries(media.slots || {}).filter(([, slot]) => slot.required === true || slot.ui?.optional === false).map(([role]) => role);
  }

  function missingGenericRoles(preset) {
    const form = $("#job-form");
    const retained = new Set(state.retryRoles || []);
    return requiredGenericRoles(preset).filter(role => {
      const input = form?.elements?.namedItem(role);
      return !(input?.files?.length || retained.has(role));
    });
  }

  const baseUpdateSubmitAvailability = updateSubmitAvailability;
  updateSubmitAvailability = function() {
    baseUpdateSubmitAvailability();
    const preset = selectedPreset();
    const missing = missingGenericRoles(preset);
    if (missing.length) {
      $("#submit-button").disabled = true;
      $("#submit-button").dataset.missingRequiredMedia = missing.join(",");
    } else {
      delete $("#submit-button").dataset.missingRequiredMedia;
    }
  };

  function refineGenericCreation() {
    const preset = selectedPreset();
    if (!preset || preset.family !== "generic") return;
    const profile = profileForPreset(preset);
    const slots = preset.input_bindings?.media?.slots || {};
    for (const [role, slot] of Object.entries(slots)) {
      const card = $(`input[name="${CSS.escape(role)}"]`)?.closest(".generic-reference-card");
      if (!card) continue;
      const required = slot.required === true || slot.ui?.optional === false;
      const strong = $("strong", card);
      const small = $("small", card);
      if (strong && required && !strong.textContent.includes("必需")) strong.textContent = `${strong.textContent} · 必需`;
      if (small && required && !state.retryRoles?.includes(role)) small.textContent = "生成前必须上传";
    }
    const section = $("#generic-parameters .generic-reference .section-heading small");
    if (section) section.textContent = requiredGenericRoles(preset).length ? "含必需输入" : "可选";
    if (profile) {
      const chips = $("#settings-chips");
      if (chips) {
        const values = [];
        if (profile.size_strategy === "inherit_input") values.push("尺寸跟随输入图");
        else if (profile.size_strategy === "workflow_fixed") values.push("尺寸由工作流决定");
        if (profile.batch_strategy === "workflow_fixed") values.push("数量由工作流决定");
        if (values.length) chips.innerHTML = values.map(value => `<span class="settings-chip">${escapeHtml(value)}</span>`).join("");
      }
    }
    updateSubmitAvailability();
  }

  function requiredWorkflowMedia(item) {
    const media = item?.manifest?.input_bindings?.media;
    if (media?.type !== "slots") return [];
    return Object.entries(media.slots || {}).filter(([, slot]) => slot?.required === true || slot?.ui?.optional === false);
  }

  const baseApplyPreset = applyPreset;
  applyPreset = function(presetId, overrides = {}) {
    const result = baseApplyPreset(presetId, overrides);
    queueMicrotask(refineGenericCreation);
    return result;
  };

  document.addEventListener("DOMContentLoaded", () => {
    document.addEventListener("click", saveConfigurator, true);
    const form = $("#job-form");
    form?.addEventListener("change", () => queueMicrotask(updateSubmitAvailability), true);
    form?.addEventListener("input", () => queueMicrotask(updateSubmitAvailability), true);
    form?.addEventListener("submit", event => {
      const preset = selectedPreset();
      const missing = missingGenericRoles(preset);
      if (!missing.length) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      const labels = missing.map(role => preset.input_bindings.media.slots[role]?.ui?.label || role);
      const message = $("#form-message");
      message.className = "form-message error";
      message.textContent = `需要上传：${labels.join("、")}`;
      updateSubmitAvailability();
    }, true);

    // The legacy one-click /test endpoint only carries JSON values. Required
    // media workflows therefore reuse the normal creation form instead of
    // inventing a second upload protocol. The real generation becomes Runtime
    // evidence and will update the persisted preflight result on completion.
    $("#workflow-list")?.addEventListener("click", async event => {
      const button = event.target.closest('[data-workflow-action="test"]');
      if (!button) return;
      const item = state.workflowItems?.get(button.dataset.id);
      const required = requiredWorkflowMedia(item);
      if (!required.length) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      let preset = state.presets.get(button.dataset.id);
      if (!preset) {
        try { await loadPresets(); preset = state.presets.get(button.dataset.id); }
        catch (_) { preset = null; }
      }
      if (!preset) {
        window.alert("请先启用该工作流，再运行需要素材的测试。");
        return;
      }
      applyPreset(preset.id);
      setView("generate");
      const labels = required.map(([role, slot]) => slot?.ui?.label || role);
      const message = $("#form-message");
      message.className = "form-message";
      message.textContent = `运行兼容性测试：请上传${labels.join("、")}后生成。完成结果会写入 Runtime Preflight。`;
      queueMicrotask(updateSubmitAvailability);
    }, true);

    const inspection = $("#workflow-inspection");
    if (inspection) {
      new MutationObserver(() => {
        if (state.workflowInspection?.capabilities && !inspection.querySelector(".v2-analysis-section")) renderConfigurator(state.workflowInspection);
      }).observe(inspection, { childList: true, subtree: false });
    }
    queueMicrotask(refineGenericCreation);
  });
})();