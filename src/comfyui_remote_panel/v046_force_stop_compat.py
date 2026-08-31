from __future__ import annotations

import os
from pathlib import Path

import psutil


def _normalized_path(value: str | os.PathLike[str], base: Path | None = None) -> str:
    path = Path(value).expanduser()
    if not path.is_absolute() and base is not None:
        path = base / path
    return os.path.normcase(os.path.normpath(str(path.resolve())))


def _stable_launch_identity(manager, process: psutil.Process) -> bool:
    """Match the configured ComfyUI executable, cwd and Python entrypoint.

    Force-stop discovery intentionally ignores optional launch flags such as
    --use-sage-attention. Those flags may be edited while an older ComfyUI
    process is still alive, which must not make that listener impossible to
    recover remotely.
    """

    if not manager.command or manager.working_dir is None:
        return False

    script_arg = next(
        (
            value
            for value in manager.command[1:]
            if isinstance(value, str) and value.replace("\\", "/").lower().endswith(".py")
        ),
        None,
    )
    if script_arg is None:
        return False

    try:
        expected_executable = _normalized_path(manager._configured_executable())
        actual_executable = _normalized_path(process.exe())
        if actual_executable != expected_executable:
            return False

        expected_cwd = _normalized_path(manager.working_dir)
        actual_cwd_path = Path(process.cwd()).resolve()
        actual_cwd = _normalized_path(actual_cwd_path)
        if actual_cwd != expected_cwd:
            return False

        expected_script = _normalized_path(script_arg, Path(manager.working_dir))
        command_line = process.cmdline()[1:]
        for value in command_line:
            if not isinstance(value, str) or not value.replace("\\", "/").lower().endswith(".py"):
                continue
            if _normalized_path(value, actual_cwd_path) == expected_script:
                return True
        return False
    except (OSError, TypeError, psutil.Error):
        return False


def install() -> None:
    from . import lifecycle as lifecycle_module

    current = lifecycle_module.ComfyLifecycle._verified_listener_process
    if getattr(current, "_v046_relaxed_launch_flags", False):
        return

    def verified_listener_process_v046(self):
        """Find one safe ComfyUI listener even if optional launch flags changed."""
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
                if self._matches(process) or _stable_launch_identity(self, process):
                    matches.append(process)
            except psutil.Error:
                continue
        return matches[0] if len(matches) == 1 else None

    verified_listener_process_v046._v046_relaxed_launch_flags = True  # type: ignore[attr-defined]
    lifecycle_module.ComfyLifecycle._verified_listener_process = verified_listener_process_v046
