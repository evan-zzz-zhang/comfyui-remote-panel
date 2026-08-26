from __future__ import annotations

import asyncio
from dataclasses import dataclass
import os
from pathlib import Path
import re
import sys
import tempfile
from typing import Iterable

from . import __version__
from .comfy import ComfyClient, ComfyError
from .config import Config, ConfigError, load_config
from .panel_control import PanelController, PanelControlError, port_available
from .preset import BUILTIN_WORKFLOW_DIR, Preset, PresetError, load_presets
from .tailscale import TailscaleError, inspect_tailscale, serve_active


PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"


@dataclass(frozen=True)
class DoctorCheck:
    section: str
    name: str
    status: str
    detail: str


def _builtin(preset: Preset) -> bool:
    try:
        preset.directory.resolve().relative_to(BUILTIN_WORKFLOW_DIR.resolve())
        return True
    except ValueError:
        return False


def _path_writable(path: Path) -> bool:
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix=".comfy-remote-doctor-", delete=True):
            return True
    except OSError:
        return False


def _path_readable(path: Path) -> bool:
    try:
        return path.is_dir() and os.access(path, os.R_OK)
    except OSError:
        return False


async def _validate_workflows(config: Config) -> tuple[dict[str, list[str]], dict]:
    presets = load_presets(config.workflow_dir)
    client = ComfyClient(config.comfyui_base_url, config.minimum_comfyui_version, "doctor")
    await client.start()
    try:
        stats = await client.system_stats()
        diagnostics = await client.validate_presets(list(presets.values()), stats)
        return diagnostics, stats
    finally:
        await client.close()


def _redact_email(match: re.Match[str]) -> str:
    local, domain = match.group(1), match.group(2)
    return f"{local[:1]}***@{domain}"


def redact_text(value: str) -> str:
    text = str(value)
    home = str(Path.home())
    if home and home not in {".", os.path.sep}:
        text = re.sub(re.escape(home), "<USER_PATH>", text, flags=re.IGNORECASE)

    text = re.sub(r"(?i)\b[A-Z]:\\Users\\[^\\/\r\n]+", "<USER_PATH>", text)
    text = re.sub(r"(?i)\b/Users/[^/\r\n]+", "<USER_PATH>", text)
    text = re.sub(r"(?i)\b/home/[^/\r\n]+", "<USER_PATH>", text)
    text = re.sub(
        r"\b([A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+)@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b",
        _redact_email,
        text,
    )
    text = re.sub(
        r"(?i)(\b(?:token|secret|cookie|api[_-]?key|authorization)\b\s*[:=]\s*)[^\s,;]+",
        r"\1<REDACTED>",
        text,
    )
    text = re.sub(
        r"(?i)\b[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.ts\.net\b",
        "<TAILSCALE_HOST>.ts.net",
        text,
    )
    return text


