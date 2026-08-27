# Windows first run: using Comfy Remote for the first time

**English** | [简体中文](GETTING_STARTED_WINDOWS.zh-CN.md)

This guide is for Windows users who are **new to Comfy Remote**. It assumes you can already use ComfyUI, but does not require familiarity with Python projects, TOML, Task Scheduler, node IDs, or Tailscale Serve.

The goal is not merely to install the program, but to complete the full path:

```text
Prepare the computer
→ Install Comfy Remote
→ Setup
→ Doctor
→ Open the Panel on your phone
→ Import your own API Workflow
→ Preflight / Test
→ First real generation
→ View the result on your phone
```

> **v0.3.0 is a Public Beta.** Windows 10/11 is the primary validated platform and Tailscale is the primary remote-access path today.

---

## 1. Confirm ComfyUI itself works first

Do not install Comfy Remote yet.

Start the ComfyUI installation you normally use on this Windows computer and confirm that at least one workflow can generate successfully locally.

Comfy Remote does not install ComfyUI, models, or third-party Custom Nodes. It provides remote control and a mobile creation UI on top of an already working local ComfyUI environment.

**MiniMax H3 is not required.** The six bundled H3 workflows are only Bundled / Verified examples. If you do not use H3, unavailable H3 workflows or H3 `WARN` results in Doctor can be ignored.

---

## 2. Prepare Git, Python, and Tailscale

### Git for Windows

If Git is not installed, install the official Git for Windows:

<https://git-scm.com/download/win>

Open a new PowerShell window after installation and check:

```powershell
git --version
```

A version number is enough.

### Python

Install a **stable Python 3.11 or newer**:

<https://www.python.org/downloads/windows/>

Do not use `alpha`, `beta`, or `rc` prerelease Python builds for the public Comfy Remote installation path. During installation, enable the option that adds Python to PATH if available (`Add python.exe to PATH` or similar wording).

Open a new PowerShell window and check:

```powershell
python --version
```

For example:

```text
Python 3.13.x
```

If `python` opens the Microsoft Store, is not found, or reports a prerelease such as `3.14.0a1`, fix the Python installation before continuing.

### Tailscale (only needed for remote phone access)

Download:

<https://tailscale.com/download>

Install Tailscale on both the computer and phone and sign in to the **same tailnet**. On the computer, check:

```powershell
tailscale status
```

Confirm that it is connected.

If you only want to test locally on the computer for now, Tailscale is optional; Setup can finish in local mode.

---

## 3. Download and install Comfy Remote

In PowerShell, go to the folder where you want to keep the project, then run:

```powershell
git clone https://github.com/evan-zzz-zhang/comfyui-remote-panel.git
cd comfyui-remote-panel
.\scripts\windows\Install-ComfyRemote.ps1
```

The installer will:

```text
Check for a stable Python
→ Create the project's .venv
→ Install Comfy Remote
→ Enter the Setup wizard automatically
```

It does not modify ComfyUI core code.

### If PowerShell blocks the script

If you get an Execution Policy error, you can relax policy only for the **current PowerShell process**:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
```

Then run again:

```powershell
.\scripts\windows\Install-ComfyRemote.ps1
```

---

## 4. Setup: what each choice means

On first install, Setup tries to detect what it can automatically and only asks when a real choice exists.

### 4.1 Where is ComfyUI?

If only one ComfyUI installation is found, Setup uses it directly.

If multiple installations are found, you will see a list similar to:

```text
Multiple possible ComfyUI installations found:
  [1] ...
  [2] ...
  [0] Enter a path manually
