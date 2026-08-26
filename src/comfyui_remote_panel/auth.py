from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from typing import Protocol

from aiohttp import web

from .config import Config


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    subject: str
    display_name: str
    provider: str


class AuthProvider(Protocol):
    def authenticate(self, request: web.Request) -> AuthenticatedPrincipal | None: ...

    def allows_origin(self, origin: str) -> bool: ...


class TailscaleAuthProvider:
    def __init__(self, allowed_logins: tuple[str, ...], public_origin: str):
        self.allowed_logins = frozenset(allowed_logins)
        self.public_origin = public_origin.rstrip("/")

    def authenticate(self, request: web.Request) -> AuthenticatedPrincipal | None:
        login = request.headers.get("Tailscale-User-Login")
        if login not in self.allowed_logins:
            return None
        return AuthenticatedPrincipal(login, login, "tailscale")

    def allows_origin(self, origin: str) -> bool:
        return origin.rstrip("/") == self.public_origin


class LocalAuthProvider:
    def __init__(self, port: int):
        self.allowed_origins = {
            f"http://127.0.0.1:{port}",
            f"http://localhost:{port}",
        }

    def authenticate(self, request: web.Request) -> AuthenticatedPrincipal | None:
        try:
            address = ipaddress.ip_address(request.remote or "")
        except ValueError:
            return None
        if not address.is_loopback:
            return None
        return AuthenticatedPrincipal("local", "本机用户", "local")

    def allows_origin(self, origin: str) -> bool:
        return origin.rstrip("/") in self.allowed_origins


def create_auth_provider(config: Config) -> AuthProvider:
    if config.auth_provider == "tailscale":
        return TailscaleAuthProvider(config.allowed_logins, config.public_origin)
    if config.auth_provider == "local":
        return LocalAuthProvider(config.port)
    raise ValueError(f"unsupported auth provider: {config.auth_provider}")
