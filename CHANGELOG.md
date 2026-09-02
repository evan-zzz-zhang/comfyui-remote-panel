# Changelog

## v0.4.8 — Ref2VA Workflow Family (implementation in progress)

### Highlights

- Adds one `MiniMax H3 Ref2VA` virtual creation entry backed by nine canonical `3 generation modes × 3 prompt backends` workflows.
- Preserves the Ref2VA collection contract: up to 9 images, 3 videos, and 3 audios remain independently bound to `MiniMaxH3ReferenceToVideo`.
- Adds Raw, Ollama, and Qwen3.5 4B prompt routes with representative-image/video-first-frame capture and standardized-prompt history recovery.
- Adds Auto, INT8, and FP16/BF16 model-profile metadata while retaining exact ComfyUI runtime selectors for variant lookup.
- Keeps the three legacy Ref2VA workflow IDs, history snapshots, retained media, and Retry mapping intact. The new routes are not yet declared GPU-field-tested.

## v0.4.6 — FL2VA Multi-Backend Prompt Standardization

Comfy Remote v0.4.6 keeps one H3 FL2VA creation entry while adding Off / Ollama / ComfyUI prompt-standardization routing and tightening FL2VA runtime progress, timing, retry, and recovery behavior.

### Highlights

- `MiniMax H3 FL2VA` keeps one creation entry with `original / LightX2V / v4_600step` generation modes and `关闭 / Ollama / ComfyUI` prompt-standardization modes.
- Three bundled ComfyUI Qwen3.5 4B physical workflows use `H3OfficialSkillPromptWriterQwen`; the physical presets remain manageable but hidden from the normal creation picker.
- Retry restores the actual generation mode and prompt-standardization backend. A frontend observer regression that could overwrite the restored backend with the browser preference was fixed.
- Qwen standardized prompts use the existing `standardized_prompt` Job field. Capture prefers the save-node metadata and falls back to the `PreviewAny` output directly connected to the Qwen writer when ComfyUI history does not expose the embedded video metadata.
- The obsolete visible Boolean prompt-standardization switch is removed while its hidden compatibility state remains available to older v0.4.2/v0.4.5 frontend logic.
- FL2VA reference-image aspect remains available and an otherwise unspecified aspect ratio falls back to `9:16`. A hidden-preset drift regression that could submit Ref2VA while rendering the FL2VA UI was fixed.
- FL2VA progress is standardization-aware (`prepare / standardize / sampling / decode / compose / save`). Only real sampler `value / max` data is used for continuous percentage; non-sampling stages do not invent time-based progress.
- Queue waiting no longer counts as execution time. Jobs expose queue waiting and execution durations separately, while standardization and sampling timings survive Panel restarts through private runtime metadata.
- Task cards show compact generation/standardization tags (`LightX2V`, `v4_600step`, `Ollama`, `Qwen3.5 4B`) only when meaningful.
- Device recovery adds guarded force-stop for a uniquely verified ComfyUI listener when the Panel no longer has a valid process record. Optional launch flags may differ, but executable, working directory, Python entrypoint, and listener identity must still match safely.
- The device overview conditionally shows `SageAttention` only when the actual currently verified ComfyUI listener command line contains `--use-sage-attention`; the configured start command is not used as a proxy for runtime state.
- Confirmed ComfyUI outages interrupt stale active jobs and freeze timing. Panel-managed Stop/Restart interrupts active jobs after shutdown is confirmed.

### Verification

- Regression coverage checks all 3 × 3 FL2VA routes, Qwen v4.4 graph preservation, reference-aspect delegation, Retry backend restoration, standardized-prompt metadata/PreviewAny fallback, queue/execution/standardization/sampling timing, semantic progress, offline interruption, FL2VA hidden-preset drift prevention, guarded force-stop, and actual-listener SageAttention detection.
- CI covers minimum dependencies, repository/history safety, Windows and Ubuntu on Python 3.11 / 3.13, pytest, JavaScript syntax/i18n checks, and package builds.
- Windows/phone field testing covered repeated Qwen3.5 FL2VA generation, task timing/tags, Retry backend restoration, and guarded force-stop behavior. Extreme GPU hard-hang/OOM behavior remains field-observed rather than intentionally manufactured.

## v0.4.5 — Artifact History Sync & Ollama Model Setting

Comfy Remote v0.4.5 keeps task history aligned with registered local outputs and makes the H3 FL2VA prompt-standardizer Ollama model configurable without adding a separate Ollama management layer.

### Highlights

