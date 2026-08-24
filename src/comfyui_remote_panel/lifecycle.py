from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
from pathlib import Path

import psutil

from .comfy import ComfyClient, ComfyError
from .config import Config


log = logging.getLogger(__name__)


class LifecycleError(RuntimeError):
    pass


class ComfyLifecycle:
    """Start and stop only the locally configured ComfyUI process."""

    def __init__(self, config: Config, comfy: ComfyClient):
        self.enabled = config.comfyui_control_enabled
        self.command = config.comfyui_start_command
        self.working_dir = config.comfyui_working_dir
        self.visible_window = config.comfyui_visible_window
        self.startup_timeout = config.comfyui_startup_timeout
        self.shutdown_timeout = config.comfyui_shutdown_timeout
        self.comfy = comfy
        self.record_path = config.data_dir / "comfyui-process.json"
        self.log_path = config.data_dir / "comfyui-control.log"
        self.operation: str | None = None
        self.last_error: str | None = None
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    def snapshot(self, online: bool) -> dict:
        busy = self.operation is not None
        return {
            "enabled": self.enabled,
            "operation": self.operation,
            "last_error": self.last_error,
            "can_start": self.enabled and not online and not busy,
            "can_stop": self.enabled and online and not busy,
            "can_restart": self.enabled and online and not busy,
        }

    async def trigger(self, action: str) -> dict:
        if not self.enabled:
            raise LifecycleError("ComfyUI 远程控制尚未配置")
        if action not in {"start", "stop", "restart"}:
            raise LifecycleError("不支持的控制操作")
        async with self._lock:
            if self._task and not self._task.done():
                raise LifecycleError("已有 ComfyUI 控制操作正在执行")
            online = await self._is_online()
            if action == "start" and online:
                raise LifecycleError("ComfyUI 已经在线")
            if action in {"stop", "restart"} and not online:
                raise LifecycleError("ComfyUI 当前不在线")
            self.operation = action
            self.last_error = None
            self._task = asyncio.create_task(self._run(action))
        return self.snapshot(online)

    async def _run(self, action: str) -> None:
        try:
            if action == "start":
                await self._start()
            elif action == "stop":
                await self._stop()
            else:
                await self._stop()
                await self._start()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.last_error = str(exc)[:300] or "ComfyUI 控制操作失败"
            log.exception("ComfyUI %s operation failed", action)
        finally:
            self.operation = None

    async def _start(self) -> None:
        existing = self._recorded_process()
        if existing is not None and existing.is_running():
            raise LifecycleError("已记录的 ComfyUI 进程仍在运行，请稍后再试")
        if not self.command or self.working_dir is None:
            raise LifecycleError("ComfyUI 启动命令不完整")
        executable = self._configured_executable()
        if not executable.is_file():
            raise LifecycleError("找不到已配置的 ComfyUI 启动程序")
        if not self.working_dir.is_dir():
            raise LifecycleError("找不到已配置的 ComfyUI 工作目录")

        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        creationflags = 0
        stdout = None
        stderr = None
        if os.name == "nt":
            creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            creationflags |= subprocess.CREATE_NEW_CONSOLE if self.visible_window else subprocess.CREATE_NO_WINDOW
        if os.name != "nt" or not self.visible_window:
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
                stdin=asyncio.subprocess.DEVNULL,
                stdout=stdout,
                stderr=stderr,
                creationflags=creationflags,
            )
        except OSError as exc:
            raise LifecycleError("无法启动 ComfyUI，请检查本机控制日志") from exc
        finally:
            if output is not None:
                output.close()

        try:
            started = psutil.Process(process.pid)
            self._write_record(started)
        except (psutil.Error, OSError) as exc:
            process.terminate()
            raise LifecycleError("无法记录新启动的 ComfyUI 进程") from exc

        deadline = time.monotonic() + self.startup_timeout
        while time.monotonic() < deadline:
            if process.returncode is not None:
                self._remove_record()
                raise LifecycleError("ComfyUI 启动后意外退出，请检查本机控制日志")
            if await self._is_online():
                return
            await asyncio.sleep(1)
        raise LifecycleError("等待 ComfyUI 启动超时；进程可能仍在加载，请稍后刷新")

    async def _stop(self) -> None:
        process = await asyncio.to_thread(self._recorded_process)
        if process is None:
            raise LifecycleError("无法通过进程记录安全确认 ComfyUI 主进程；未执行关闭")

        surviving_pids = await asyncio.to_thread(self._stop_recorded_process, process)
        self._remove_record()
        if surviving_pids:
            log.warning(
                "ComfyUI main process stopped but descendant processes remain; "
                "refusing to terminate them automatically: pids=%s",
                surviving_pids,
            )

        deadline = time.monotonic() + min(self.shutdown_timeout, 10)
        while time.monotonic() < deadline:
            if not await self._is_online():
                return
            await asyncio.sleep(.5)
        raise LifecycleError("ComfyUI 进程已停止，但服务端口仍然在线")

    def _stop_recorded_process(self, process: psutil.Process) -> list[int]:
        """Perform blocking psutil work off the aiohttp event-loop thread."""
        descendants = self._record_descendants(process)
        try:
            process.terminate()
            _, alive = psutil.wait_procs([process], timeout=self.shutdown_timeout)
            if alive:
                process.kill()
                _, alive = psutil.wait_procs(alive, timeout=5)
            if alive:
                raise LifecycleError("已确认的 ComfyUI 主进程未能停止；未处理任何子进程")
        except (psutil.AccessDenied, psutil.Error) as exc:
            raise LifecycleError("没有权限关闭已确认的 ComfyUI 进程") from exc
        return self._surviving_descendant_pids(descendants)

    async def _is_online(self) -> bool:
        try:
            await self.comfy.system_stats()
            return True
        except ComfyError:
            return False

    def _configured_executable(self) -> Path:
        executable = Path(self.command[0]).expanduser()
        if not executable.is_absolute():
            executable = self.working_dir / executable  # type: ignore[operator]
        return executable.resolve()

    def _write_record(self, process: psutil.Process) -> None:
        payload = {
            "pid": process.pid,
            "create_time": process.create_time(),
            "executable": process.exe(),
            "command_line": process.cmdline(),
        }
        temporary = self.record_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8")
        temporary.replace(self.record_path)

    def _remove_record(self) -> None:
        try:
            self.record_path.unlink(missing_ok=True)
        except OSError:
            pass

    def _recorded_process(self) -> psutil.Process | None:
        try:
            payload = json.loads(self.record_path.read_text(encoding="utf-8"))
            process = psutil.Process(int(payload["pid"]))
            if process.create_time() != float(payload["create_time"]):
                return None
            if not self._matches_record(process, payload) or not self._matches(process):
                return None
            return process
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError, psutil.Error):
            return None

    def _matches_record(self, process: psutil.Process, payload: dict) -> bool:
        try:
            recorded_executable = Path(payload["executable"]).resolve()
            actual_executable = Path(process.exe()).resolve()
            if os.path.normcase(str(actual_executable)) != os.path.normcase(str(recorded_executable)):
                return False
            recorded_command_line = payload["command_line"]
            return (
                isinstance(recorded_command_line, list)
                and all(isinstance(value, str) for value in recorded_command_line)
                and process.cmdline() == recorded_command_line
            )
        except (OSError, TypeError, psutil.Error):
            return False

    def _record_descendants(self, process: psutil.Process) -> list[tuple[psutil.Process, float]]:
        try:
            return [(child, child.create_time()) for child in process.children(recursive=True)]
        except psutil.Error as exc:
            log.warning("Could not inspect ComfyUI descendants before stopping the main process: %s", exc)
            return []

    def _surviving_descendant_pids(
        self, descendants: list[tuple[psutil.Process, float]]
    ) -> list[int]:
        surviving: list[int] = []
        for child, create_time in descendants:
            try:
                if child.is_running() and child.create_time() == create_time:
                    surviving.append(child.pid)
            except psutil.Error:
                continue
        return surviving

    def _matches(self, process: psutil.Process) -> bool:
        try:
            actual = Path(process.exe()).resolve()
            expected = self._configured_executable()
            if os.path.normcase(str(actual)) != os.path.normcase(str(expected)):
                return False
            command_line = [value.replace("\\", "/") for value in process.cmdline()[1:]]
            expected_args = [value.replace("\\", "/") for value in self.command[1:]]
            return all(value in command_line for value in expected_args)
        except (OSError, psutil.Error):
            return False

    async def close(self) -> None:
        if self._task and not self._task.done():
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
