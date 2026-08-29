# Changelog

## v0.4.1 — Media Continuity

Comfy Remote v0.4.1 completes the v0.4 mobile creation/recovery baseline with reliable Retry media continuity and actual image output metadata.

### Highlights

- Retry restores retained historical reference media through authenticated server URLs instead of placeholder-only state or fabricated browser `File`/`Blob` objects.
- Retained media can be reused without reselecting it on the phone, while replacement and deletion remain explicit per-Job actions.
- Each retried Job keeps its own private input copy; when image resolution policy and target are unchanged, saved preprocessing metadata is reused and redundant image processing is skipped.
- Changing the resolution policy or target processes only the new Job's private copy and leaves the source Job untouched.
- Image result cards show actual output width, height, format, and file size read from the produced file; historical image metadata is lazily backfilled when available.
- `job_artifacts.metadata_json` is additive and the existing SQLite compatibility marker is preserved for rollback compatibility.
- Recovery Lite now requires three consecutive failed ComfyUI health polls before a verified still-running managed process is classified as `unresponsive`; any successful poll resets the streak. Force restart is not offered during the first two failures.
- Existing H3 / Generic workflow behavior, Seed Policy, mobile Prompt keyboard behavior, Settings, and Recovery Lite controls remain regression-covered.

### Verification

- Real-phone acceptance completed on 2026-08-29 for retained preview, prompt-only Retry, A → B → C Retry continuity, Replace / Delete, resolution-policy changes, H3 ↔ Generic switching, Settings, Recovery Lite, and WAI txt2img/img2img output-dimension comparison.
- The three-failure unresponsive debounce is covered by automated tests, including streak reset after a successful health poll; a real GPU/ComfyUI hard hang is intentionally not manufactured for acceptance.
- CI covers minimum dependencies, repository/history safety, Windows and Ubuntu on Python 3.11 / 3.13, pytest, JavaScript syntax checks, i18n smoke, and package builds.

### Still out of scope

- Automatic watchdog / crash-loop recovery and automatic job resubmission.
- Wake-on-LAN or powered-off/sleeping host recovery.
- Multi-host routing.
- Media library / global Asset system, content-addressed storage, hardlinks, or reference counting.
- Video poster generation or FFmpeg/OpenCV-based media parsing.

## v0.3.0 — Public Beta

Comfy Remote v0.3.0 is the first public-beta baseline focused on making a local ComfyUI installation usable from a phone without requiring users to hand-edit project configuration.

### Highlights

- Windows setup wizard and setup-first installation path.
- Tailscale Serve remote access with identity-based authorization.
- Generic ComfyUI API Workflow import and runtime submission.
- Configurator 2.0 workflow analysis using schema + graph + conservative heuristic fallback.
- Workflow capability / editable-parameter separation; workflows do not need fixed `width`, `height`, or `batch_size` fields.
- PASS / WARN / FAIL Preflight across structure, nodes, inputs, parameters, outputs, and runtime.
- Real Runtime Test against the user's local ComfyUI.
- Image / video / audio / file artifacts and task history.
- Panel `start / stop / restart / status`, ComfyUI lifecycle controls, and Windows login autostart.
- Doctor diagnostics and privacy-safe `doctor --report` output.
- Windows Portable launch-script discovery that preserves real arguments such as `--enable-manager` and optional `--use-sage-attention`.
- Six MiniMax H3 workflows retained as Bundled / Verified examples without making H3 a core dependency.

### Verified during v0.3 development

- Fresh Windows installation and Setup on separate machines.
- Panel background start/status behavior without a persistent Panel console window.
- ComfyUI lifecycle start/stop/restart with its own visible console.
- Generic non-H3 API Workflow import, Preflight, runtime submission, generation, and result viewing.
- Tailscale identity / Serve configuration path and mobile access during acceptance.
- Windows autostart registration.
- Environment with H3 nodes/workflows present but H3 model assets absent: optional H3 assets no longer make the generic installation incorrectly `NOT READY`.
- Normal and SageAttention Portable startup variants with their actual command-line flags preserved.

### Known limitations

- Windows 10/11 is the primary publicly validated platform.
- Tailscale is the primary supported remote transport in v0.3.
- Advanced recovery after severe ComfyUI/GPU/driver crashes is limited.
- No Wake-on-LAN or off-machine power recovery.
- No multi-host registry/routing/selector.
- Third-party Custom Node compatibility depends on `/object_info` schema plus real runtime behavior.
- Seed Policy is not yet a separate feature; blank seed is random, explicit numeric seed including `0` is fixed.

### Next

The v0.4 development baseline is **Reliability / Recovery**: clearer ComfyUI health states, crash/restart policy, task reconciliation after disconnects, safe process-tree recovery, and more explicit failure classification.
