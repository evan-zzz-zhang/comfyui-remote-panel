from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import time
from pathlib import Path
from urllib.parse import urlparse

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
        parsed_base_url = urlparse(config.comfyui_base_url)
        self.comfyui_port = parsed_base_url.port or (443 if parsed_base_url.scheme == "https" else 80)
        self.record_path = config.data_dir / "comfyui-process.json"
        self.log_path = config.data_dir / "comfyui-control.log"
        self.operation: str | None = None
        self.phase: str | None = None
        self.last_error: str | None = None
        self.last_error_action: str | None = None
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    def snapshot(
        self,
        online: bool,
        *,
        unresponsive: bool = False,
        managed_process_alive: bool = False,
        verified_process_alive: bool = False,
        last_success_at: float | None = None,
    ) -> dict:
        busy = self.operation is not None
        process_alive = managed_process_alive or verified_process_alive
        if self.phase == "starting":
            state, summary = "starting", "正在启动并等待 ComfyUI 节点加载"
        elif self.phase == "stopping":
            state, summary = "stopping", "正在关闭 ComfyUI 并等待端口释放"
        elif online:
            state, summary = "online", "ComfyUI 在线"
        elif self.last_error and self.last_error_action in {"start", "restart", "force_restart"}:
            state, summary = "start_failed", self.last_error
        elif unresponsive or process_alive:
            state, summary = "unresponsive", "ComfyUI 进程仍在运行，但 API 无法正常响应"
        else:
            state, summary = "offline", "ComfyUI 离线"
        return {
            "enabled": self.enabled,
            "operation": self.operation,
            "phase": self.phase,
            "state": state,
            "summary": summary,
            "last_success_at": last_success_at,
            "last_error": self.last_error,
            "managed_process_alive": managed_process_alive,
            "verified_process_alive": verified_process_alive,
            "can_start": self.enabled and not online and not process_alive and not busy,
            "can_stop": self.enabled and online and not busy,
            "can_restart": self.enabled and online and not busy,
            "can_force_stop": self.enabled and process_alive and not busy,
            "can_force_restart": self.enabled and managed_process_alive and not busy,
        }

    async def trigger(self, action: str) -> dict:
        if not self.enabled:
            raise LifecycleError("ComfyUI 远程控制尚未配置")
        if action not in {"start", "stop", "restart", "force_stop", "force_restart"}:
            raise LifecycleError("不支持的控制操作")
        async with self._lock:
            if self._task and not self._task.done():
                raise LifecycleError("已有 ComfyUI 控制操作正在执行")
            online = await self._is_online()
            managed_process_alive = await asyncio.to_thread(self.managed_process_alive)
            verified_process_alive = managed_process_alive
            if not verified_process_alive:
                verified_process_alive = await asyncio.to_thread(
                    lambda: self._verified_listener_process() is not None
                )
            if action == "start":
                if online:
                    raise LifecycleError("ComfyUI 已经在线")
                if verified_process_alive:
                    raise LifecycleError("ComfyUI 进程仍在运行但无响应，请先强制关闭")
            if action in {"stop", "restart"} and not online:
                raise LifecycleError("ComfyUI 当前不在线")
            if action == "force_stop" and not verified_process_alive:
                raise LifecycleError("无法安全确认 ComfyUI 主进程；未执行强制关闭")
            if action == "force_restart" and not managed_process_alive:
                raise LifecycleError("无法通过进程记录安全确认 ComfyUI 主进程；未执行强制重启")
            self.operation = action
            self.phase = "starting" if action == "start" else "stopping"
            self.last_error = None
            self.last_error_action = None
            self._task = asyncio.create_task(self._run(action))
        return self.snapshot(
            online,
            unresponsive=not online and verified_process_alive,
            managed_process_alive=managed_process_alive,
            verified_process_alive=verified_process_alive,
        )

    async def _run(self, action: str) -> None:
        try:
            if action == "start":
                await self._start()
            elif action == "stop":
                await self._stop()
            elif action == "restart":
                await self._stop()
                await self._start()
            elif action == "force_stop":
                await self._force_stop()
            else:
                await self._force_stop()
                await self._start()
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.last_error = str(exc)[:300] or "ComfyUI 控制操作失败"
            self.last_error_action = action
            log.exception("ComfyUI %s operation failed", action)
        finally:
            self.operation = None
            self.phase = None

    async def _start(self) -> None:
        self.phase = "starting"
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
        self.phase = "stopping"
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

    async def _force_stop(self) -> None:
        self.phase = "stopping"
        process = await asyncio.to_thread(self._recorded_process)
        discovered = False
        if process is None:
            process = await asyncio.to_thread(self._verified_listener_process)
            discovered = process is not None
        if process is None:
            raise LifecycleError(
                "无法安全确认正在监听当前端口的 ComfyUI 主进程；未执行强制关闭"
            )
        if discovered:
            log.warning(
                "Using verified listener fallback for ComfyUI force stop: pid=%s port=%s",
                process.pid,
                self.comfyui_port,
            )

        await asyncio.to_thread(self._force_stop_recorded_tree, process)
        self._remove_record()
        deadline = time.monotonic() + min(self.shutdown_timeout, 10)
        while time.monotonic() < deadline:
            if not await self._is_online():
                return
            await asyncio.sleep(.5)
        raise LifecycleError("已结束确认过的 ComfyUI 进程树，但服务端口仍然在线；拒绝继续启动")

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

    def _force_stop_recorded_tree(self, process: psutil.Process) -> None:
        """Terminate only the verified ComfyUI process and descendants captured from it."""
        descendants = self._record_descendants(process)
        try:
            main_create_time = process.create_time()
        except psutil.Error as exc:
            raise LifecycleError("无法重新确认 ComfyUI 主进程身份；未执行强制关闭") from exc

        records = descendants + [(process, main_create_time)]
        expected = {item.pid: create_time for item, create_time in records}
        targets = [item for item, create_time in records if self._same_process_instance(item, create_time)]
        if process not in targets:
            raise LifecycleError("ComfyUI 主进程身份已变化；未执行强制关闭")

        log.warning(
            "Force stopping verified ComfyUI process tree: main_pid=%s descendants=%s",
            process.pid,
            [item.pid for item in targets if item.pid != process.pid],
        )
        try:
            for item in targets:
                item.terminate()
            _, alive = psutil.wait_procs(targets, timeout=min(self.shutdown_timeout, 5))
            still_alive = [
                item for item in alive
                if self._same_process_instance(item, expected.get(item.pid))
            ]
            for item in still_alive:
                item.kill()
            if still_alive:
                _, alive_after_kill = psutil.wait_procs(still_alive, timeout=5)
                alive_after_kill = [
                    item for item in alive_after_kill
                    if self._same_process_instance(item, expected.get(item.pid))
                ]
                if alive_after_kill:
                    raise LifecycleError("已确认的 ComfyUI 进程树仍有进程无法停止")
        except psutil.AccessDenied as exc:
            raise LifecycleError("没有权限强制关闭已确认的 ComfyUI 进程树") from exc
        except psutil.Error as exc:
            raise LifecycleError("强制关闭 ComfyUI 进程树失败") from exc
        log.info("Forced ComfyUI process tree stopped successfully: main_pid=%s", process.pid)

    async def _is_online(self) -> bool:
        try:
            await self.comfy.system_stats()
            return True
        except ComfyError:
            return False

    def managed_process_alive(self) -> bool:
        process = self._recorded_process()
        if process is None:
            return False
        try:
            return process.is_running()
        except psutil.Error:
            return False

    def verified_process_alive(self) -> bool:
        process = self._recorded_process()
        if process is None:
            process = self._verified_listener_process()
        if process is None:
            return False
        try:
            return process.is_running()
        except psutil.Error:
            return False

    def _verified_listener_process(self) -> psutil.Process | None:
        """Find one ComfyUI listener that matches the configured executable and args."""
        try:
            connections = psutil.net_connections(kind="tcp")
        except (psutil.AccessDenied, psutil.Error, OSError):
            return None

        candidate_pids: set[int] = set()
        for connection in connections:
            if connection.status != psutil.CONN_LISTEN or connection.pid is None:
                continue
            local = connection.laddr
            try:
                port = local.port
            except AttributeError:
                try:
                    port = local[1]
                except (IndexError, TypeError):
                    continue
            if port == self.comfyui_port:
                candidate_pids.add(int(connection.pid))

        matches: list[psutil.Process] = []
        for pid in candidate_pids:
            try:
                process = psutil.Process(pid)
                if self._matches(process):
                    matches.append(process)
            except psutil.Error:
                continue
        return matches[0] if len(matches) == 1 else None

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

    @staticmethod
    def _same_process_instance(process: psutil.Process, create_time: float | None) -> bool:
        if create_time is None:
            return False
        try:
            return process.is_running() and process.create_time() == create_time
        except psutil.NoSuchProcess:
            return False
        except psutil.Error as exc:
            raise LifecycleError("无法重新确认 ComfyUI 进程树身份") from exc

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