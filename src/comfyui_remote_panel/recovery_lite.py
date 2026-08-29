from __future__ import annotations

from pathlib import Path
from typing import Any

from aiohttp import web


def install() -> None:
    """Install the small, explicit Recovery Lite compatibility layer."""

    from . import app as app_module
    from . import lifecycle as lifecycle_module
    from . import metrics as metrics_module

    original_snapshot = lifecycle_module.ComfyLifecycle.snapshot
    original_trigger = lifecycle_module.ComfyLifecycle.trigger

    def snapshot_recovery_lite(self, online: bool, **kwargs):
        snapshot = original_snapshot(self, online, **kwargs)
        if online:
            snapshot["can_force_restart"] = False
        return snapshot

    async def trigger_recovery_lite(self, action: str):
        if action == "force_restart" and await self._is_online():
            raise lifecycle_module.LifecycleError("ComfyUI 当前在线，请使用普通重启")
        return await original_trigger(self, action)

    lifecycle_module.ComfyLifecycle.snapshot = snapshot_recovery_lite
    lifecycle_module.ComfyLifecycle.trigger = trigger_recovery_lite

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

    if getattr(app_module.create_app, "_recovery_lite_frontend", False):
        return
    original_create_app = app_module.create_app

    def create_app_recovery_lite(*args: Any, **kwargs: Any):
        application = original_create_app(*args, **kwargs)
        static_dir = Path(__file__).with_name("static")

        @web.middleware
        async def recovery_lite_asset(request: web.Request, handler):
            if request.path == "/static/app.js":
                base = (static_dir / "app.js").read_text(encoding="utf-8")
                extension = (static_dir / "recovery_lite.js").read_text(encoding="utf-8")
                return web.Response(
                    text=f"{base}\n\n{extension}\n",
                    content_type="application/javascript",
                )
            return await handler(request)

        application.middlewares.append(recovery_lite_asset)
        return application

    create_app_recovery_lite._recovery_lite_frontend = True  # type: ignore[attr-defined]
    app_module.create_app = create_app_recovery_lite
