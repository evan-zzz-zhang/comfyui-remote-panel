(() => {
  const retainedMedia = new Map();
  const removedRoles = new Set();
  const outputMetadata = new Map();
  const metadataRequests = new Set();

  const inputForRole = role => {
    if (role === "first") return document.querySelector("#first-frame");
    if (role === "last") return document.querySelector("#last-frame");
    return document.querySelector(`#job-form input[type="file"][name="${CSS.escape(role)}"]`);
  };

  const previewUrl = item => `/api/jobs/${encodeURIComponent(item.sourceJob)}/inputs/${encodeURIComponent(item.artifact_id)}`;

  const mediaKind = item => mediaKindFromRole(item.role) || item.kind || "file";

  function resetRetainedState() {
    retainedMedia.clear();
    removedRoles.clear();
    document.querySelectorAll("img[data-v041-retained-role]").forEach(image => {
      const input = inputForRole(image.dataset.v041RetainedRole || "");
      if (!input?.files?.length) {
        image.removeAttribute("src");
        image.closest(".upload-card")?.classList.remove("has-image");
      }
      delete image.dataset.v041RetainedRole;
    });
    document.querySelectorAll(".v041-retained-remove").forEach(button => button.remove());
  }

  function markLazy(image, role) {
    image.loading = "lazy";
    image.decoding = "async";
    image.dataset.v041RetainedRole = role;
  }

  function addRetainedDelete(card, role) {
    if (!card || card.querySelector(`.v041-retained-remove[data-role="${CSS.escape(role)}"]`)) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "v041-retained-remove";
    button.dataset.role = role;
    button.textContent = "删除";
    button.setAttribute("aria-label", `删除沿用素材 ${role}`);
    card.append(button);
  }

  function renderSingleRetained(item) {
    if (mediaKind(item) !== "image" || removedRoles.has(item.role)) return;
    const input = inputForRole(item.role);
    if (!input || input.files?.length) return;
    const card = input.closest(".upload-card") || input.closest(".generic-reference-card") || input.parentElement;
    if (!card) return;
    card.classList.add("upload-card", "has-image");
    let image = card.querySelector(":scope > img");
    if (!image) {
      image = document.createElement("img");
      image.alt = "参考图预览";
      input.insertAdjacentElement("afterend", image);
    }
    image.src = previewUrl(item);
    markLazy(image, item.role);
    addRetainedDelete(card, item.role);
  }

  function patchCollectionPreview(kind, entry, index, item) {
    const container = document.querySelector(`#ref-${kind}-preview`);
    const card = container?.children?.[index];
    if (!card || removedRoles.has(item.role)) return;
    const url = previewUrl(item);
    entry.url = url;
    if (kind === "image") {
      let image = card.querySelector(":scope > img");
      if (!image) {
        image = document.createElement("img");
        image.alt = `参考图片 ${index + 1}`;
        const placeholder = card.firstElementChild;
        if (placeholder?.tagName === "SPAN") placeholder.replaceWith(image);
        else card.prepend(image);
      }
      image.src = url;
      markLazy(image, item.role);
      return;
    }
    if (kind === "video" && !card.querySelector(":scope > video")) {
      const video = document.createElement("video");
      video.controls = true;
      video.muted = true;
      video.playsInline = true;
      video.preload = "metadata";
      video.src = url;
      card.prepend(video);
    }
  }

  function renderCollectionRetained() {
    for (const kind of ["image", "video", "audio"]) {
      const entries = state.mediaFiles?.[kind] || [];
      entries.forEach((entry, index) => {
        if (entry?.source !== "retained") return;
        const item = retainedMedia.get(entry.role);
        if (!item || removedRoles.has(entry.role)) return;
        patchCollectionPreview(kind, entry, index, item);
      });
    }
  }

  function renderRetainedDraft() {
    document.querySelectorAll("img[data-v041-retained-role]").forEach(image => {
      if (!inputForRole(image.dataset.v041RetainedRole || "")?.files?.length) image.removeAttribute("src");
      delete image.dataset.v041RetainedRole;
    });
    document.querySelectorAll(".v041-retained-remove").forEach(button => button.remove());
    if (!document.querySelector("#retry-source-id")?.value) return;
    if (selectedPreset()?.family === "ref2va") renderCollectionRetained();
    else retainedMedia.forEach(renderSingleRetained);
  }

  function queueRetainedRender() {
    window.setTimeout(() => {
      window.requestAnimationFrame(() => renderRetainedDraft());
    }, 0);
  }

  function restoreRetainedDraft(draft) {
    resetRetainedState();
    const sourceJob = String(draft?.retry_source_id || "");
    for (const raw of draft?.retained_media || []) {
      const role = String(raw?.role || "");
      if (!role || raw?.artifact_id == null) continue;
      retainedMedia.set(role, { ...raw, role, sourceJob });
    }
    if (selectedPreset()?.family === "ref2va") {
      for (const kind of ["image", "video", "audio"]) {
        for (const entry of state.mediaFiles?.[kind] || []) {
          const item = retainedMedia.get(entry.role);
          if (entry?.source === "retained" && item) entry.url = previewUrl(item);
        }
      }
    }
    renderRetainedDraft();
  }

  function deleteSingleRetained(role) {
    if (!retainedMedia.has(role)) return;
    removedRoles.add(role);
    state.retryRoles = (state.retryRoles || []).filter(item => item !== role);
    state.retryKeepRoles = (state.retryKeepRoles || []).filter(item => item !== role);
    const input = inputForRole(role);
    if (input) {
      input.value = "";
      input.dispatchEvent(new Event("change", { bubbles: true }));
    }
    const image = document.querySelector(`img[data-v041-retained-role="${CSS.escape(role)}"]`);
    if (image) {
      image.removeAttribute("src");
      delete image.dataset.v041RetainedRole;
      image.closest(".upload-card")?.classList.remove("has-image");
    }
    document.querySelector(`.v041-retained-remove[data-role="${CSS.escape(role)}"]`)?.remove();
  }

  function retainedKeepRoles() {
    if (!document.querySelector("#retry-source-id")?.value) return [];
    if (selectedPreset()?.family === "ref2va") {
      return Object.values(state.mediaFiles || {}).flat()
        .filter(entry => entry?.source === "retained" && retainedMedia.has(entry.role) && !removedRoles.has(entry.role))
        .map(entry => entry.role);
    }
    return [...retainedMedia.keys()].filter(role => {
      if (removedRoles.has(role)) return false;
      const input = inputForRole(role);
      return !input?.files?.length;
    });
  }

  const baseApiActionV041 = apiAction;
  apiAction = async function(path, options = {}) {
    const result = await baseApiActionV041(path, options);
    const method = String(options.method || "GET").toUpperCase();
    if (method === "POST" && /^\/api\/jobs\/[^/]+\/retry$/.test(path) && result?.retry_source_id) {
      window.setTimeout(() => {
        window.requestAnimationFrame(() => restoreRetainedDraft(result));
      }, 0);
    }
    return result;
  };

  const baseUploadFormV041 = uploadForm;
  uploadForm = function(path, formData, onProgress) {
    const retrySource = path === "/api/jobs" ? formData.get("retry_source_id") : null;
    if (retrySource) {
      formData.set("retry_keep_roles", JSON.stringify(retainedKeepRoles()));
    }
    const request = baseUploadFormV041(path, formData, onProgress);
    if (!retrySource) return request;
    return request.then(result => {
      window.setTimeout(() => resetRetainedState(), 0);
      return result;
    });
  };

  function outputLabel(artifact) {
    const metadata = artifact?.metadata || {};
    const width = Number(metadata.width);
    const height = Number(metadata.height);
    if (!Number.isFinite(width) || !Number.isFinite(height)) return null;
    const format = String(metadata.format || artifact.mime_type?.split("/").pop() || "image").toUpperCase();
    return `${width}×${height} · ${format} · ${formatBytes(artifact.size_bytes)}`;
  }

  function applyOutputMetadata(jobId) {
    const artifact = outputMetadata.get(jobId);
    if (!artifact) return;
    const card = document.querySelector(`#jobs-list [data-job="${CSS.escape(jobId)}"]`);
    const meta = card?.querySelector(".job-meta");
    const label = outputLabel(artifact);
    if (!meta || !label) return;
    const spans = [...meta.querySelectorAll(":scope > span")];
    const target = spans.find(span => span.dataset.v041OutputMetadata === "1") || spans.at(-1);
    if (!target) return;
    target.dataset.v041OutputMetadata = "1";
    target.textContent = label;
  }

  async function loadOutputMetadata(job) {
    if (!job || job.status !== "succeeded" || job.has_video) return;
    if (outputMetadata.has(job.id)) {
      applyOutputMetadata(job.id);
      return;
    }
    if (metadataRequests.has(job.id)) return;
    metadataRequests.add(job.id);
    try {
      const response = await fetch(`/api/jobs/${encodeURIComponent(job.id)}/artifacts`);
      if (!response.ok) return;
      const payload = await response.json();
      const images = (payload.items || []).filter(item => item.direction === "output" && item.kind === "image");
      const artifact = images.find(item => item.binding_id === "primary") || images[0] || null;
      outputMetadata.set(job.id, artifact);
      if (artifact) applyOutputMetadata(job.id);
    } catch (_) {
      // History must remain usable when output metadata is unavailable.
    } finally {
      metadataRequests.delete(job.id);
    }
  }

  function refreshOutputMetadata() {
    for (const job of state.jobs.values()) {
      if (outputMetadata.has(job.id)) applyOutputMetadata(job.id);
      else void loadOutputMetadata(job);
    }
  }

  const baseRenderJobsV041 = renderJobs;
  renderJobs = function() {
    const result = baseRenderJobsV041();
    queueMicrotask(refreshOutputMetadata);
    return result;
  };

  const baseUpsertJobV041 = upsertJob;
  upsertJob = function(job) {
    const result = baseUpsertJobV041(job);
    if (outputMetadata.has(job?.id)) applyOutputMetadata(job.id);
    else void loadOutputMetadata(job);
    return result;
  };

  document.addEventListener("DOMContentLoaded", () => {
    const form = document.querySelector("#job-form");

    form?.addEventListener("change", event => {
      const input = event.target.closest?.('input[type="file"]');
      if (!input?.files?.length) return;
      let role = input.name;
      if (input.id === "first-frame") role = "first";
      if (input.id === "last-frame") role = "last";
      if (!retainedMedia.has(role)) return;
      removedRoles.add(role);
      state.retryRoles = (state.retryRoles || []).filter(item => item !== role);
      const image = input.closest(".upload-card")?.querySelector(":scope > img");
      if (image) delete image.dataset.v041RetainedRole;
      input.closest(".upload-card")?.querySelector(`.v041-retained-remove[data-role="${CSS.escape(role)}"]`)?.remove();
    });

    document.addEventListener("click", event => {
      const remove = event.target.closest?.(".v041-retained-remove");
      if (remove) {
        event.preventDefault();
        event.stopPropagation();
        deleteSingleRetained(remove.dataset.role || "");
        return;
      }
      if (event.target.closest?.("#clear-retry")) {
        window.setTimeout(() => resetRetainedState(), 0);
        return;
      }
      if (event.target.closest?.("#ref2va-media [data-media-action]")) {
        window.setTimeout(() => {
          document.querySelectorAll("#ref-image-preview img").forEach(image => {
            const entry = (state.mediaFiles.image || []).find(item => item?.url === image.getAttribute("src"));
            if (entry?.source === "retained") markLazy(image, entry.role);
          });
        }, 0);
      }
    });

    document.querySelector("#preset-select")?.addEventListener("change", queueRetainedRender);
    queueMicrotask(refreshOutputMetadata);
  });
})();
