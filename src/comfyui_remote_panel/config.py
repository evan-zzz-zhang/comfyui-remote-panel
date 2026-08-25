from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit
import tomllib


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Config:
    host: str
    port: int
    public_origin: str
    allowed_logins: tuple[str, ...]
    comfyui_base_url: str
    comfyui_input_dir: Path
    comfyui_output_dir: Path
    minimum_comfyui_version: str
    data_dir: Path
    workflow_dir: Path
    monitoring_interval: float
    nvidia_smi_timeout: float
    comfyui_control_enabled: bool = False
    comfyui_start_command: tuple[str, ...] = ()
    comfyui_working_dir: Path | None = None
    comfyui_visible_window: bool = False
    comfyui_startup_timeout: float = 120.0
    comfyui_shutdown_timeout: float = 30.0
    minimum_free_bytes: int = 512 * 1024 * 1024
    output_reserve_bytes: int = 1024 * 1024 * 1024
    max_tracked_bytes: int | None = None
    auth_provider: str = "tailscale"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "panel.db"

    @property
    def dedicated_input_dir(self) -> Path:
        return self.comfyui_input_dir / "h3_remote"

    @property
    def dedicated_output_dir(self) -> Path:
        return self.comfyui_output_dir / "h3_remote"


def _table(data: dict, name: str) -> dict:
    value = data.get(name)
    if not isinstance(value, dict):
        raise ConfigError(f"missing [{name}] section")
    return value


