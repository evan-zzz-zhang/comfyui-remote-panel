# Comfy Remote

**English** | [简体中文](README.zh-CN.md)

**Run your local ComfyUI workflows from your phone.**

> **Current status: v0.4.4 Public Beta.**
>
> Generic ComfyUI API Workflow support, mobile creation, retained-media Retry, H3 FL2VA unified generation modes, task reconciliation hardening, self-healing Windows installation, Windows Setup, Tailscale remote access, Doctor diagnostics, and guarded Recovery Lite controls are available. Full automatic watchdog recovery, multi-host support, and Wake-on-LAN are not implemented.

Comfy Remote is a mobile-first remote creation panel for ComfyUI. It runs on the Windows computer that hosts ComfyUI and turns locally verified **ComfyUI API Workflows** into a phone-friendly interface for selecting workflows, adding media, editing prompts, submitting jobs, and reviewing results.

The current v0.4.4 baseline builds on **Public Readiness + Configurator 2.0** with a clearer Specialized / Generic creation boundary, explicit Seed Policy, reference-image resolution preprocessing, guarded manual ComfyUI recovery, reliable historical-media Retry, H3 FL2VA product-level mode routing, safer final-state reconciliation, and Windows environment self-healing when an existing project `.venv` is damaged. It still avoids silently rewriting arbitrary workflows or exposing ComfyUI directly to the network.

## What it does

- Imports ordinary ComfyUI **API Workflows** and analyzes workflow capabilities, media inputs, prompts, editable parameters, and primary outputs.
- Uses **Schema + Graph + heuristic fallback** instead of assuming every workflow must contain fixed fields such as `width`, `height`, or `batch_size`.
- Configurator 2.0 presents explicit confirmation and advanced manual mapping for uncertain cases; it does not silently rewrite the workflow graph to fit the UI.
- Supports image / video / audio / file artifacts and job history.
- Supports submit, queue, live progress, cancel, Retry, result preview, and download.
- Restores retained historical reference media on Retry without requiring the same file to be reselected or re-uploaded from the phone; retained inputs can still be replaced or removed explicitly.
- Shows actual produced image width, height, format, and file size when the output file is available.
- Provides `randomize / fixed / increment` Seed Policy and reference-image resolution preprocessing while keeping Generic controls bound to real Workflow inputs.
- Groups the three bundled H3 FL2VA physical workflows behind one creation entry with `v4_600step`, `LightX2V`, and `original` modes while keeping their physical workflow enable/disable state authoritative.
- Hardens task reconciliation so incomplete ComfyUI history is not treated as failure and explicit `execution_success` remains success evidence even when final history persistence is slightly delayed.
- Provides guarded Recovery Lite controls for managed ComfyUI processes; an `unresponsive` state requires three consecutive failed health polls while the recorded process is still independently verified alive.
- Provides `setup`, `start / stop / restart / status`, `doctor`, and Windows login autostart commands.
- The Windows installer actively health-checks an existing project `.venv`; an unhealthy environment is backed up and rebuilt instead of being reused or silently replaced by the global Python runtime.
- Detects existing Windows Portable ComfyUI launch scripts and preserves their real static arguments, including options such as `--enable-manager` and `--use-sage-attention`.
- Recommends Tailscale Serve for phone access while keeping both the Panel and ComfyUI bound to localhost.
- Public documentation is available in English and Simplified Chinese; the current Web Panel release keeps the accepted stable Chinese UI baseline.
- Includes six MiniMax H3 workflows as **Bundled / Verified examples**. Missing H3 nodes or models do not block you from using your own workflows.

## Quick Start — Windows

### Requirements

- Windows 10/11.
- A **stable** Python 3.11 or newer. Alpha, beta, and RC Python builds are not supported as the public installation path.
- Git for Windows.
- A ComfyUI installation that can already generate successfully on the same computer.
- For remote phone access: Tailscale installed on both the computer and phone, signed in to the same tailnet.

First-time users should follow the complete [Windows first-run guide](docs/GETTING_STARTED_WINDOWS.md). It covers Git/Python/Tailscale preparation, every Setup choice, exporting an API Workflow, and the full path to a successful first generation from a phone.

### Install

```powershell
git clone https://github.com/evan-zzz-zhang/comfyui-remote-panel.git
cd comfyui-remote-panel
.\scripts\windows\Install-ComfyRemote.ps1
```

The installer checks the base Python, health-checks the project's existing `.venv` when present, preserves and rebuilds it if unhealthy, installs Comfy Remote into `.venv`, verifies the package import, and then enters the Setup wizard. The base/global Python is used to bootstrap the project environment; normal Panel commands continue to run from `.venv`.

After Setup:

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe doctor
.\.venv\Scripts\comfyui-remote-panel.exe start
.\.venv\Scripts\comfyui-remote-panel.exe status
```

If Setup configured Tailscale Serve, open the displayed `https://…ts.net` address on your phone.

### Update

For a normal source update, make sure no important job is running, then:

```powershell
git pull
.\.venv\Scripts\comfyui-remote-panel.exe restart
```

Because Comfy Remote is installed in editable mode, a normal `git pull` updates the source used by the existing `.venv`; restarting the Panel reloads that code. Re-run `Install-ComfyRemote.ps1` only when the release changes dependencies or installation metadata, when Setup/configuration must be refreshed, or when the Python / `.venv` environment needs repair.

## Workflow compatibility