Choose ComfyUI:
```

Choose the installation you actually want to control remotely.

If automatic discovery finds nothing, Setup asks for the ComfyUI root directory. For Windows Portable you can enter:

```text
<drive>:\your-folder\ComfyUI_windows_portable
```

or its nested directory:

```text
<drive>:\your-folder\ComfyUI_windows_portable\ComfyUI
```

Setup normalizes either form to the Portable bundle root.

### 4.2 Allow Comfy Remote to control ComfyUI?

You will see a prompt equivalent to:

```text
Allow Comfy Remote to start, stop, and restart ComfyUI [y/N]:
```

- Enter `y` if you want the phone's Device page to start / stop / restart ComfyUI later.
- Press Enter to leave this disabled if you always start ComfyUI yourself on the computer.

This is a lifecycle-control permission. It does not affect importing or remotely submitting workflows.

### 4.3 Choose the ComfyUI launch method

This appears only when lifecycle control is enabled and multiple valid Portable launch scripts are detected.

For example:

```text
Multiple ComfyUI launch scripts detected:
  [1] StartComfyUI.bat
      -s ComfyUI/main.py --windows-standalone-build --enable-manager
  [2] StartComfyUI_SageAttention.bat
      -s ComfyUI/main.py --windows-standalone-build --enable-manager --use-sage-attention
  [0] Use the Comfy Remote default launch command
Choose launch method:
```

**Choose the launch method you actually use day to day.**

Comfy Remote extracts the script's static Python launch arguments and starts Python directly. It does not silently remove real arguments such as `--enable-manager` or `--use-sage-attention` for UI convenience.

When Comfy Remote launches ComfyUI on Windows, the ComfyUI console window is visible by default so loading and errors can be observed. The Panel itself does not leave an extra black console window open.

### 4.4 Tailscale

If the computer is already signed in to Tailscale, Setup displays the current identity and asks whether to enable remote access.

Choose yes if you want phone access.

Setup configures Tailscale Serve and displays an address similar to:

```text
Remote URL: https://...ts.net
```

**Keep this address; you will open it on your phone later.**

Do not enable Tailscale Funnel and do not expose Panel port 8190 or ComfyUI port 8188 with public port forwarding.

### 4.5 Windows login autostart

On the first configuration, Setup asks whether Comfy Remote should start after Windows login.

Keeping this enabled is recommended. The Panel will recover automatically after login instead of requiring a manual `start` each time.

When you later run Setup in check/update mode, an existing valid autostart registration is preserved/refreshed automatically instead of asking the same question again.

### If `config.toml` already exists

Running Setup again presents three explicit choices:

```text
  [1] Check and update
  [2] Create a new configuration (back up the old file automatically)
  [3] Exit
Choose action:
```

There is no hidden default; enter `1`, `2`, or `3`.

---

## 5. Run Doctor first

After Setup:

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe doctor
```

Focus on:

```text
Core
ComfyUI
Remote access
Workflow compatibility
Overall
```

Core dependencies should report `PASS` when healthy.

A `WARN` does not always mean installation failed. Examples include:

- Tailscale is not installed or signed in;
- bundled H3 workflows you do not use are missing models;
- an optional workflow is missing a Custom Node.

Fix blocking `FAIL` results first, such as an unreachable ComfyUI API or an unwritable input directory.

For a support report:

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe doctor --report
```

This produces redacted Markdown intended for an Issue. **Still review it yourself before posting publicly; do not upload configuration files, databases, full logs, or real media assets.**

---

## 6. Start the Panel

If Windows autostart already started the Panel, `start` safely recognizes the existing instance.

Run:

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe start
.\.venv\Scripts\comfyui-remote-panel.exe status
```

A healthy status looks similar to:

```text
Panel      Running
PID        12345
Port       8190
Health     OK
```

