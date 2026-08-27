# v0.3 Public Readiness Acceptance — Completed Phase Record

> Status: **Public Readiness product acceptance completed.**
>
> This document records the v0.3 Phase 1 gate. The final `v0.3.0` Public Beta release candidate still requires the current release commit to pass automated checks and a short smoke test before tagging.

CI cannot replace real Windows / GPU / mobile acceptance, and old real-machine acceptance cannot replace validation of the final release commit. Both layers are required.

## Product acceptance completed during v0.3

The following areas were implemented and exercised through automated tests and/or real Windows acceptance:

- [x] Public CLI: setup, Panel lifecycle, Doctor, autostart.
- [x] Setup-generated configuration without requiring users to hand-edit TOML.
- [x] Windows Portable ComfyUI discovery and lifecycle control.
- [x] Portable launch-script discovery preserving real startup flags.
- [x] Panel background process identity / health / unknown-port safety boundaries.
- [x] Tailscale identity and Serve configuration path.
- [x] Doctor PASS/WARN/FAIL and privacy-safe report output.
- [x] Generic ComfyUI API Workflow import / Configurator / Preflight / Runtime Test.
- [x] Real non-H3 Workflow generation and result viewing during acceptance.
- [x] H3 treated as optional Bundled / Verified examples rather than a core dependency.
- [x] Windows autostart registration path.
- [x] Real Windows setup on separate clean environments without existing Comfy Remote config/data.

A dedicated acceptance environment also exposed and fixed the case where H3 nodes/workflows existed but H3 model assets did not: missing optional H3 assets must not make a generic Comfy Remote installation `NOT READY`.

## Final release-candidate automated gate

For the exact commit that will become `v0.3.0`:

- [ ] Windows Python 3.11 pytest.
- [ ] Windows Python 3.13 pytest.
- [ ] Linux Python 3.11 pytest.
- [ ] Linux Python 3.13 pytest.
- [ ] minimum-dependencies pytest/build.
- [ ] frontend JavaScript syntax checks.
- [ ] `python scripts/check_repository.py`.
- [ ] `python -m build`.

If GitHub Actions cannot acquire a runner and reports zero executed steps, that is an infrastructure failure, **not a passing gate**. The release record must not call CI green until jobs actually execute.

## Final release-candidate smoke test

The final public `main` candidate only needs one short end-to-end smoke, not another full Phase 1 matrix:

```text
clean clone of final main
→ Install-ComfyRemote.ps1
→ setup
→ doctor
→ start/status
→ phone access through Tailscale
→ import one ordinary API Workflow
→ real generation
→ result visible on phone
```

This smoke confirms that the public `main` tree itself—not an old development branch—still follows the documented first-run path.

## Acceptance principles retained

### A — H3 is optional

A user who does not use MiniMax H3 must still be able to run the Panel and their own compatible ComfyUI API Workflow. H3 availability is not the generic installation success criterion.

### B — Happy path hides internal implementation concepts

A first-time user should not need to understand TOML, PID tracking, Task Scheduler internals, Tailscale LoginName, or ComfyUI node IDs to complete the normal setup path.

### C — Diagnosable

Problems should be reportable with:

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe doctor --report
```

The output is automatically redacted, but users are still instructed to review it before posting publicly.

### D — Ordinary API Workflow

The generic success path is:

```text
API Workflow export
→ import
→ Configurator analysis
→ Preflight
→ Runtime Test
→ creation
→ artifact
```

No fixed `width / height / batch_size` contract is required.

### E — Login recovery

Windows login autostart is part of the supported v0.3 deployment path. More advanced crash/watchdog recovery is explicitly deferred to v0.4 Reliability / Recovery.