First confirm that the target workflow runs correctly in ComfyUI, then export it as an **API Workflow JSON**. A normal UI Workflow JSON is a different format.

Configurator 2.0 does not simply search for a few fixed nodes. Its compatibility analysis combines:

1. **JSON / Structure** — whether the file is a valid API Workflow node structure.
2. **Schema** — current ComfyUI `/object_info` data for node input types, enums, numeric ranges, and custom-node capabilities.
3. **Graph** — node connections used to infer prompts, media inputs, size sources, sampler paths, and output semantics.
4. **Heuristic fallback** — conservative inference when schema/graph evidence is still insufficient, with confidence surfaced instead of silent guessing.
5. **Preflight** — aggregated `PASS / WARN / FAIL` checks across JSON / Node / Input / Parameter / Output / Runtime layers.
6. **Runtime Test** — a real ComfyUI submission. Model files, VRAM limits, and third-party node behavior are ultimately validated by actual execution.

A valid img2img workflow therefore does not need an `EmptyLatentImage`, and a workflow may have no remotely editable `width / height / batch_size` at all. Comfy Remote exposes the creation inputs the workflow actually has and that can be safely identified or explicitly mapped by the user.

See [Workflow / Configurator 2.0 guide](docs/WORKFLOWS.md).

## Doctor / Feedback

When something goes wrong, start with:

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe doctor
```

For a GitHub Issue, prefer attaching:

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe doctor --report
```

The report uses `PASS / WARN / FAIL` and redacts user directories, email addresses, Tailscale hostnames, and obvious secret values. You should still review it manually before posting it publicly.

**If you do not use MiniMax H3, unavailable bundled H3 workflows or H3 `WARN` results in Doctor can be ignored.** They do not mean the Comfy Remote installation failed.

See [Troubleshooting](docs/TROUBLESHOOTING.md) for common issues.

## Tailscale security model

Recommended path:

```text
Phone → Tailscale HTTPS Serve → 127.0.0.1:8190 Comfy Remote → 127.0.0.1:8188 ComfyUI
```

- The Panel is forced to listen on `127.0.0.1:8190`.
- ComfyUI stays local on `8188`.
- Tailscale auth mode authorizes requests using the login identity header injected by Serve.
- Do not use Funnel and do not expose ports 8190 or 8188 directly to the public internet.
- Third-party ComfyUI Custom Nodes remain a local code-execution boundary; Comfy Remote does not sandbox them.

See [SECURITY.md](SECURITY.md) for details.

## Known limitations — v0.4.4 Public Beta

- **Windows 10/11 is the primary validated platform.** Linux participates in CI, but the public install and real-device path is currently Windows-first.
- **Tailscale is the primary remote transport today.** The core architecture is not intended to be permanently tied to Tailscale, but other transports do not yet have an equivalent public installation path.
- **Recovery Lite is manual, not a full watchdog.** The Panel can identify a verified managed process as unresponsive after three consecutive failed health polls and offer a guarded force restart, but it does not automatically restart crash loops, recover GPU/driver faults, or resubmit interrupted jobs.
- **Real hard-hang/OOM recovery remains field-validated rather than manufactured for release testing.** Safety and debounce paths are automated-test covered, but v0.4.4 does not intentionally force GPU/ComfyUI hangs during acceptance.
- **Task state remains evidence-based.** v0.4.4 retains the v0.4.3 history-timing fix, but it does not retroactively infer success from a leftover MP4 if an older version already misclassified a task and ComfyUI later cleared that task's history.
- **No Wake-on-LAN.** Waking a sleeping or powered-off computer from outside the machine is not part of v0.4.4.
- **No multi-host support.** One Panel currently maps to one local ComfyUI installation.
- **Third-party Custom Node compatibility depends on schema and real runtime behavior.** Configurator 2.0 analyzes what it can, but cannot guarantee automatic understanding of every custom node.

See [TODO / Roadmap](docs/TODO.md) for the next development baseline.

## CLI

```text
comfyui-remote-panel setup

comfyui-remote-panel start
comfyui-remote-panel stop
comfyui-remote-panel restart
comfyui-remote-panel status

comfyui-remote-panel doctor
comfyui-remote-panel doctor --report

comfyui-remote-panel autostart install
comfyui-remote-panel autostart status
comfyui-remote-panel autostart remove
```

The legacy foreground launch form is still supported:

```powershell
comfyui-remote-panel --config config.toml
```

## Development

```powershell
python -m pytest
python scripts/check_repository.py
python -m build
```

CI covers Windows / Linux, Python 3.11 / 3.13, and minimum-dependencies. Real GPUs, unfamiliar Windows machines, phone access, and third-party nodes cannot be fully replaced by CI.

Read [CONTRIBUTING.md](CONTRIBUTING.md) before contributing.

## Documentation

- [Windows first-run guide](docs/GETTING_STARTED_WINDOWS.md) · [简体中文](docs/GETTING_STARTED_WINDOWS.zh-CN.md)
- [Troubleshooting](docs/TROUBLESHOOTING.md) · [简体中文](docs/TROUBLESHOOTING.zh-CN.md)
- [Workflow / Configurator 2.0 guide](docs/WORKFLOWS.md) · [简体中文](docs/WORKFLOWS.zh-CN.md)
- [Release Acceptance](docs/ACCEPTANCE.md)
- [Public Readiness Acceptance](docs/PUBLIC_READINESS_ACCEPTANCE.md)
- [TODO / Roadmap](docs/TODO.md)
- [Security](SECURITY.md)