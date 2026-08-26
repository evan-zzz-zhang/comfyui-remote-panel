(() => {
  const ACTIVE_STATUSES = new Set(["submitting", "queued", "running"]);

  const MediaUI = window.ComfyRemoteMediaUI = window.ComfyRemoteMediaUI || {};

  MediaUI.bindSingleImageInput = function(input, { card = null, image = null } = {}) {
    if (!input || input.dataset.mediaUiBound === "1") return;
    const targetCard = card || input.closest(".upload-card");
    if (!targetCard) return;
    let preview = image || targetCard.querySelector(":scope > img");
    if (!preview) {
      preview = document.createElement("img");
      preview.alt = "图片预览";
      input.insertAdjacentElement("afterend", preview);
    }

    const revoke = () => {
      if (preview.dataset.objectUrl) URL.revokeObjectURL(preview.dataset.objectUrl);
      delete preview.dataset.objectUrl;
    };
    const sync = () => {
      const file = input.files?.[0];
      revoke();
      targetCard.classList.toggle("has-image", Boolean(file));
      if (!file) {
        preview.removeAttribute("src");
        return;
      }
      const url = URL.createObjectURL(file);
      preview.dataset.objectUrl = url;
      preview.src = url;
    };

    input.dataset.mediaUiBound = "1";
    input.addEventListener("change", sync);
    sync();
  };

  function genericFamily(job) {
    return state.presets.get(job?.preset_id)?.family
      || state.workflowItems?.get(job?.preset_id)?.manifest?.family
      || null;
  }

  function prepareGenericImageCards() {
    const preset = selectedPreset();
    if (!preset || preset.family !== "generic") return;
    const slots = preset.input_bindings?.media?.slots || {};
    for (const [role, slot] of Object.entries(slots)) {
      if (slot?.kind !== "image") continue;
      const input = document.querySelector(`#job-form input[name="${CSS.escape(role)}"]`);
      const card = input?.closest(".generic-reference-card");
      if (!input || !card) continue;
      card.classList.add("upload-card");
      let image = card.querySelector(":scope > img");
      if (!image) {
        image = document.createElement("img");
        image.alt = slot.ui?.label ? `${slot.ui.label}预览` : "参考图预览";
        input.insertAdjacentElement("afterend", image);
      }
      MediaUI.bindSingleImageInput(input, { card, image });
    }
  }

  const baseApplyPresetForMedia = applyPreset;
  applyPreset = function(...args) {
    const result = baseApplyPresetForMedia(...args);
    queueMicrotask(prepareGenericImageCards);
    return result;
  };

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
    queueMicrotask(prepareGenericImageCards);
  });
})();
