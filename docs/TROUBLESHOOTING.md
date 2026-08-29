# Troubleshooting

**English** | [简体中文](TROUBLESHOOTING.zh-CN.md)

Always start troubleshooting with:

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe doctor
```

When you need to report a problem, also run:

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe doctor --report
```

## Setup cannot find ComfyUI

Make sure the path you enter is one of these two root layouts:

```text
ComfyUI_windows_portable\
  python_embeded\
  ComfyUI\
    main.py
```

or:

```text
ComfyUI\
  main.py
```

The wizard does not scan every drive. You can enter the root manually, or set the `COMFYUI_ROOT` environment variable and run Setup again.

## Cannot connect to port 8188

Open `http://127.0.0.1:8188` in a browser on the computer first. If it does not open, fix ComfyUI itself before troubleshooting Comfy Remote. Comfy Remote does not replace the basic ComfyUI installation.

## Port 8190 is already in use

Run:

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe status
```

If it reports `port-occupied`, the Panel will not force-kill an unknown process. Identify and close the program using port 8190, then start Comfy Remote again.

## Browser returns 403

In Tailscale auth mode, a direct request to `http://127.0.0.1:8190` is expected to return 403 outside `/healthz` because it does not contain the identity header injected by Tailscale Serve.

Use the HTTPS address shown by `tailscale serve status`. If you only need local debugging, run Setup again and choose local auth.

## Tailscale is not signed in

Check:

```powershell
tailscale status
```

Make sure the computer and phone are signed in to the same tailnet. After signing in, run Setup again.

## The Serve address does not open

Check:

```powershell
tailscale serve status
tailscale status
.\.venv\Scripts\comfyui-remote-panel.exe status
```

All three layers must be healthy at the same time: the Panel must be healthy on `127.0.0.1:8190`, the Tailscale backend must be connected, and Serve must point to 8190. To configure Serve again, run `tailscale serve --bg 8190`.

## The phone cannot open it but the computer can

Make sure Tailscale is connected on the phone, both devices are in the same tailnet, and you are using the `https://...ts.net` Serve address rather than a LAN IP. Also check whether `allowed login` in `doctor` reports an identity mismatch.

## Workflow is missing nodes

Workflow import/validation uses the current ComfyUI `object_info` to verify that each `class_type` exists. Install the matching custom node, restart ComfyUI, run `doctor` again, and retest the workflow.

Do not treat one bundled H3 workflow missing nodes as a Panel installation failure. Bundled H3 workflows are optional verified examples, so missing optional dependencies should be a `WARN`.

## Workflow is missing models

If the node exists but the required model is absent from the node's model list, the workflow is shown as unavailable or missing dependencies. Put the model in the directory that node actually reads, confirm ComfyUI itself can load it, then test again.

## Import succeeds but Runtime Test fails

A successful import only proves that the JSON, node structure, and mappings can be parsed. A real Runtime Test can still expose missing models, incorrect paths, insufficient VRAM, custom-node runtime errors, or output nodes that do not produce the expected artifact.

Read the job error summary and ComfyUI console, then include `doctor --report` when filing a compatibility Issue.

## Image upload fails

Verify the file format, make sure the ComfyUI `input` directory is writable, confirm the Doctor input-directory check is `PASS`, and make sure the disk has enough free space.

## The result cannot be found after generation

Confirm the ComfyUI job itself completed, the workflow uses the correct SaveImage / SaveVideo / output node, the `output` directory is readable, and the output file was not moved or cleaned during generation. If a custom workflow has multiple output candidates, confirm the primary output during import.

## The Panel was restarted while a job was running

Restarting Comfy Remote does not intentionally cancel a prompt that ComfyUI has already accepted. After restart, the Panel reconciles active jobs from ComfyUI queue/history state. v0.4.3 no longer treats an incomplete history row as a failure and accepts explicit `execution_success` evidence even if the final history payload is still being persisted.

If a task was already misclassified by an older version and ComfyUI has since removed that task's history, v0.4.3 does not infer success from a leftover MP4 filename. The file may still exist in the managed output directory, but task state remains based on explicit ComfyUI evidence.

## Panel does not open after restart

Run `status` and `doctor`. If background startup failed, inspect:

```text
data\panel-launch.log
data\panel.log
```

Do not manually kill unfamiliar Python processes. `stop` verifies process identity before terminating anything.

## Comfy Remote does not start after Windows login

Check:

```powershell
.\.venv\Scripts\comfyui-remote-panel.exe autostart status
```

If needed, run `autostart remove` and `autostart install` again, then perform an actual Windows sign-out/sign-in test.

## All H3 workflows are unavailable

This does not affect ordinary ComfyUI API Workflows. H3 workflows depend on the corresponding MiniMax H3 custom nodes, models, VAE, text encoder, and related environment. The public project treats them as Bundled / Verified examples, not a core Comfy Remote installation requirement.
