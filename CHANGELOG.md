# Changelog

## v0.4.4 — Windows Environment Self-Healing

Comfy Remote v0.4.4 hardens the Windows install and autostart path so a damaged project virtual environment no longer requires manual Python troubleshooting before the Panel can be recovered.

### Highlights

- `Install-ComfyRemote.ps1` now actually starts an existing `.venv` and imports core Python modules plus `pip` before deciding it is reusable.
- A missing or unhealthy `.venv` is preserved as `.venv.broken-YYYYMMDD-HHMMSS` and rebuilt from the selected healthy stable Python instead of being deleted in place.
- A newly created `.venv` is health-checked before installation continues, and the installed `comfyui_remote_panel` package is imported afterward as a final environment verification.
- The installer keeps `.venv` as the preferred runtime environment; the global/base Python is used to validate prerequisites and create the project environment rather than becoming the normal long-term Panel runtime.
- Windows autostart path handling now accepts rooted/absolute Python and config paths in both the startup launcher and Task Scheduler registration path, covering recovery/override scenarios without mangling paths under the project root.
- Installer `ConfigPath` handling now follows the same relative-or-rooted path semantics.

### Recovery behavior

If an existing environment fails the health probe, the installer follows this sequence:

```text
existing .venv
→ launch/import health probe
→ unhealthy
→ rename to .venv.broken-<timestamp>
→ create fresh .venv
→ health probe again
→ pip install -e .
→ import comfyui_remote_panel
→ Setup
```

The backup is intentionally retained so a failed rebuild never destroys the previous environment automatically.

### Verification

- Regression coverage checks the venv health probe, backup-before-rebuild behavior, fresh-environment verification, package import verification, rooted config handling, and PowerShell syntax on runners where PowerShell is available.
- Full CI continues to cover minimum dependencies, repository/history safety, Windows and Ubuntu on Python 3.11 / 3.13, pytest, JavaScript syntax checks, i18n smoke, and package builds.

## v0.4.3 — Task Reconciliation Hardening

Comfy Remote v0.4.3 hardens task final-state reconciliation around Remote Panel restarts and ComfyUI history timing races.

### Highlights

- Incomplete or transient ComfyUI history rows are no longer treated as execution failures merely because they are not yet explicitly successful.
- `execution_success` WebSocket events are accepted as terminal success evidence even when `/history/<prompt_id>` has not finished persisting yet.
- Message-only `execution_success` history is normalized before passing through the older reconciliation layer so it cannot be misclassified as a generic failure.
- Explicit `execution_error` and `execution_interrupted` evidence remains authoritative; a delayed success observation cannot overwrite a specific terminal failure.
- Recent v0.4.2 jobs with the exact generic false-failure signature may self-correct only when ComfyUI history still contains explicit success evidence.
- Disk files do not redefine task state. If ComfyUI history has already been removed, v0.4.3 does not infer success from a leftover MP4 filename.

### Verification

- Regression tests cover empty/not-ready history on `execution_success`, ambiguous non-terminal history, message-only success history, explicit execution errors, and history-backed repair of the known v0.4.2 generic false-failure signature.
- Existing concurrency coverage still requires explicit WebSocket terminal failures to win over delayed reconcile results.
- Full CI covers minimum dependencies, repository/history safety, Windows and Ubuntu on Python 3.11 / 3.13, pytest, JavaScript syntax checks, i18n smoke, and package builds.

### Known limitation

- A task that was already misclassified by an older version and whose ComfyUI history has since been cleared is not automatically rewritten from filesystem evidence. The generated file may still exist on disk, but v0.4.3 keeps task state evidence-based rather than guessing from filenames.

## v0.4.2 — H3 FL2VA Unified Modes

Comfy Remote v0.4.2 introduces one product-level FL2VA creation entry that routes to three retained physical ComfyUI workflows.

### Highlights

- `MiniMax H3 FL2VA` now exposes `v4_600step`, `LightX2V`, and `original` as generation modes under one creation entry while keeping the physical workflows independently manageable.
- `v4_600step` is the first-use default and the selected mode is remembered in the browser; Retry restores the actual mode used by the retried task.
- Optional H3 prompt standardization is exposed as an Advanced Setting and defaults to enabled.
- The standardizer receives its own randomized hidden seed, separate from the video seed.
- Standardized prompt text is captured from the actual ComfyUI `PreviewAny` history output and shown next to the raw prompt in task details.
- H3 reference-aspect routing uses the workflow's own `H3AspectRouter`, and reference-image preprocessing supports original plus 0.5 / 1.0 / 1.5 / 2.0 MP downscale-only policies.
- Physical workflow disable/enable state remains authoritative for whether each generation mode is available.

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
