# Changelog

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
