(() => {
  if (typeof jobCard !== "function") return;

  const baseJobCardV046Runtime = jobCard;

  function duration(value) {
    return formatDuration(Math.max(0, Number(value) || 0));
  }

  function generationText(job) {
    return `生成 ${duration(job.execution_elapsed_seconds ?? job.elapsed_seconds)}`;
  }

  function timingText(job) {
    if (["submitting", "queued"].includes(job.status)) {
      return `等待 ${duration(job.queue_elapsed_seconds)}`;
    }
    if (job.started_at) return generationText(job);
    if (["interrupted", "failed", "cancelled"].includes(job.status)) {
      return `等待 ${duration(job.queue_elapsed_seconds)}`;
    }
    return generationText(job);
  }

  function progressTimingText(job) {
    if (["submitting", "queued"].includes(job.status)) {
      return `已等待 ${duration(job.queue_elapsed_seconds)}`;
    }
    if (job.progress_phase === "sampling" && job.generation_elapsed_seconds != null) {
      return `采样 ${duration(job.generation_elapsed_seconds)} · ${generationText(job)}`;
    }
    return generationText(job);
  }

  function runtimeTags(job) {
    const tags = [];
    const generationMode = job.generation_mode === "v4step600"
      ? "v4_600step"
      : job.generation_mode;
    const backend = job.prompt_backend || ({
      off: "raw", ollama: "ollama", comfyui: "qwen35",
    }[job.prompt_standardization_mode]);
    if (generationMode === "original") tags.push("原版");
    if (generationMode === "lightx2v") tags.push("LightX2V");
    if (generationMode === "v4_600step") tags.push("v4_600step");
    if (backend === "ollama") tags.push("Ollama");
    if (backend === "qwen35") tags.push("Qwen3.5");
    return tags;
  }

  function appendRuntimeTags(card, job) {
    const meta = card.querySelector(".job-meta");
    if (!meta) return;
    meta.querySelectorAll("[data-v046-runtime-tag]").forEach(node => node.remove());
    for (const label of runtimeTags(job)) {
      const tag = document.createElement("span");
      tag.dataset.v046RuntimeTag = "true";
      tag.textContent = label;
      meta.append(tag);
    }
  }

  function timingDetailRow(label, value) {
    const row = document.createElement("div");
    row.className = "settings-row static";
    row.dataset.v046Timing = label;
    const span = document.createElement("span");
    const strong = document.createElement("strong");
    const small = document.createElement("small");
    strong.textContent = label;
    small.textContent = duration(value);
    span.append(strong, small);
    row.append(span);
    return row;
  }

  function enhanceTimingDetails(jobId) {
    const job = state.jobs?.get?.(jobId);
    const body = document.querySelector("#sheet-body");
    if (!job || !body || body.querySelector("[data-v046-timing]")) return;
    const list = body.querySelector(".settings-list");
    if (!list) return;

    const rows = [
      ["排队等待", job.queue_elapsed_seconds],
      ["标准化提示词", job.standardization_elapsed_seconds],
      ["采样", job.generation_elapsed_seconds],
      ["总生成", job.execution_elapsed_seconds ?? job.elapsed_seconds],
    ].filter(([, value]) => value != null);
    rows.forEach(([label, value]) => list.append(timingDetailRow(label, value)));
  }

  jobCard = function(job) {
    const html = baseJobCardV046Runtime(job);
    const host = document.createElement("div");
    host.innerHTML = String(html || "").trim();
    const card = host.firstElementChild;
    if (!card) return html;

    const time = card.querySelector(".job-time");
    if (time) time.textContent = `${formatDate(job.created_at)} · ${timingText(job)}`;

    appendRuntimeTags(card, job);

    const progressMeta = card.querySelector(".job-progress b");
    if (progressMeta) {
      if (["submitting", "queued"].includes(job.status)) {
        progressMeta.textContent = progressTimingText(job);
      } else {
        const percent = Math.max(0, Math.min(100, Number(job.progress_percent) || 0));
        progressMeta.textContent = `${percent}% · ${progressTimingText(job)}`;
      }
    }
    return card.outerHTML;
  };

  document.addEventListener("click", event => {
    const button = event.target.closest?.("[data-task-details]");
    if (!button?.dataset.taskDetails) return;
    window.setTimeout(() => enhanceTimingDetails(button.dataset.taskDetails), 0);
  }, true);
})();
