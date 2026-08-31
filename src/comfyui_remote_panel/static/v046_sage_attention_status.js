(() => {
  if (typeof renderMetrics !== "function") return;

  const baseRenderMetricsV046SageAttention = renderMetrics;

  renderMetrics = function(metrics) {
    baseRenderMetricsV046SageAttention(metrics);

    const overview = document.querySelector("#device-overview");
    if (!overview) return;

    overview.querySelector('[data-v046-sage-attention]')?.remove();
    if (!metrics?.comfyui?.sage_attention) return;

    const chip = document.createElement("div");
    chip.className = "device-chip online";
    chip.dataset.v046SageAttention = "true";
    chip.innerHTML = "<small>ATTENTION</small><strong>SageAttention</strong>";
    overview.append(chip);
  };
})();
