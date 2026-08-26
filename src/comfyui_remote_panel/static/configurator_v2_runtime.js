(() => {
  const ACTIVE_STATUSES = new Set(["submitting", "queued", "running"]);

  function genericFamily(job) {
    return state.presets.get(job?.preset_id)?.family
      || state.workflowItems?.get(job?.preset_id)?.manifest?.family
      || null;
  }

  function revokePreview(preview) {
    const url = preview?.dataset?.objectUrl;
    if (url) URL.revokeObjectURL(url);
  }

  function removePreview(input) {
    const card = input.closest(".generic-reference-card");
    const preview = card?.querySelector(".generic-source-preview");
    revokePreview(preview);
    preview?.remove();
    card?.classList.remove("has-source-preview");
  }

  function renderPreview(input) {
    const file = input.files?.[0];
    const card = input.closest(".generic-reference-card");
    if (!card) return;
    removePreview(input);
    if (!file) return;

    const preview = document.createElement("img");
    preview.className = "generic-source-preview";
    preview.alt = "源图预览";
    const url = URL.createObjectURL(file);
    preview.dataset.objectUrl = url;
    preview.src = url;
    card.insertBefore(preview, card.querySelector("span") || null);
    card.classList.add("has-source-preview");
  }

  function bindGenericImagePreviews() {
    const preset = selectedPreset();
    if (!preset || preset.family !== "generic") return;
    const slots = preset.input_bindings?.media?.slots || {};
    for (const [role, slot] of Object.entries(slots)) {
      if (slot?.kind !== "image") continue;
      const input = document.querySelector(`#job-form input[name="${CSS.escape(role)}"]`);
      if (!input || input.dataset.v2PreviewBound === "1") continue;
      input.dataset.v2PreviewBound = "1";
      input.addEventListener("change", () => renderPreview(input));
      if (input.files?.length) renderPreview(input);
    }
  }

  function installPreviewStyles() {
    if (document.querySelector("#v2-runtime-preview-style")) return;
    const style = document.createElement("style");
    style.id = "v2-runtime-preview-style";
    style.textContent = `
      .generic-reference-card.has-source-preview{min-height:94px;border-style:solid;align-items:center}
      .generic-reference-card.has-source-preview>svg{display:none}
      .generic-source-preview{display:block;width:76px;height:76px;flex:0 0 76px;object-fit:cover;background:#090b08;border:1px solid var(--border-soft);border-radius:10px}
      .artifact-grid.gallery.single-image{grid-template-columns:minmax(0,1fr)!important;justify-items:center}
      .artifact-grid.single-image .artifact-item{width:min(100%,680px);justify-self:center}
      .artifact-grid.single-image .artifact-item img{display:block;width:auto;max-width:100%;height:auto;max-height:calc(100dvh - 180px);margin:0 auto;object-fit:contain}
      .artifact-preview.one{grid-template-columns:minmax(0,1fr);place-items:center}
      .artifact-preview.one .artifact-preview-item{display:grid;width:100%;place-items:center}
      .artifact-preview.one .artifact-preview-item img{display:block;width:auto;max-width:100%;height:auto;max-height:430px;margin:0 auto;object-fit:contain}
      @media (max-width:370px){.generic-source-preview{width:64px;height:64px;flex-basis:64px}}
    `;
    document.head.append(style);
  }

  function normalizeSingleImageLayouts(root = document) {
    root.querySelectorAll?.(".artifact-grid").forEach(grid => {
      const items = [...grid.children].filter(item => item.classList?.contains("artifact-item"));
      const singleImage = items.length === 1
        && Boolean(items[0].querySelector("img"))
        && !items[0].querySelector("video,audio");
      grid.classList.toggle("single-image", singleImage);
    });
  }

  function stabilizeGenericProgress(job) {
    const previous = state.jobs.get(job?.id);
    if (!previous || genericFamily(job) !== "generic") return job;
    if (!ACTIVE_STATUSES.has(previous.status) || !ACTIVE_STATUSES.has(job.status)) return job;

    const next = { ...job };
    const oldPercent = Number(previous.progress_percent);
    const newPercent = Number(next.progress_percent);
    const oldValid = Number.isFinite(oldPercent);
    const newValid = Number.isFinite(newPercent);

    if (!newValid && oldValid) next.progress_percent = previous.progress_percent;
    else if (oldValid && newValid && newPercent < oldPercent) next.progress_percent = previous.progress_percent;

    if ((!next.stage || next.stage === "运行中") && previous.stage && previous.stage !== "运行中") {
      next.stage = previous.stage;
    }
    return next;
  }

  function patchActiveGenericCard(job, previous) {
    const list = document.querySelector("#jobs-list");
    const card = list?.querySelector(`[data-job="${CSS.escape(job.id)}"]`);
    if (!card || !previous) return false;
    if (genericFamily(job) !== "generic") return false;
    if (!ACTIVE_STATUSES.has(previous.status) || !ACTIVE_STATUSES.has(job.status)) return false;

    state.jobs.set(job.id, job);

    const status = card.querySelector(".job-status");
    if (status) {
      status.className = `job-status ${job.status}`;
      status.textContent = statusLabels[job.status] || job.status;
    }

    const progress = Math.max(0, Math.min(100, Number(job.progress_percent) || 0));
    const queueText = job.status === "queued" && job.queue_position ? ` · 第 ${job.queue_position} 位` : "";
    const progressBox = card.querySelector(".job-progress");
    if (progressBox) {
      const label = progressBox.querySelector("span");
      const value = progressBox.querySelector("b");
      const track = progressBox.querySelector(".progress-track");
      if (label) label.textContent = `${job.stage || "等待状态"}${queueText}`;
      if (value) value.textContent = `${progress}% · ${formatDuration(job.elapsed_seconds)}`;
      if (track) {
        track.value = progress;
        track.setAttribute("aria-label", `进度 ${progress}%`);
      }
    }

    updateJobsSummary();
    return true;
  }

  const baseUpsertJob = upsertJob;
  upsertJob = function(job) {
    const previous = state.jobs.get(job?.id);
    const stable = stabilizeGenericProgress(job);
    if (patchActiveGenericCard(stable, previous)) return;
    return baseUpsertJob(stable);
  };

  document.addEventListener("DOMContentLoaded", () => {
    installPreviewStyles();
    const root = document.querySelector("#generic-parameters");
    if (root) {
      new MutationObserver(records => {
        for (const record of records) {
          for (const node of record.removedNodes) {
            if (!(node instanceof Element)) continue;
            if (node.matches?.(".generic-source-preview")) revokePreview(node);
            node.querySelectorAll?.(".generic-source-preview").forEach(revokePreview);
          }
        }
        bindGenericImagePreviews();
      }).observe(root, { childList: true, subtree: true });
      bindGenericImagePreviews();
    }

    const body = document.body;
    if (body) {
      new MutationObserver(() => normalizeSingleImageLayouts(body)).observe(body, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ["class"],
      });
      normalizeSingleImageLayouts(body);
    }
  });
})();
