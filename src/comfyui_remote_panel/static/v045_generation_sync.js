(() => {
  function emitH3GenerationState() {
    const family = selectedPreset()?.family;
    if (family !== "fl2va" && family !== "ref2va") return;

    // The outer Generation Settings summary already derives from these source
    // controls. Some legacy paths restore or auto-fallback their values by
    // assigning .value directly, which does not emit DOM input/change events.
    // Re-emit the authoritative source state instead of maintaining a second
    // summary cache or polling the DOM.
    document.querySelector('select[name="aspect_ratio"]')
      ?.dispatchEvent(new Event("change", { bubbles: true }));
    document.querySelector('input[name="duration_seconds"]')
      ?.dispatchEvent(new Event("input", { bubbles: true }));
    document.querySelector("#megapixels-value")
      ?.dispatchEvent(new Event("input", { bubbles: true }));
  }

  const baseSetViewV045 = setView;
  setView = function(name) {
    const result = baseSetViewV045(name);
    // Retry restores H3 values immediately before returning to the Generate
    // view. Emitting here guarantees the summary sees the final restored values.
    if (name === "generate") emitH3GenerationState();
    return result;
  };

  document.addEventListener("DOMContentLoaded", () => {
    // Removing reference media may force reference/reference_video back to
    // 9:16 inside app.js without a native select change event.
    document.querySelector("#ref2va-media")?.addEventListener("click", event => {
      if (event.target.closest?.('[data-media-action="remove"]')) emitH3GenerationState();
    });

    // Clearing retained Retry media can invalidate a reference-derived aspect.
    document.querySelector("#clear-retry")?.addEventListener("click", emitH3GenerationState);

    // Reassert after workflow-family changes so FL2VA/Ref2VA cannot inherit a
    // stale outer chip from the previously selected workflow.
    document.querySelector("#preset-select")?.addEventListener("change", emitH3GenerationState);
  });
})();
