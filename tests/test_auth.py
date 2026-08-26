from types import SimpleNamespace
from unittest.mock import Mock

from comfyui_remote_panel.auth import (
    AuthenticatedPrincipal,
    LocalAuthProvider,
    TailscaleAuthProvider,
    create_auth_provider,
)


def test_tailscale_provider_maps_only_allowed_login_to_principal():
    provider = TailscaleAuthProvider(("owner@example.com",), "https://device.example.ts.net")
    request = Mock(headers={"Tailscale-User-Login": "owner@example.com"})
    assert provider.authenticate(request) == AuthenticatedPrincipal(
        "owner@example.com", "owner@example.com", "tailscale"
    )
    request.headers = {"Tailscale-User-Login": "other@example.com"}
    assert provider.authenticate(request) is None
    assert provider.allows_origin("https://device.example.ts.net/") is True
    assert provider.allows_origin("https://other.example.ts.net") is False


def test_local_provider_requires_loopback_client_and_exact_local_origin():
    provider = LocalAuthProvider(8190)
    assert provider.authenticate(Mock(remote="127.0.0.1")).provider == "local"
    assert provider.authenticate(Mock(remote="::1")).provider == "local"
    assert provider.authenticate(Mock(remote="192.168.1.10")) is None
    assert provider.allows_origin("http://localhost:8190") is True
    assert provider.allows_origin("http://localhost:9000") is False


def test_provider_factory_does_not_depend_on_business_services():
    tailscale = create_auth_provider(SimpleNamespace(
        auth_provider="tailscale",
        allowed_logins=("owner@example.com",),
        public_origin="https://device.example.ts.net",
        port=8190,
    ))
    local = create_auth_provider(SimpleNamespace(
        auth_provider="local", allowed_logins=(), public_origin="", port=8190,
    ))
    assert isinstance(tailscale, TailscaleAuthProvider)
    assert isinstance(local, LocalAuthProvider)