def _collect(config_path: str | Path) -> list[DoctorCheck]:
    path = Path(config_path).expanduser().resolve()
    checks: list[DoctorCheck] = []
    version_text = ".".join(str(part) for part in sys.version_info[:3])
    checks.append(DoctorCheck("Core", "Python", PASS if sys.version_info >= (3, 11) else FAIL, version_text))
    if not path.is_file():
        checks.append(DoctorCheck("Core", "config.toml", FAIL, f"not found: {path}"))
        return checks

    try:
        config = load_config(path)
    except (OSError, ConfigError) as exc:
        checks.append(DoctorCheck("Core", "config.toml", FAIL, str(exc)))
        return checks

    checks.append(DoctorCheck("Core", "config.toml", PASS, str(path)))
    data_ok = _path_writable(config.data_dir)
    checks.append(
        DoctorCheck(
            "Core",
            "data directory",
            PASS if data_ok else FAIL,
            f"{config.data_dir} ({'writable' if data_ok else 'not writable'})",
        )
    )

    try:
        panel = PanelController(path).status()
        if panel.running:
            status = PASS if panel.health_ok else FAIL
            detail = f"running pid={panel.pid} port={config.port}; health={'ok' if panel.health_ok else 'failed'}"
        elif panel.reason == "port-occupied":
            status = FAIL
            detail = f"port {config.port} is occupied by another process"
        else:
            status = PASS if port_available(config.host, config.port) else FAIL
            detail = f"port {config.port} {'available' if status == PASS else 'unavailable'}"
        checks.append(DoctorCheck("Core", "Panel", status, detail))
    except (PanelControlError, OSError) as exc:
        checks.append(DoctorCheck("Core", "Panel", WARN, str(exc)))

    comfy_stats: dict = {}
    workflow_diagnostics: dict[str, list[str]] = {}
    try:
        workflow_diagnostics, comfy_stats = asyncio.run(_validate_workflows(config))
        version = str(comfy_stats.get("system", {}).get("comfyui_version") or "unknown")
        checks.append(DoctorCheck("ComfyUI", "API", PASS, f"reachable; version {version}"))
    except (ComfyError, PresetError, OSError, RuntimeError) as exc:
        checks.append(DoctorCheck("ComfyUI", "API", FAIL, str(exc)))

    input_ok = _path_writable(config.comfyui_input_dir)
    checks.append(
        DoctorCheck(
            "ComfyUI",
            "input directory",
            PASS if input_ok else FAIL,
            f"{config.comfyui_input_dir} ({'writable' if input_ok else 'not writable'})",
        )
    )
    output_ok = _path_readable(config.comfyui_output_dir)
    checks.append(
        DoctorCheck(
            "ComfyUI",
            "output directory",
            PASS if output_ok else FAIL,
            f"{config.comfyui_output_dir} ({'readable' if output_ok else 'not readable'})",
        )
    )

    try:
        ts = inspect_tailscale()
        if not ts.installed:
            checks.append(DoctorCheck("Remote access", "Tailscale", WARN, "not installed; local mode remains available"))
        elif not ts.connected:
            checks.append(
                DoctorCheck(
                    "Remote access",
                    "Tailscale",
                    WARN,
                    f"installed ({ts.version or 'unknown version'}) but state is {ts.backend_state or 'unknown'}",
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    "Remote access",
                    "Tailscale",
                    PASS,
                    f"connected as {ts.login_name or 'unknown identity'}",
                )
            )
        if config.auth_provider == "tailscale":
            identity_matches = bool(ts.login_name and ts.login_name in config.allowed_logins)
            checks.append(
                DoctorCheck(
                    "Remote access",
                    "allowed login",
                    PASS if identity_matches else WARN,
                    "current Tailscale identity matches config"
                    if identity_matches
                    else "current Tailscale identity does not match configured allowed_logins",
                )
            )
            active = serve_active(config.port) if ts.installed else False
            checks.append(
                DoctorCheck(
                    "Remote access",
                    "Serve",
                    PASS if active else WARN,
                    f"Tailscale Serve {'active' if active else 'not detected'} for port {config.port}",
                )
            )
        else:
            checks.append(DoctorCheck("Remote access", "Remote auth", WARN, "local auth mode; remote access is not configured"))
    except (TailscaleError, OSError) as exc:
        checks.append(DoctorCheck("Remote access", "Tailscale", WARN, str(exc)))

    if workflow_diagnostics:
        try:
            presets = load_presets(config.workflow_dir)
        except PresetError:
            presets = {}
        for preset_id in sorted(workflow_diagnostics):
            diagnostics = workflow_diagnostics[preset_id]
            preset = presets.get(preset_id)
            optional = bool(preset and _builtin(preset))
            if diagnostics:
                status = WARN if optional else FAIL
                detail = "; ".join(diagnostics[:6])
                if len(diagnostics) > 6:
                    detail += f"; +{len(diagnostics) - 6} more"
            else:
                status = PASS
                detail = "compatible with current ComfyUI"
            label = preset.manifest.get("name", preset_id) if preset else preset_id
            checks.append(DoctorCheck("Workflows", label, status, detail))

    devices = comfy_stats.get("devices") if isinstance(comfy_stats, dict) else None
    if isinstance(devices, list) and devices:
        names = [str(device.get("name")) for device in devices if isinstance(device, dict) and device.get("name")]
        if names:
            checks.append(DoctorCheck("System", "GPU", PASS, ", ".join(names[:4])))

    return checks


def _overall(checks: Iterable[DoctorCheck]) -> str:
    return "NOT READY" if any(item.status == FAIL for item in checks) else "READY"


def format_text(checks: list[DoctorCheck]) -> str:
    lines = [f"Comfy Remote {__version__}", ""]
    sections: list[str] = []
    for item in checks:
        if item.section not in sections:
            sections.append(item.section)
    for section in sections:
        lines.append(section)
        for item in (check for check in checks if check.section == section):
            lines.append(f"{item.status:<4} {item.name} — {item.detail}")
        lines.append("")
    lines.extend(["Overall", _overall(checks)])
    return redact_text("\n".join(lines).rstrip())


def format_markdown(checks: list[DoctorCheck]) -> str:
    lines = [
        "## Comfy Remote doctor report",
        "",
        f"- Comfy Remote: `{__version__}`",
        f"- Overall: **{_overall(checks)}**",
        "",
        "| Section | Check | Result | Detail |",
        "| --- | --- | --- | --- |",
    ]
    for item in checks:
        detail = item.detail.replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {item.section} | {item.name} | **{item.status}** | {detail} |")
    lines.extend(
        [
            "",
            "> Paths, email addresses, Tailscale hostnames, and obvious secret values are redacted automatically.",
        ]
    )
    return redact_text("\n".join(lines))


def run_doctor(config_path: str | Path = "config.toml", *, report: bool = False) -> tuple[int, str]:
    checks = _collect(config_path)
    output = format_markdown(checks) if report else format_text(checks)
    return (1 if any(item.status == FAIL for item in checks) else 0), output