def _resolve(base: Path, value: object, key: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{key} must be a non-empty path")
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def load_config(path: str | Path) -> Config:
    config_path = Path(path).expanduser().resolve()
    with config_path.open("rb") as handle:
        raw = tomllib.load(handle)
    base = config_path.parent
    server = _table(raw, "server")
    auth = _table(raw, "auth")
    comfyui = _table(raw, "comfyui")
    storage = _table(raw, "storage")
    monitoring = _table(raw, "monitoring")
    control = comfyui.get("control", {})
    if not isinstance(control, dict):
        raise ConfigError("comfyui.control must be a table")

    host = server.get("host")
    if host != "127.0.0.1":
        raise ConfigError("server.host must be exactly 127.0.0.1")
    port = server.get("port")
    if port != 8190:
        raise ConfigError("server.port must be exactly 8190")
    auth_provider = auth.get("provider", "tailscale")
    if auth_provider not in {"tailscale", "local"}:
        raise ConfigError("auth.provider must be tailscale or local")

    public_origin = server.get("public_origin")
    if auth_provider == "local" and public_origin is None:
        public_origin = f"http://127.0.0.1:{port}"
    parsed_origin = urlsplit(public_origin) if isinstance(public_origin, str) else None
    if (
        not parsed_origin
        or parsed_origin.scheme != ("https" if auth_provider == "tailscale" else "http")
        or not parsed_origin.hostname
        or parsed_origin.username is not None
        or parsed_origin.password is not None
        or parsed_origin.path not in ("", "/")
        or parsed_origin.query
        or parsed_origin.fragment
        or auth_provider == "local" and (
            parsed_origin.hostname not in {"127.0.0.1", "localhost"}
            or parsed_origin.port != port
        )
    ):
        raise ConfigError(
            "server.public_origin must be an HTTPS origin without a path"
            if auth_provider == "tailscale"
            else "server.public_origin must be a local HTTP origin without a path"
        )
    public_origin = public_origin.rstrip("/")

    logins = auth.get("allowed_logins", [])
    if not isinstance(logins, list) or not all(isinstance(v, str) and v.strip() == v and v for v in logins):
        raise ConfigError("auth.allowed_logins must be an array of non-empty logins")
    if auth_provider == "tailscale" and not logins:
        raise ConfigError("auth.allowed_logins must contain at least one login for tailscale")
    if len(set(logins)) != len(logins):
        raise ConfigError("auth.allowed_logins must not contain duplicates")

    base_url = comfyui.get("base_url")
    parsed_comfy = urlsplit(base_url) if isinstance(base_url, str) else None
    if not parsed_comfy or parsed_comfy.scheme != "http" or parsed_comfy.hostname not in {"127.0.0.1", "localhost"}:
        raise ConfigError("comfyui.base_url must be a local HTTP URL")

    interval = monitoring.get("interval_seconds", 3)
    timeout = monitoring.get("nvidia_smi_timeout_seconds", 2)
    if not isinstance(interval, (int, float)) or interval < 1:
        raise ConfigError("monitoring.interval_seconds must be at least 1")
    if not isinstance(timeout, (int, float)) or timeout <= 0:
        raise ConfigError("monitoring.nvidia_smi_timeout_seconds must be positive")

    control_enabled = control.get("enabled", False)
    if not isinstance(control_enabled, bool):
        raise ConfigError("comfyui.control.enabled must be true or false")
    start_command = control.get("start_command", [])
    if not isinstance(start_command, list) or not all(isinstance(v, str) and v.strip() for v in start_command):
        raise ConfigError("comfyui.control.start_command must be an array of non-empty strings")
    if control_enabled and not start_command:
        raise ConfigError("comfyui.control.start_command is required when control is enabled")
    working_dir_value = control.get("working_dir")
    working_dir = None
    if working_dir_value is not None:
        working_dir = _resolve(base, working_dir_value, "comfyui.control.working_dir")
    elif control_enabled:
        raise ConfigError("comfyui.control.working_dir is required when control is enabled")
    visible_window = control.get("visible_window", False)
    if not isinstance(visible_window, bool):
        raise ConfigError("comfyui.control.visible_window must be true or false")
    startup_timeout = control.get("startup_timeout_seconds", 120)
    shutdown_timeout = control.get("shutdown_timeout_seconds", 30)
    if not isinstance(startup_timeout, (int, float)) or startup_timeout <= 0:
        raise ConfigError("comfyui.control.startup_timeout_seconds must be positive")
    if not isinstance(shutdown_timeout, (int, float)) or shutdown_timeout <= 0:
        raise ConfigError("comfyui.control.shutdown_timeout_seconds must be positive")

    minimum_free_bytes = storage.get("minimum_free_bytes", 512 * 1024 * 1024)
    output_reserve_bytes = storage.get("output_reserve_bytes", 1024 * 1024 * 1024)
    max_tracked_bytes = storage.get("max_tracked_bytes")
    if not isinstance(minimum_free_bytes, int) or isinstance(minimum_free_bytes, bool) or minimum_free_bytes < 0:
        raise ConfigError("storage.minimum_free_bytes must be a non-negative integer")
    if not isinstance(output_reserve_bytes, int) or isinstance(output_reserve_bytes, bool) or output_reserve_bytes < 0:
        raise ConfigError("storage.output_reserve_bytes must be a non-negative integer")
    if max_tracked_bytes is not None and (
        not isinstance(max_tracked_bytes, int) or isinstance(max_tracked_bytes, bool) or max_tracked_bytes <= 0
    ):
        raise ConfigError("storage.max_tracked_bytes must be a positive integer")

    return Config(
        host=host,
        port=port,
        public_origin=public_origin,
        allowed_logins=tuple(logins),
        comfyui_base_url=base_url.rstrip("/"),
        comfyui_input_dir=_resolve(base, comfyui.get("input_dir"), "comfyui.input_dir"),
        comfyui_output_dir=_resolve(base, comfyui.get("output_dir"), "comfyui.output_dir"),
        minimum_comfyui_version=str(comfyui.get("minimum_version", "0.26.0")),
        data_dir=_resolve(base, storage.get("data_dir", "./data"), "storage.data_dir"),
        workflow_dir=_resolve(base, storage.get("workflow_dir", "./workflows"), "storage.workflow_dir"),
        monitoring_interval=float(interval),
        nvidia_smi_timeout=float(timeout),
        comfyui_control_enabled=control_enabled,
        comfyui_start_command=tuple(start_command),
        comfyui_working_dir=working_dir,
        comfyui_visible_window=visible_window,
        comfyui_startup_timeout=float(startup_timeout),
        comfyui_shutdown_timeout=float(shutdown_timeout),
        minimum_free_bytes=minimum_free_bytes,
        output_reserve_bytes=output_reserve_bytes,
        max_tracked_bytes=max_tracked_bytes,
        auth_provider=auth_provider,
    )
