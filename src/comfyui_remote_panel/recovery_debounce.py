from __future__ import annotations


UNRESPONSIVE_FAILURE_THRESHOLD = 3
_TRANSITIONAL_STATES = {"starting", "stopping", "start_failed"}


def install() -> None:
    """Debounce Recovery Lite unresponsive classification across health polls."""

    from . import metrics as metrics_module

    current_collect_once = metrics_module.MetricsService._collect_once
    if getattr(current_collect_once, "_recovery_debounce", False):
        return

    async def collect_once_debounced(self):
        snapshot = await current_collect_once(self)
        comfy = snapshot.setdefault("comfyui", {})
        control = comfy.get("control")
        if not isinstance(control, dict):
            return snapshot

        if comfy.get("online"):
            return snapshot

        control_state = str(control.get("state") or comfy.get("control_state") or "")
        if control_state in _TRANSITIONAL_STATES:
            return snapshot

        managed_process_alive = bool(control.get("managed_process_alive"))
        failures = max(0, int(getattr(self, "_comfy_failures", 0) or 0))
        unresponsive = managed_process_alive and failures >= UNRESPONSIVE_FAILURE_THRESHOLD
        state = "unresponsive" if unresponsive else "offline"

        control["state"] = state
        control["can_force_restart"] = bool(control.get("can_force_restart")) and unresponsive
        comfy["state"] = state
        comfy["control_state"] = state
        return snapshot

    collect_once_debounced._recovery_debounce = True  # type: ignore[attr-defined]
    metrics_module.MetricsService._collect_once = collect_once_debounced
