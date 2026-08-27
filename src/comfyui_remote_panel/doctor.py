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
from .doctor_workflows import load_doctor_presets
from .panel_control import PanelController, PanelControlError, port_available
from .preset import BUILTIN_WORKFLOW_DIR, Preset, PresetError
from .tailscale import TailscaleError, inspect_tailscale, serve_active


PASS = "PASS"
WARN = "WARN"
FAIL = "FAIL"
_PATH_CHECK_NAMES = {"config.toml", "data directory", "input directory", "output directory"}


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


async def _validate_workflows(
    config: Config,
) -> tuple[dict[str, list[str]], dict, dict[str, Preset]]:
    presets = await load_doctor_presets(config)
    client = ComfyClient(config.comfyui_base_url, config.minimum_comfyui_version, "doctor")
    await client.start()
    try:
        stats = await client.system_stats()
        diagnostics = await client.validate_presets(list(presets.values()), stats)
        return diagnostics, stats, presets
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
    # Report diagnostics can point at arbitrary drives, not only the current
    # user's profile. Redact unquoted absolute path tokens as a second line of
    # defence; structured path checks are replaced separately below.
    text = re.sub(r"(?i)\b[A-Z]:\\[^\s|]+", "<PATH>", text)
    text = re.sub(r"(?<![A-Za-z0-9_])/(?:[^\s|/]+/)+[^\s|]*", "<PATH>", text)
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


def _report_detail(item: DoctorCheck) -> str:
    detail = item.detail
    if item.name in _PATH_CHECK_NAMES:
        suffix = re.search(r"\s+\([^\r\n]*\)$", detail)
        detail = "<PATH>" + (suffix.group(0) if suffix else "")
    return detail


def _fallback_output_type(preset: Preset) -> str:
    bindings = preset.manifest.get("output_bindings")
    if isinstance(bindings, list) and bindings:
        primary = next((item for item in bindings if isinstance(item, dict) and item.get("primary")), bindings[0])
        if isinstance(primary, dict) and primary.get("kind"):
            return str(primary["kind"])
    return "unknown"


def _required_input_summary(preset: Preset) -> str:
    profile = preset.manifest.get("capability_profile")
    if isinstance(profile, dict):
        required = profile.get("required_media_inputs")
        if isinstance(required, dict) and required:
            parts = [f"{kind}×{count}" for kind, count in required.items() if int(count or 0) > 0]
            if parts:
                return ", ".join(parts)
    media = preset.manifest.get("input_bindings", {}).get("media", {})
    if isinstance(media, dict) and media.get("type") == "slots":
        counts: dict[str, int] = {}
        for slot in media.get("slots", {}).values():
            if not isinstance(slot, dict):
                continue
            required = slot.get("required") is True or (
                isinstance(slot.get("ui"), dict) and slot["ui"].get("optional") is False
            )
            if required:
                kind = str(slot.get("kind") or "file")
                counts[kind] = counts.get(kind, 0) + 1
        if counts:
            return ", ".join(f"{kind}×{count}" for kind, count in counts.items())
    return "none"


def _preflight_messages(preset: Preset, severity: str) -> list[str]:
    preflight = preset.manifest.get("preflight")
    if not isinstance(preflight, dict):
        return []
    messages: list[str] = []
    for section, item in preflight.items():
        if not isinstance(item, dict) or item.get("status") != severity:
            continue
        message = str(item.get("message") or severity.lower())
        messages.append(f"{section}: {message}")
    return messages


def _preflight_warnings(preset: Preset) -> list[str]:
    return _preflight_messages(preset, WARN)


def _preflight_failures(preset: Preset) -> list[str]:
    return _preflight_messages(preset, FAIL)


def workflow_compatibility_detail(preset: Preset, diagnostics: list[str]) -> str:
    """Return a privacy-safe one-line profile; never serializes workflow JSON."""
    profile = preset.manifest.get("capability_profile")
    output_type = (
        str(profile.get("output_type"))
        if isinstance(profile, dict) and profile.get("output_type")
        else _fallback_output_type(preset)
    )
    missing_nodes = [item.removeprefix("缺少节点：") for item in diagnostics if item.startswith("缺少节点：")]
    other_runtime = [item for item in diagnostics if not item.startswith("缺少节点：")]
    warnings = [f"FAIL {item}" for item in _preflight_failures(preset)]
    warnings.extend(_preflight_warnings(preset))
    if other_runtime:
        warnings.extend(other_runtime[:4])
    warning_text = "; ".join(warnings[:4]) or "none"
    missing_text = ", ".join(missing_nodes[:6]) or "none"
    return (
        f"output={output_type}; required inputs={_required_input_summary(preset)}; "
        f"missing nodes={missing_text}; warnings={warning_text}"
    )


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
