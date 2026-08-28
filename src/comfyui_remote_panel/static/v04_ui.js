(() => {
  const V04_EN = {
    "面板在线": "Panel online",
    "面板离线": "Panel offline",
    "未知": "Unknown",
    "Seed 策略": "Seed policy",
    "固定": "Fixed",
    "递增": "Increment",
    "起始 Seed": "Starting seed",
    "保持原图": "Keep original",
    "参考图分辨率": "Reference image resolution",
    "全部参考图": "All reference images",
    "参考图": "Reference image",
    "首帧分辨率": "First-frame resolution",
    "尾帧分辨率": "Last-frame resolution",
    "只降低进入 Workflow 的参考图像素，不裁剪、不放大小图。": "Only reduce reference-image pixels before the workflow; never crop or upscale.",
    "创作默认值": "Creation defaults",
    "默认 Seed 策略": "Default seed policy",
    "可在创作页临时覆盖": "Can be overridden on the Create page",
    "保守保持原图": "Conservatively keep the original",
    "普通参考图可安全使用自动缩放": "Ordinary reference images can use automatic downscaling",
    "像素级或控制类输入默认保持原图": "Pixel-linked or control inputs keep the original by default",
    "用途无法可靠确认，默认保持原图": "Unknown image inputs keep the original by default",
    "img2img 源图缩放可能同时改变生成尺寸": "Downscaling an img2img source may also change output dimensions",
    "该输入用途不明确或存在像素级关联，默认保持原图": "This input is unknown or pixel-linked, so the original is kept by default"
  };

  const TARGET_SELECTOR = ".v04-control, .v04-configurator, .job-meta, #device-overview, #connection-pill";
  const textSources = new WeakMap();

  function language() {
    return window.ComfyI18n?.language || document.documentElement.lang || "zh-CN";
  }

  function eligibleTextNode(node) {
    if (!node || node.nodeType !== Node.TEXT_NODE) return false;
    return Boolean(node.parentElement?.closest(TARGET_SELECTOR));
  }

  function translateTextNode(node) {
    if (!eligibleTextNode(node)) return;
    const current = node.nodeValue || "";
    let source = textSources.get(node);
    if (source == null) {
      source = current;
      textSources.set(node, source);
    } else if (language() === "zh-CN" && current !== source && V04_EN[source] !== current) {
      source = current;
      textSources.set(node, source);
    }
    const trimmed = source.trim();
    if (!trimmed) return;
    const translated = language() === "zh-CN" ? trimmed : (V04_EN[trimmed] || window.ComfyI18n?.t?.(trimmed) || trimmed);
    if (translated === trimmed && source === current) return;
    const prefix = source.match(/^\s*/)?.[0] || "";
    const suffix = source.match(/\s*$/)?.[0] || "";
    node.nodeValue = `${prefix}${translated}${suffix}`;
  }

  function translateTarget(root) {
    if (!root) return;
    if (root.nodeType === Node.TEXT_NODE) {
      translateTextNode(root);
      return;
    }
    if (root.nodeType !== Node.ELEMENT_NODE) return;
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) translateTextNode(node);
  }

  function translateRelevant(root = document.body) {
    if (!root) return;
    if (root.nodeType === Node.TEXT_NODE) {
      translateTextNode(root);
      return;
    }
    if (root.nodeType !== Node.ELEMENT_NODE) return;

    const targets = new Set();
    if (root.matches?.(TARGET_SELECTOR)) targets.add(root);
    const ancestor = root.closest?.(TARGET_SELECTOR);
    if (ancestor) targets.add(ancestor);
    root.querySelectorAll?.(TARGET_SELECTOR).forEach(node => targets.add(node));
    targets.forEach(translateTarget);
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
        pill.innerHTML = `<span></span>${panel.online ? "面板在线" : "面板离线"}`;
      }

      const stateLabels = {
        online: "在线",
        starting: "正在启动",
        offline: "离线",
        unknown: "未知"
      };
      const comfyState = comfy.state || (comfy.online ? "online" : "unknown");
      const comfyLabel = stateLabels[comfyState] || comfyState;
      const overview = document.querySelector("#device-overview");
      if (overview) {
        overview.innerHTML = `<div class="device-chip ${panel.online ? "online" : ""}"><small>PANEL</small><strong>${panel.online ? "在线" : "离线"}</strong></div><div class="device-chip ${comfyState === "online" ? "online" : ""}"><small>COMFYUI</small><strong>${escapeHtml(comfyLabel)}${comfyState === "online" && comfy.version ? ` · ${escapeHtml(comfy.version)}` : ""}</strong></div><div class="device-chip"><small>队列任务</small><strong>${comfy.queue_count ?? "—"}</strong></div>`;
      }
      translateRelevant(pill);
      translateRelevant(overview);
    };
  }

  document.addEventListener("DOMContentLoaded", () => {
    translateRelevant(document.body);
    const observer = new MutationObserver(records => {
      const roots = new Set();
      for (const record of records) {
        for (const node of record.addedNodes || []) {
          if (node.nodeType === Node.TEXT_NODE) {
            if (eligibleTextNode(node)) roots.add(node);
          } else if (node.nodeType === Node.ELEMENT_NODE) {
            const relevant = node.matches?.(TARGET_SELECTOR)
              || node.closest?.(TARGET_SELECTOR)
              || node.querySelector?.(TARGET_SELECTOR);
            if (relevant) roots.add(node);
          }
        }
      }
      roots.forEach(translateRelevant);
    });
    observer.observe(document.body, { subtree: true, childList: true });
  });

  window.addEventListener("comfy-language-changed", () => translateRelevant(document.body));
})();
