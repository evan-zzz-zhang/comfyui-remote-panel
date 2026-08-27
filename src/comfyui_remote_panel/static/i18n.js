(() => {
  const STORAGE_KEY = "comfy-remote-language";
  const SUPPORTED = new Set(["en", "zh-CN"]);

  const EN = {
    "连接中": "Connecting",
    "打开设置": "Open settings",
    "主导航": "Main navigation",
    "创作": "Create",
    "任务": "Jobs",
    "设备": "Device",
    "工作流加载中": "Loading workflow",
    "已载入上次任务": "Previous job loaded",
    "清除": "Clear",
    "工作流": "Workflow",
    "加载中": "Loading",
    "正在读取可用工作流": "Reading available workflows",
    "参考素材": "Reference media",
    "首帧预览": "First-frame preview",
    "尾帧预览": "Last-frame preview",
    "首帧": "First frame",
    "尾帧": "Last frame",
    "可选": "Optional",
    "添加参考": "Add reference",
    "图片 / 视频 / 音频": "Image / Video / Audio",
    "图片": "Image",
    "视频": "Video",
    "音频": "Audio",
    "提示词中可使用 ": "You can use ",
    " 指代对应素材。": " to refer to the matching media in the prompt.",
    "提示词": "Prompt",
    "正面提示词": "Positive prompt",
    "负面提示词": "Negative prompt",
    "描述画面、动作、镜头与声音": "Describe the scene, action, camera, and sound",
    "输入提示词……": "Enter a prompt…",
    "生成设置": "Generation settings",
    "调整": "Adjust",
    "时长": "Duration",
    "跟随参考视频 1": "Match reference video 1",
    "画幅": "Aspect ratio",
    "参考图": "Reference image",
    "参考视频": "Reference video",
    "参考音频": "Reference audio",
    "分辨率": "Resolution",
    "当前组合负载较高，可能耗时较久或显存不足。": "This combination is heavy and may take longer or run out of VRAM.",
    "高级设置": "Advanced settings",
    "调度器": "Scheduler",
    "采样器": "Sampler",
    "迭代步数": "Steps",
    "种子": "Seed",
    "随机": "Random",
    "生成": "Generate",
    "刷新任务": "Refresh jobs",
    "还没有任务": "No jobs yet",
    "从“创作”页开始第一次生成。": "Start your first generation from Create.",
    "加载更多任务": "Load more jobs",
    "设置": "Settings",
    "关闭设置": "Close settings",
    "管理生成工作流、导入和显示名称": "Manage workflows, imports, and display names",
    "连接": "Connection",
    "Tailscale / 本地访问": "Tailscale / local access",
    "当前配置": "Current configuration",
    "日志与诊断": "Logs & diagnostics",
    "运行日志与故障信息": "Runtime logs and diagnostics",
    "设备页": "Device page",
    "关于": "About",
    "语言": "Language",
    "语言 / Language": "Language",
    "简体中文": "Simplified Chinese",
    "返回设置": "Back to settings",
    "全部": "All",
    "导入工作流": "Import workflow",
    "导入 API Workflow": "Import API Workflow",
    "Schema + Graph 分析；不确定项再由你确认": "Schema + Graph analysis; you confirm uncertain items",
    "关闭导入": "Close import",
    "显示名称": "Display name",
    "例如：WAI 出图": "Example: WAI Image",
    "工作流 ID": "Workflow ID",
    "自动生成": "Generated automatically",
    "选择 API Workflow JSON": "Select API Workflow JSON",
    "请使用 ComfyUI 的“导出（API）”": "Use ComfyUI Export (API)",
    "保存并启用": "Save and enable",
    "导入 Remote Workflow Package": "Import Remote Workflow Package",
    "选择 ZIP": "Select ZIP",
    "不得包含模型、素材、本地路径或密钥": "Must not contain models, media, local paths, or secrets",
    "工作站": "Workstation",
    "远程启动、重启或关闭": "Remote start, restart, or stop",
    "检查中": "Checking",
    "启动": "Start",
    "重启": "Restart",
    "关闭": "Stop",
    "暂不可用": "Unavailable",
    "显存": "VRAM",
    "温度": "Temperature",
    "功耗": "Power",
    "系统内存": "System memory",
    "存储": "Storage",
    "面板文件": "Panel files",
    "面板运行": "Panel uptime",
    "视频预览": "Video preview",
    "关闭视频": "Close video",
    "提交中": "Submitting",
    "排队中": "Queued",
    "生成中": "Running",
    "已完成": "Completed",
    "失败": "Failed",
    "已取消": "Cancelled",
    "意外中断": "Interrupted",
    "输出缺失": "Output missing",
    "删除中": "Deleting",
    "参考图 1 画幅": "Reference image 1 aspect",
    "参考视频 1 画幅": "Reference video 1 aspect",
    "通用 ComfyUI 工作流": "Generic ComfyUI workflow",
    "参考图 1": "Reference image 1",
    "参考图 2": "Reference image 2",
    "主要参考": "Primary reference",
    "补充参考": "Additional reference",
    "镜头起点 · 可选": "Shot start · optional",
    "镜头终点 · 可选": "Shot end · optional",
    "参考图 1 画幅（需参考图）": "Reference image 1 aspect (image required)",
    "参考图比例（需参考图）": "Reference image aspect (image required)",
    "取消任务": "Cancel job",
    "载入原参数": "Load original settings",
    "播放视频": "Play video",
    "下载": "Download",
    "移出历史": "Remove from history",
    "等待状态": "Waiting",
    "工作站在线": "Workstation online",
    "工作站离线": "Workstation offline",
    "在线": "Online",
    "离线": "Offline",
    "队列任务": "Queued jobs",
    "不可用": "Unavailable",
    "正在启动": "Starting",
    "正在关闭": "Stopping",
    "正在重启": "Restarting",
    "已就绪": "Ready",
    "未配置": "Not configured",
    "需要在本机配置固定启动命令后才能使用。": "Configure a fixed local launch command before using this control.",
    "服务在线，可关闭或重启。": "Service is online and can be stopped or restarted.",
    "服务离线，可以远程启动。": "Service is offline and can be started remotely.",
    "工作流列表加载失败": "Failed to load workflows",
    "无法加载工作流管理列表": "Failed to load workflow manager",
    "编辑": "Edit",
    "删除": "Delete",
    "内置工作流": "Bundled workflow",
    "自定义工作流": "Custom workflow",
    "禁用": "Disable",
    "启用": "Enable",
    "测试": "Test",
    "复制": "Copy",
    "导出": "Export",
    "选择手机端可修改参数": "Choose parameters editable on mobile",
    "没有可安全暴露的字面输入。": "No literal inputs can be safely exposed.",
    "选择媒体上传槽位": "Choose media upload slots",
    "没有检测到固定媒体加载节点。": "No fixed media loader nodes detected.",
    "选择主要输出": "Choose primary output",
    "未自动找到输出节点，请在 ComfyUI 中加入 SaveImage 或 SaveVideo。": "No output node was detected automatically. Add SaveImage or SaveVideo in ComfyUI.",
    "任务列表加载失败": "Failed to load jobs",
    "请求失败": "Request failed",
    "上传连接失败，请检查网络后重试": "Upload connection failed. Check the network and retry.",
    "上传已取消": "Upload cancelled",
    "替换": "Replace",
    "已保留素材": "Retained media",
    "已保留": "Retained",
    "请先选择参考视频 1": "Select reference video 1 first",
    "按参考视频 1 时长取整并限制在 5–15 秒": "Round to reference video 1 duration and clamp to 5–15 seconds",
    "无法读取参考视频时长，请手动选择 5–15 秒": "Could not read reference video duration. Choose 5–15 seconds manually.",
    "测试会真实提交一次 ComfyUI 任务并消耗 GPU，确认继续？": "The test submits a real ComfyUI job and uses the GPU. Continue?",
    "新工作流 ID（小写字母、数字、点、下划线或连字符）": "New workflow ID (lowercase letters, numbers, dots, underscores, or hyphens)",
    "新工作流名称": "New workflow name",
    "准备上传…": "Preparing upload…",
    "请检查工作站状态": "Check workstation status",
    "上传完成，任务已加入生成队列": "Upload complete. Job added to the generation queue.",
    "确认将这个任务移出历史？本地输入素材和生成视频会保留。": "Remove this job from history? Local input media and generated files will be kept.",
    "已载入原任务参数": "Original job settings loaded",
    "沿用原任务图片": "Using image from original job",
    "确认远程启动 ComfyUI？": "Start ComfyUI remotely?",
    "宽度": "Width",
    "高度": "Height",
    "生成数量": "Batch count",
    "其他": "Other",
    "视频 · 首尾帧生成": "Video · first/last frame",
    "视频 · 参考生成": "Video · reference generation",
    "图片 · ComfyUI 工作流": "Image · ComfyUI workflow",
    "视频 · ComfyUI 工作流": "Video · ComfyUI workflow",
    "自定义": "Custom",
    "未重新选择时沿用上次素材": "Keep previous media unless replaced",
    "添加参考素材": "Add reference media",
    "描述想生成的内容": "Describe what you want to generate",
    "描述画面、主体、风格和细节……": "Describe the scene, subject, style, and details…",
    "不希望出现的内容……": "Things you do not want to appear…",
    "这些参数来自手动映射，通常无需修改。": "These parameters come from manual mapping and usually do not need changes.",
    "描述主体、动作、镜头运动、对白和声音……": "Describe subject, action, camera movement, dialogue, and sound…",
    "描述参考主体如何运动、镜头变化、对白和声音……": "Describe how the reference subject moves, camera changes, dialogue, and sound…",
    "纯文字或首尾帧生成": "Text-only or first/last-frame generation",
    "可引用 Picture / Video / Audio": "Can reference Picture / Video / Audio",
    "首帧、尾帧均可选": "First and last frames are optional",
    "最多 9 图 · 3 视频 · 3 音频": "Up to 9 images · 3 videos · 3 audio files",
    "选择工作流": "Choose workflow",
    "管理工作流": "Manage workflows",
    "重命名、启用、禁用或导入": "Rename, enable, disable, or import",
    "完成": "Done",
    "尺寸": "Dimensions",
    "读取图片结果…": "Loading image result…",
    "取消": "Cancel",
    "再次生成": "Generate again",
    "查看结果": "View results",
    "任务详情": "Job details",
    "结果列表加载失败": "Failed to load results",
    "结果文件仍在写入": "Result file is still being written",
    "点击查看结果": "Click to view results",
    "生成结果": "Generation results",
    "正在读取结果…": "Loading results…"
  };

  const textSources = new WeakMap();
  const textRendered = new WeakMap();
  const attributeSources = new WeakMap();
  let observer = null;
  let currentLanguage = resolveInitialLanguage();
  let internalMutation = false;

  function normalizeLanguage(value) {
    const raw = String(value || "").toLowerCase();
    return raw.startsWith("zh") ? "zh-CN" : "en";
  }

  function resolveInitialLanguage() {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored && SUPPORTED.has(stored)) return stored;
    } catch (_) {}
    return normalizeLanguage(navigator.language || navigator.languages?.[0] || "en");
  }

  function exact(source) {
    return currentLanguage === "zh-CN" ? source : (EN[source] || null);
  }

  function translatePattern(source) {
    if (currentLanguage === "zh-CN") return source;
    let match;
    if ((match = source.match(/^(\d+) 秒$/))) return `${match[1]} sec`;
    if ((match = source.match(/^(\d+)秒$/))) return `${match[1]} sec`;
    if ((match = source.match(/^(\d+)分(\d+)秒$/))) return `${match[1]}m ${match[2]}s`;
    if ((match = source.match(/^ · 第 (\d+) 位$/))) return ` · #${match[1]}`;
    if ((match = source.match(/^(\d+) 张$/))) return `${match[1]} images`;
    if ((match = source.match(/^种子 (.+)$/))) return `Seed ${match[1]}`;
    if ((match = source.match(/^进度 (\d+)%$/))) return `Progress ${match[1]}%`;
    if ((match = source.match(/^(.+) 可用$/))) return `${match[1]} free`;
    if ((match = source.match(/^最多选择 (\d+) 个图片$/))) return `Select up to ${match[1]} images`;
    if ((match = source.match(/^最多选择 (\d+) 个视频$/))) return `Select up to ${match[1]} videos`;
    if ((match = source.match(/^最多选择 (\d+) 个音频$/))) return `Select up to ${match[1]} audio files`;
    if ((match = source.match(/^参考图片 (\d+)$/))) return `Reference image ${match[1]}`;
    if ((match = source.match(/^已读取 (\d+) 个节点，请选择参数和输出。$/))) return `Read ${match[1]} nodes. Choose parameters and output.`;
    if ((match = source.match(/^(.+) 已保存为草稿 r(\d+)$/))) return `${match[1]} saved as draft r${match[2]}`;
    if ((match = source.match(/^(.+) 已导入为草稿$/))) return `${match[1]} imported as a draft`;
    if ((match = source.match(/^正在编辑 (.+)；保存会创建新 revision，旧任务仍使用原快照。$/))) return `Editing ${match[1]}; saving creates a new revision while old jobs keep their original snapshot.`;
    if ((match = source.match(/^删除 (.+)？历史任务不会受影响。$/))) return `Delete ${match[1]}? Historical jobs will not be affected.`;
    if ((match = source.match(/^已按参考视频 1 时长设置为 (\d+) 秒$/))) return `Duration set to ${match[1]} seconds from reference video 1`;
    if ((match = source.match(/^上传中 (.+) \/ (.+)（(\d+)%） · (.+)$/))) return `Uploading ${match[1]} / ${match[2]} (${match[3]}%) · ${match[4]}`;
    if ((match = source.match(/^上传完成，但 ComfyUI 提交失败：(.+)$/))) return `Upload completed, but ComfyUI submission failed: ${match[1]}`;
    if ((match = source.match(/^参数或素材校验失败：(.+)$/))) return `Parameter or media validation failed: ${match[1]}`;
    if ((match = source.match(/^ComfyUI 提交失败：(.+)$/))) return `ComfyUI submission failed: ${match[1]}`;
    if ((match = source.match(/^提交失败：(.+)$/))) return `Submission failed: ${match[1]}`;
    if ((match = source.match(/^已载入原参数，并沿用 (.+)$/))) return `Original settings loaded; keeping ${match[1]}`;
    if ((match = source.match(/^确认(关闭|重启) ComfyUI？(.*)$/))) return `${match[1] === "关闭" ? "Stop" : "Restart"} ComfyUI?${match[2] ? " Unfinished jobs will be interrupted." : ""}`;
    return source;
  }

  function translate(source) {
    const value = String(source ?? "");
    const direct = exact(value);
    return direct == null ? translatePattern(value) : direct;
  }

  function shouldSkip(node) {
    const parent = node.parentElement;
    return !parent || Boolean(parent.closest("script, style, code, pre, textarea, [data-i18n-ignore], .job-prompt"));
  }

  function translateTextNode(node) {
    if (!node || node.nodeType !== Node.TEXT_NODE || shouldSkip(node)) return;
    const current = node.nodeValue || "";
    const previousRendered = textRendered.get(node);
    let source = textSources.get(node);
    if (source == null || (previousRendered != null && current !== previousRendered)) {
      source = current;
      textSources.set(node, source);
    }
    const rendered = translate(source);
    textRendered.set(node, rendered);
    if (current !== rendered) {
      internalMutation = true;
      node.nodeValue = rendered;
      internalMutation = false;
    }
  }

  function translateAttributes(element) {
    if (!(element instanceof Element) || element.matches("[data-i18n-ignore]")) return;
    const names = ["aria-label", "placeholder", "title", "alt"];
    let sources = attributeSources.get(element);
    if (!sources) { sources = {}; attributeSources.set(element, sources); }
    for (const name of names) {
      if (!element.hasAttribute(name)) continue;
      const current = element.getAttribute(name) || "";
      const marker = `${name}Rendered`;
      if (!(name in sources) || (sources[marker] != null && current !== sources[marker])) sources[name] = current;
      const rendered = translate(sources[name]);
      sources[marker] = rendered;
      if (current !== rendered) element.setAttribute(name, rendered);
    }
  }

  function translateTree(root = document.body) {
    if (!root) return;
    if (root.nodeType === Node.TEXT_NODE) translateTextNode(root);
    if (root.nodeType === Node.ELEMENT_NODE) translateAttributes(root);
    const walker = document.createTreeWalker(root, NodeFilter.SHOW_ELEMENT | NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      if (node.nodeType === Node.TEXT_NODE) translateTextNode(node);
      else translateAttributes(node);
    }
  }

  function updateLanguageUi() {
    document.documentElement.lang = currentLanguage;
    const value = document.querySelector("#language-value");
    if (value) value.textContent = currentLanguage === "zh-CN" ? "简体中文" : "English";
    const toggle = document.querySelector("#language-toggle");
    if (toggle) toggle.setAttribute("aria-label", currentLanguage === "zh-CN" ? "切换到 English" : "Switch to 简体中文");
  }

  function setLanguage(language) {
    const next = normalizeLanguage(language);
    if (!SUPPORTED.has(next)) return;
    currentLanguage = next;
    try { localStorage.setItem(STORAGE_KEY, next); } catch (_) {}
    updateLanguageUi();
    translateTree(document.body);
    window.dispatchEvent(new CustomEvent("comfy-language-changed", { detail: { language: next } }));
  }

  function startObserver() {
    observer?.disconnect();
    observer = new MutationObserver(records => {
      if (internalMutation) return;
      for (const record of records) {
        if (record.type === "characterData") translateTextNode(record.target);
        if (record.type === "attributes") translateAttributes(record.target);
        for (const node of record.addedNodes || []) translateTree(node);
      }
      updateLanguageUi();
    });
    observer.observe(document.body, { subtree: true, childList: true, characterData: true, attributes: true, attributeFilter: ["aria-label", "placeholder", "title", "alt"] });
  }

  window.ComfyI18n = {
    get language() { return currentLanguage; },
    t: translate,
    setLanguage,
    apply: translateTree,
    supported: ["en", "zh-CN"]
  };

  document.addEventListener("DOMContentLoaded", () => {
    updateLanguageUi();
    translateTree(document.body);
    const toggle = document.querySelector("#language-toggle");
    toggle?.addEventListener("click", () => setLanguage(currentLanguage === "zh-CN" ? "en" : "zh-CN"));
    startObserver();
  });
})();