Stop / restart:

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe stop
.\.venv\Scripts\comfyui-remote-panel.exe restart
```

---

## 7. Open Comfy Remote for the first time

### Remote from your phone

Make sure Tailscale is connected on the phone and signed in to the same tailnet, then open the Setup URL:

```text
https://...ts.net
```

If you forgot the URL, check on the computer:

```powershell
tailscale serve status
```

### Local-only testing on the computer

If Setup uses local auth, open:

```text
http://127.0.0.1:8190
```

If Tailscale auth is configured, a direct localhost request returning 403 outside the health endpoint is expected because it lacks the identity header injected by Tailscale Serve. Use the Tailscale Serve HTTPS address instead.

---

## 8. The most important step: export the correct ComfyUI API Workflow

Comfy Remote requires an **API Workflow JSON**, not the normal UI Workflow JSON produced by the usual save-workflow action.

Back in ComfyUI:

1. Open and run the workflow you want to use remotely; confirm it succeeds locally.
2. If the API-format export option is hidden, open ComfyUI Settings and enable **Dev Mode / Developer Mode Options** (wording varies by frontend version).
3. Use **Save (API Format)**, **Export (API)**, or the equivalent API-format export action in your version.
4. Save the resulting `.json` file.

As a rough check, an API Workflow normally uses node IDs as top-level keys and each node contains `class_type` and `inputs`. It is not primarily a canvas/layout file full of positions, colors, and widget UI state.

If Comfy Remote explicitly says the uploaded file is not an API Workflow, do not hand-edit the JSON. Go back to ComfyUI and export the API format again.

---

## 9. Import your workflow into Comfy Remote

Open:

```text
Settings
→ Workflows
→ Import workflow
```

Then:

1. Select the API Workflow JSON you just exported.
2. Review the Configurator 2.0 analysis.
3. Check the detected prompts, media inputs, parameters, and primary output.
4. If there are multiple candidates or low-confidence items, choose according to the real meaning of your workflow.
5. If needed, use **Advanced · Manual node mapping** to expose literal inputs that automatic analysis cannot identify reliably.
6. Save and enable the workflow.
7. Run one **Test**.

The test **submits a real ComfyUI job and uses the GPU**. It is not only JSON validation.

### Configurator 2.0 does not require fixed parameters

Do not assume analysis failed just because the import page does not show `width`, `height`, or `batch_size`.

Different workflows have different capabilities. For example, img2img may inherit the input image size; a video custom node may encapsulate dimensions internally; some workflows do not allow remote batch changes at all.

Comfy Remote uses:

```text
Schema
+ Graph connections
+ conservative heuristic fallback
+ explicit user mapping
```

to decide what should be exposed instead of forcing every workflow into one fixed form.

---

## 10. First real generation

Return to:

```text
Create
```

Select the workflow you just enabled.

According to the capabilities it actually declares:

- enter the prompt;
- upload required images / videos / audio;
- adjust parameters that are safe to edit remotely;
- submit the job.

Then open Jobs. The normal path is:

```text
Submit
→ Queued
→ Running
→ Completed
→ View / download result
```

If it fails:

1. read the job error summary;
2. inspect ComfyUI's own console;
3. run `doctor`;
4. check [Troubleshooting](TROUBLESHOOTING.md).

---

## 11. What counts as a successful first installation?

The setup is genuinely complete when these are true, not merely when the service starts:

- [ ] `doctor` has no core blocking `FAIL`.
- [ ] The phone can open Comfy Remote through Tailscale HTTPS (or local mode works on the computer).
- [ ] You successfully imported **your own** API Workflow.
- [ ] Preflight has no unresolved blocking `FAIL`.
- [ ] Runtime Test succeeds, or you clearly know the failure belongs to the workflow's own model/node environment.
- [ ] The Create page exposes the inputs the workflow actually needs.
- [ ] One real job completes.
- [ ] The result is visible and openable from the phone's Jobs page.

**If you do not use H3, availability of the six bundled H3 workflows is not part of this success criterion.**

---

## 12. Windows login autostart

Check status:

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe autostart status
```

Install / remove manually:

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe autostart install
.\.venv\Scripts\comfyui-remote-panel.exe autostart remove
```

---

## 13. Update the project

Public Beta releases may move quickly. Make sure no important job is running, then:

```powershell
git pull
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\comfyui-remote-panel.exe setup
.\.venv\Scripts\comfyui-remote-panel.exe doctor
.\.venv\Scripts\comfyui-remote-panel.exe restart
```

Setup's check/update path tries to preserve valid settings and backs up `config.toml` to `config.toml.bak` before rewriting it.

---

## CLI language override

CLI output follows the operating-system locale by default. You can override it per command:

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe setup --lang en
.\.venv\Scripts\comfyui-remote-panel.exe doctor --lang zh-CN
```

Or set `COMFY_REMOTE_LANG` to `en` or `zh-CN` for the current shell/environment.

The Web Panel keeps its own browser-side language preference under **Settings → Language**.

---

## Next

- Workflow recognition and Configurator 2.0: [WORKFLOWS.md](WORKFLOWS.md)
- Common problems: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- Security boundaries: [../SECURITY.md](../SECURITY.md)
- Current roadmap: [TODO.md](TODO.md)
