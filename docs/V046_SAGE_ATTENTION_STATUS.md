# v0.4.6 SageAttention Runtime Status

The Device page can show whether the currently running ComfyUI listener is actually using the `--use-sage-attention` launch flag.

## Device overview

The existing Device overview remains unchanged by default:

- Panel
- ComfyUI
- Queue tasks

When the actual ComfyUI process listening on the configured ComfyUI port has `--use-sage-attention` in its live command line, a fourth `SageAttention` chip is appended to the right of Queue tasks. When the flag is absent, no extra chip is shown.

## Source of truth

The status does not infer SageAttention from `config.toml`. The configured launch command can differ from the process that is currently running, for example when ComfyUI was restarted manually by another local tool.

Comfy Remote therefore checks the safely identified live ComfyUI listener and reads that process's actual command line. If the listener cannot be identified safely, the SageAttention chip is not shown.

This indicator is informational only. It does not change ComfyUI launch arguments, workflow graphs, or attention behavior.