- Jobs that previously registered output artifacts are reconciled against their actual managed local paths on startup/periodic reconciliation; deleting or moving the only registered output removes the corresponding Job from history.
- Multi-output Jobs keep surviving outputs when only some registered artifacts disappear, and the Job is purged only after all registered outputs are gone.
- Jobs that never registered an output are not removed merely because no file exists, and active `submitting / queued / running` Jobs are excluded from artifact cleanup.
- Artifact reconciliation does not redefine execution state: ComfyUI history/WebSocket evidence still decides `succeeded / failed / interrupted`.
- Purge is artifact-aware so secondary Generic output artifacts are cleaned together with tracked Job inputs instead of relying only on the legacy primary `job_files` entry.
- H3 FL2VA `original / LightX2V / v4_600step` expose `ollama_model` as an Advanced Setting, defaulting to `gemma4:e4b`; `unload_after=true` remains locked.
- The selected Ollama model is remembered in the browser, stored in each new Job's input values, and restored by Retry. Legacy FL2VA Jobs recover the old model from their workflow snapshot when available.
- Ollama process control, model installation/removal, model enumeration, and Ref2VA standardization remain out of scope.

### Verification

- Focused regression coverage checks single-output deletion, partial/all multi-output deletion, active/no-output protections, artifact-aware purge, all three FL2VA model bindings, blank-model fallback, legacy Retry restoration, and frontend preference/form wiring.
- CI covers minimum dependencies, repository/history safety, Windows and Ubuntu on Python 3.11 / 3.13, pytest, JavaScript syntax checks, i18n smoke, and package builds.
- Real Windows/phone acceptance for deleting or moving a produced artifact and changing the standardizer model remains a release acceptance step before merge/closeout.

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
- Prompt standardization is optional and enabled by default. The standardizer seed is randomized independently from the video seed so video variation no longer requires destabilizing the prompt-normalization path.
- The standardized prompt is captured from the workflow's `PreviewAny` history output, persisted inside Job input values, and exposed next to the raw prompt in task details.
- Physical workflow enabled/disabled state is authoritative; disabling one generation mode prevents new jobs from routing to that preset while preserving the other modes.

### Verification

- Regression coverage checks all three generation modes, default/remembered mode behavior, Retry restoration, independent standardizer seed behavior, standardized-prompt capture, and route-specific preset availability.
- CI covers minimum dependencies, repository/history safety, Windows and Ubuntu on Python 3.11 / 3.13, pytest, JavaScript syntax checks, i18n smoke, and package builds.

## v0.4.1 — Workflow Compatibility / Configurator 2.0

Comfy Remote v0.4.1 upgrades workflow import from fixed-node guessing to a semantic compatibility model built around API Workflow structure and live ComfyUI `/object_info` metadata.

### Highlights

- Workflow inspection now reports node connectivity, literal inputs, output candidates, inferred media inputs, semantic parameter candidates, and compatibility warnings instead of assuming every workflow has the same parameter set.
- Configurator 2.0 stores explicit parameter/media/output bindings in the workflow manifest and keeps manual Advanced Mapping for uncertain inputs.
- Unknown custom-node schemas are treated as compatibility uncertainty rather than silently becoming editable controls.
- Generic workflows can be imported, reviewed, enabled/disabled, tested, copied, exported, and used from the creation page without being forced into the H3 FL2VA/Ref2VA shape.
- Existing H3 families remain first-class built-ins and keep their specialized mobile UX.

### Verification

- Regression coverage checks semantic analysis, literal-input safety, multiple output candidates, media slot detection, workflow package round-tripping, status management, and Generic runtime execution.
- CI covers minimum dependencies, repository/history safety, Windows and Ubuntu on Python 3.11 / 3.13, pytest, JavaScript syntax checks, i18n smoke, and package builds.

## v0.4.0 — Public Beta

Comfy Remote v0.4.0 is the first public-beta baseline for the mobile-first Remote Panel architecture.

### Highlights

- Mobile creation UI, workflow management, task history, result playback/download, GPU/system telemetry, and guarded ComfyUI lifecycle controls are available through one lightweight Panel service.
- Built-in H3 FL2VA and Ref2VA workflows use constrained manifests so the phone can safely edit only intended inputs while ComfyUI retains the full generation graph.
- Tailscale is treated as a transport/authentication path rather than a core workflow dependency, keeping the architecture open to additional connection methods.
- Job execution, Retry media retention, output recovery, task reconciliation, and controlled ComfyUI start/stop/restart are managed by the Panel instead of exposing the raw ComfyUI API directly.

### Verification

- CI covers minimum dependencies, repository/history safety, Windows and Ubuntu on Python 3.11 / 3.13, pytest, i18n smoke, JavaScript syntax checks, and package builds.
