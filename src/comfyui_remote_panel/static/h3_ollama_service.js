(() => {
  let modelsPromise = null;

  async function getModels() {
    if (!modelsPromise) {
      modelsPromise = fetch("/api/ollama/models", {
        headers: { Accept: "application/json" },
      }).then(async response => {
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload?.error?.message || "无法读取 Ollama 模型");
        return Array.isArray(payload?.items)
          ? [...new Set(payload.items.filter(value => typeof value === "string" && value.trim()).map(value => value.trim()))]
          : [];
      }).catch(error => {
        modelsPromise = null;
        throw error;
      });
    }
    return modelsPromise;
  }

  window.H3OllamaModelService = {
    getModels,
    invalidate() { modelsPromise = null; },
  };
})();
