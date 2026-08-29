from __future__ import annotations

import asyncio
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from aiohttp import web


def _launch_stdin(platform_name: str, visible_window: bool):
    """Keep Windows visible-console std handles owned by the new console.

    Passing DEVNULL for stdin makes Python set STARTF_USESTDHANDLES.  When the
    Panel itself is detached, that also carries unusable stdout/stderr handles
    into a CREATE_NEW_CONSOLE child, producing a visible but completely blank
    ComfyUI console.  With all stdio left inherited/default, Windows initializes
    the fresh console handles normally and ComfyUI output remains visible.
    """

    if platform_name == "nt" and visible_window:
        return None
    return asyncio.subprocess.DEVNULL


def _repository_root() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        if (parent / ".git").exists():
            return parent
    return None


def _git_output(root: Path, *args: str) -> str:
    options: dict[str, Any] = {
        "cwd": root,
        "stdout": subprocess.PIPE,
        "stderr": subprocess.DEVNULL,
        "text": True,
        "timeout": 2,
        "check": True,
    }
    if os.name == "nt":
        options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
    result = subprocess.run(["git", *args], **options)
    return result.stdout.strip()


def _build_info(version: str) -> dict[str, Any]:
    info: dict[str, Any] = {
        "version": version,
        "branch": None,
        "commit": None,
        "tracked_dirty": None,
        "source": "package",
    }
    root = _repository_root()
    if root is None:
        return info
    try:
        commit = _git_output(root, "rev-parse", "HEAD")
        branch = _git_output(root, "rev-parse", "--abbrev-ref", "HEAD")
        tracked = _git_output(root, "status", "--porcelain", "--untracked-files=no")
    except (OSError, subprocess.SubprocessError):
        return info
    info.update({
        "branch": None if branch == "HEAD" else branch,
        "commit": commit or None,
        "tracked_dirty": bool(tracked),
        "source": "git",
    })
    return info


def install() -> None:
    """Install the small, explicit Recovery Lite compatibility layer."""

    from . import __version__ as package_version
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

    async def start_recovery_lite(self) -> None:
        """Start ComfyUI while preserving a real visible Windows console."""

        self.phase = "starting"
        existing = self._recorded_process()
        if existing is not None and existing.is_running():
            raise lifecycle_module.LifecycleError("已记录的 ComfyUI 进程仍在运行，请稍后再试")
        if not self.command or self.working_dir is None:
            raise lifecycle_module.LifecycleError("ComfyUI 启动命令不完整")
        executable = self._configured_executable()
        if not executable.is_file():
            raise lifecycle_module.LifecycleError("找不到已配置的 ComfyUI 启动程序")
        if not self.working_dir.is_dir():
            raise lifecycle_module.LifecycleError("找不到已配置的 ComfyUI 工作目录")

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        creationflags = 0
        stdout = None
        stderr = None
        stdin = _launch_stdin(lifecycle_module.os.name, self.visible_window)
        if lifecycle_module.os.name == "nt":
            creationflags = lifecycle_module.subprocess.CREATE_NEW_PROCESS_GROUP
            creationflags |= (
                lifecycle_module.subprocess.CREATE_NEW_CONSOLE
                if self.visible_window
                else lifecycle_module.subprocess.CREATE_NO_WINDOW
            )
        if lifecycle_module.os.name != "nt" or not self.visible_window:
            output = self.log_path.open("ab")
            stdout = output
            stderr = asyncio.subprocess.STDOUT
        else:
            output = None
        try:
            process = await asyncio.create_subprocess_exec(
                str(executable),
                *self.command[1:],
                cwd=self.working_dir,
                stdin=stdin,
                stdout=stdout,
                stderr=stderr,
                creationflags=creationflags,
            )
        except OSError as exc:
            raise lifecycle_module.LifecycleError("无法启动 ComfyUI，请检查本机控制日志") from exc
        finally:
            if output is not None:
                output.close()

        try:
            started = lifecycle_module.psutil.Process(process.pid)
            self._write_record(started)
        except (lifecycle_module.psutil.Error, OSError) as exc:
            process.terminate()
            raise lifecycle_module.LifecycleError("无法记录新启动的 ComfyUI 进程") from exc

        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            if process.returncode is not None:
                self._remove_record()
                raise lifecycle_module.LifecycleError("ComfyUI 启动后意外退出，请检查本机控制日志")
            if await self._is_online():
                return
            await asyncio.sleep(1)
        raise lifecycle_module.LifecycleError("等待 ComfyUI 启动超时；进程可能仍在加载，请稍后刷新")

    lifecycle_module.ComfyLifecycle.snapshot = snapshot_recovery_lite
    lifecycle_module.ComfyLifecycle.trigger = trigger_recovery_lite
    lifecycle_module.ComfyLifecycle._start = start_recovery_lite

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
        build_info = _build_info(package_version)

        async def about(_: web.Request) -> web.Response:
            return web.json_response(build_info)

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

        application.router.add_get("/api/about", about)
        application.middlewares.append(recovery_lite_asset)
        return application

    create_app_recovery_lite._recovery_lite_frontend = True  # type: ignore[attr-defined]
    app_module.create_app = create_app_recovery_lite
