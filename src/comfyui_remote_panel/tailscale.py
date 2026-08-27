from __future__ import annotations

from dataclasses import dataclass
import json
import shutil
import subprocess
from typing import Any


class TailscaleError(RuntimeError):
    pass


@dataclass(frozen=True)
class TailscaleStatus:
    executable: str | None
    installed: bool
    version: str | None = None
    backend_state: str | None = None
    login_name: str | None = None
    dns_name: str | None = None
    connected: bool = False

    @property
    def public_origin(self) -> str | None:
        if not self.dns_name:
            return None
        return f"https://{self.dns_name.rstrip('.')}"


def find_tailscale() -> str | None:
    return shutil.which("tailscale") or shutil.which("tailscale.exe")


def _run(executable: str, *args: str, timeout: float = 8.0) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            [executable, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise TailscaleError(f"Tailscale command failed: {exc}") from exc


def inspect_tailscale() -> TailscaleStatus:
    executable = find_tailscale()
    if not executable:
        return TailscaleStatus(executable=None, installed=False)

    version_result = _run(executable, "version")
    version = None
    if version_result.returncode == 0:
        version = (version_result.stdout or "").splitlines()[0].strip() or None

    status_result = _run(executable, "status", "--json")
    if status_result.returncode != 0:
        return TailscaleStatus(
            executable=executable,
            installed=True,
            version=version,
        )

    try:
        payload = json.loads(status_result.stdout or "{}")
    except json.JSONDecodeError:
        return TailscaleStatus(
            executable=executable,
            installed=True,
            version=version,
        )
    if not isinstance(payload, dict):
        payload = {}

    backend_state = payload.get("BackendState")
    self_info = payload.get("Self") if isinstance(payload.get("Self"), dict) else {}
    dns_name = self_info.get("DNSName")
    if not isinstance(dns_name, str) or not dns_name.strip():
        dns_name = None

    login_name = None
    user_id = self_info.get("UserID")
    users = payload.get("User")
    if isinstance(users, dict) and user_id is not None:
        user = users.get(str(user_id))
        if user is None:
            user = users.get(user_id)
        if isinstance(user, dict):
            candidate = user.get("LoginName")
            if isinstance(candidate, str) and candidate.strip():
                login_name = candidate.strip()

    connected = str(backend_state).lower() == "running"
    return TailscaleStatus(
        executable=executable,
        installed=True,
        version=version,
        backend_state=str(backend_state) if backend_state is not None else None,
        login_name=login_name,
        dns_name=dns_name,
        connected=connected,
    )


def _contains_target(value: Any, target: str) -> bool:
    if isinstance(value, str):
        normalized = value.replace("localhost", "127.0.0.1")
        return target in normalized or target.rsplit(":", 1)[-1] == normalized
    if isinstance(value, dict):
        return any(_contains_target(child, target) for child in value.values())
    if isinstance(value, list):
        return any(_contains_target(child, target) for child in value)
    return False


def serve_active(port: int = 8190) -> bool:
    executable = find_tailscale()
    if not executable:
        return False
    result = _run(executable, "serve", "status", "--json")
    if result.returncode != 0:
        return False
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return False
    return _contains_target(payload, f"127.0.0.1:{port}") or _contains_target(payload, str(port))


def enable_serve(port: int = 8190) -> str:
    executable = find_tailscale()
    if not executable:
        raise TailscaleError("Tailscale is not installed")
    result = _run(executable, "serve", "--bg", str(port), timeout=20)
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "unknown error").strip()
        raise TailscaleError(message)
    return (result.stdout or "").strip()
