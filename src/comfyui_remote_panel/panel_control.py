from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
from urllib.request import urlopen

import psutil

from .config import Config, load_config


class PanelControlError(RuntimeError):
    pass


@dataclass(frozen=True)
class PanelStatus:
    running: bool
    pid: int | None
    port: int
    health_ok: bool
    reason: str = ""


def _background_creationflags() -> int:
    if os.name != "nt":
        return 0
    # CREATE_NO_WINDOW is the important part here. DETACHED_PROCESS looks like a
    # natural fit for a background service, but Windows ignores CREATE_NO_WINDOW
    # when DETACHED_PROCESS is used, which can leave a persistent console window
    # behind on some systems. A new process group still keeps Ctrl+C from the
    # launching shell from being delivered to the panel process.
    return getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(
        subprocess, "CREATE_NO_WINDOW", 0
    )


class PanelController:
    def __init__(self, config_path: str | Path = "config.toml"):
        self.config_path = Path(config_path).expanduser().resolve()
        self.config: Config = load_config(self.config_path)
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        self.pid_path = self.config.data_dir / "panel.pid"
        self.runtime_path = self.config.data_dir / "panel-runtime.json"
        self.launch_log_path = self.config.data_dir / "panel-launch.log"

    def _read_runtime(self) -> dict:
        if not self.runtime_path.is_file():
            return {}
        try:
            payload = json.loads(self.runtime_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _write_runtime(self, pid: int) -> None:
        payload = {
            "pid": int(pid),
            "config": str(self.config_path),
            "port": self.config.port,
            "started_at": time.time(),
        }
        temporary = self.runtime_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.runtime_path)
        self.pid_path.write_text(str(pid), encoding="ascii")

    def _clear_runtime(self) -> None:
        for path in (self.runtime_path, self.pid_path):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass

    @staticmethod
    def _command_signature(process: psutil.Process) -> bool:
        try:
            cmdline = process.cmdline()
            executable = process.exe()
        except (psutil.Error, OSError):
            return False
        joined = " ".join(cmdline).lower()
        name = Path(executable).name.lower() if executable else ""
        panel_marker = "comfyui_remote_panel" in joined or "comfyui-remote-panel" in joined
        python_marker = name.startswith("python") or "comfyui-remote-panel" in name
        return panel_marker and python_marker

    def _listener_pid(self) -> int | None:
        try:
            connections = psutil.net_connections(kind="inet")
        except (psutil.Error, OSError):
            return None
        for connection in connections:
            if connection.status != psutil.CONN_LISTEN or not connection.laddr:
                continue
            if connection.laddr.port != self.config.port:
                continue
            host = connection.laddr.ip
            if host not in {self.config.host, "0.0.0.0", "::", "::1"}:
                continue
            return connection.pid
        return None

    def _health(self, timeout: float = 1.0) -> bool:
        try:
            with urlopen(f"http://127.0.0.1:{self.config.port}/healthz", timeout=timeout) as response:
                if response.status != 200:
                    return False
                payload = json.loads(response.read().decode("utf-8"))
                return isinstance(payload, dict) and payload.get("status") == "ok"
        except Exception:
            return False

    def status(self) -> PanelStatus:
        listener_pid = self._listener_pid()
        runtime = self._read_runtime()
        runtime_pid = runtime.get("pid")
        try:
            runtime_pid = int(runtime_pid) if runtime_pid is not None else None
        except (TypeError, ValueError):
            runtime_pid = None

        if listener_pid is None:
            if runtime_pid is not None and not psutil.pid_exists(runtime_pid):
                self._clear_runtime()
            return PanelStatus(False, None, self.config.port, False, "stopped")

        try:
            process = psutil.Process(listener_pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return PanelStatus(False, listener_pid, self.config.port, False, "port-occupied")

        if not self._command_signature(process):
            return PanelStatus(False, listener_pid, self.config.port, False, "port-occupied")

        health = self._health()
        if runtime_pid != listener_pid:
            # A valid Comfy Remote listener may have been started manually or by Task Scheduler.
            # Adopt it so subsequent status/stop calls have a consistent runtime record.
            try:
                self._write_runtime(listener_pid)
            except OSError:
                pass
        return PanelStatus(True, listener_pid, self.config.port, health, "running")

    def start(self) -> PanelStatus:
        current = self.status()
        if current.running:
            return current
        if current.reason == "port-occupied":
            raise PanelControlError(f"port {self.config.port} is already used by another process")

        command = [
            sys.executable,
            "-m",
            "comfyui_remote_panel",
            "--config",
            str(self.config_path),
        ]
        creationflags = _background_creationflags()
        kwargs: dict = {}
        if os.name != "nt":
            kwargs["start_new_session"] = True
        kwargs["close_fds"] = os.name != "nt"

        try:
            launch_log = self.launch_log_path.open("ab", buffering=0)
            try:
                process = subprocess.Popen(
                    command,
                    cwd=self.config_path.parent,
                    stdin=subprocess.DEVNULL,
                    stdout=launch_log,
                    stderr=subprocess.STDOUT,
                    creationflags=creationflags,
                    **kwargs,
                )
            finally:
                launch_log.close()
        except OSError as exc:
            raise PanelControlError(f"failed to start Comfy Remote: {exc}") from exc

        self._write_runtime(process.pid)
        for _ in range(40):
            if process.poll() is not None:
                break
            if self._health(timeout=0.5):
                return self.status()
            time.sleep(0.25)

        if process.poll() is None:
            try:
                process.terminate()
            except OSError:
                pass
        self._clear_runtime()
        raise PanelControlError(
            f"panel health check failed; see {self.launch_log_path}"
        )

    def stop(self) -> PanelStatus:
        current = self.status()
        if not current.running or current.pid is None:
            if current.reason == "port-occupied":
                raise PanelControlError(
                    f"refusing to stop unknown process on port {self.config.port}"
                )
            self._clear_runtime()
            return current

        try:
            process = psutil.Process(current.pid)
        except psutil.NoSuchProcess:
            self._clear_runtime()
            return PanelStatus(False, None, self.config.port, False, "stopped")
        if not self._command_signature(process):
            raise PanelControlError("refusing to stop a process that is not Comfy Remote")

        try:
            process.terminate()
            process.wait(timeout=10)
        except psutil.TimeoutExpired:
            process.kill()
            try:
                process.wait(timeout=5)
            except psutil.TimeoutExpired as exc:
                raise PanelControlError("panel process did not stop") from exc
        except (psutil.AccessDenied, OSError) as exc:
            raise PanelControlError(f"failed to stop panel: {exc}") from exc
        finally:
            self._clear_runtime()

        for _ in range(20):
            status = self.status()
            if not status.running:
                return status
            time.sleep(0.1)
        return self.status()

    def restart(self) -> PanelStatus:
        current = self.status()
        if current.running:
            self.stop()
        elif current.reason == "port-occupied":
            raise PanelControlError(
                f"cannot restart because port {self.config.port} is used by another process"
            )
        return self.start()


def port_available(host: str = "127.0.0.1", port: int = 8190) -> bool:
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    sock = socket.socket(family, socket.SOCK_STREAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        sock.close()
