from __future__ import annotations


def install() -> None:
    """Keep Recovery Lite device states authoritative after v0.4 compatibility wrappers."""

    from . import metrics as metrics_module

    original_collect_once = metrics_module.MetricsService._collect_once

    async def collect_once_recovery_lite(self):
        snapshot = await original_collect_once(self)
        comfy = snapshot.setdefault("comfyui", {})
        control = comfy.get("control") if isinstance(comfy.get("control"), dict) else {}
        control_state = str(control.get("state") or comfy.get("control_state") or "")

        if comfy.get("online"):
            state = "online"
        elif control_state in {"starting", "stopping", "start_failed"}:
            state = control_state
        elif control_state == "unresponsive" or control.get("managed_process_alive"):
            state = "unresponsive"
        else:
            state = "offline"

        comfy["state"] = state
        comfy["control_state"] = control_state or None
        return snapshot

    metrics_module.MetricsService._collect_once = collect_once_recovery_lite
