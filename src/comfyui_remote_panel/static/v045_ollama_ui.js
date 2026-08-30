(() => {
  const MODEL_SELECTOR = "[data-v045-ollama-model]";
  const FIELD_SELECTOR = "[data-v045-ollama-model-field]";
  const STANDARDIZER_SELECTOR = "[data-v042-prompt-standardization]";
  const STORAGE_KEY = "comfy-remote.fl2va.ollama-model";
  const DEFAULT_MODEL = "gemma4:e4b";
  let modelsPromise = null;

  function rememberedModel() {
    try {
      return window.localStorage.getItem(STORAGE_KEY)?.trim() || "";
    } catch (_) {
      return "";
    }
  }

  function rememberModel(value) {
    const model = String(value || "").trim();
    if (!model) return;
    try { window.localStorage.setItem(STORAGE_KEY, model); } catch (_) {}
  }

  function standardizationEnabled() {
    return document.querySelector(STANDARDIZER_SELECTOR)?.checked !== false;
  }

  function syncDisabled(select) {
    if (select) select.disabled = !standardizationEnabled();
  }

  async function fetchModels() {
    if (!modelsPromise) {
      modelsPromise = fetch("/api/ollama/models", { headers: { Accept: "application/json" } })
        .then(async response => {
          const payload = await response.json().catch(() => ({}));
          if (!response.ok) throw new Error(payload?.error?.message || "无法读取 Ollama 模型");
          return Array.isArray(payload?.items)
            ? payload.items.filter(value => typeof value === "string" && value.trim()).map(value => value.trim())
            : [];
        })
        .catch(error => {
          modelsPromise = null;
          throw error;
        });
    }
    return modelsPromise;
  }

  function option(value, label = value) {
    const item = document.createElement("option");
    item.value = value;
    item.textContent = label;
    return item;
  }

  async function upgradeField() {
    const field = document.querySelector(FIELD_SELECTOR);
    if (!field) return;
    const current = field.querySelector(MODEL_SELECTOR);
    if (!current) return;
    if (current.tagName === "SELECT") {
      syncDisabled(current);
      return;
    }

    const preferred = String(current.value || rememberedModel() || DEFAULT_MODEL).trim() || DEFAULT_MODEL;
    const select = document.createElement("select");
    select.dataset.v045OllamaModel = "true";
    select.disabled = true;
    select.append(option(preferred, "正在读取 Ollama 模型…"));
    current.replaceWith(select);

    select.addEventListener("change", () => rememberModel(select.value));

    try {
      const models = await fetchModels();
      if (!select.isConnected) return;
      select.innerHTML = "";
      const unique = [...new Set(models)];
      if (!unique.includes(preferred)) {
        select.append(option(preferred, `${preferred}（未检测到）`));
      }
      for (const model of unique) select.append(option(model));
      if (!select.options.length) select.append(option(preferred));
      select.value = preferred;
      select.title = unique.length ? `已检测到 ${unique.length} 个 Ollama 模型` : "未检测到 Ollama 模型";
    } catch (error) {
      if (!select.isConnected) return;
      select.innerHTML = "";
      select.append(option(preferred, `${preferred}（模型列表读取失败）`));
      select.value = preferred;
      select.title = String(error?.message || error || "无法读取 Ollama 模型");
    } finally {
      syncDisabled(select);
    }
  }

  document.addEventListener("change", event => {
    if (event.target?.matches?.(STANDARDIZER_SELECTOR)) {
      syncDisabled(document.querySelector(MODEL_SELECTOR));
    }
  });

  document.addEventListener("DOMContentLoaded", () => {
    upgradeField();
    const advanced = document.querySelector("#advanced-settings");
    if (advanced) {
      new MutationObserver(() => queueMicrotask(upgradeField))
        .observe(advanced, { childList: true, subtree: true });
    }
  });
})();
