from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {
    ".git",
    ".venv",
    ".pytest_cache",
    ".pytest_tmp",
    "__pycache__",
    "build",
    "dist",
    "data",
}
BANNED_SUFFIXES = {
    ".safetensors",
    ".ckpt",
    ".pt",
    ".pth",
    ".mp4",
    ".mov",
    ".webm",
    ".mkv",
    ".avi",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
    ".wav",
    ".mp3",
    ".flac",
    ".m4a",
    ".db",
    ".sqlite",
    ".log",
}
BANNED_BASENAMES = {
    "config.toml",
    "panel.pid",
    "panel-runtime.json",
}
WINDOWS_ABSOLUTE = re.compile(r"(?i)(?:^|[\s='\"])[a-z]:[\\/]")
DOCUMENTED_WINDOWS_PLACEHOLDER = re.compile(r"(?i)\b[a-z]:[\\/]你的目录[\\/]")
POSIX_HOME_ABSOLUTE = re.compile(r"(?i)(?:^|[\s='\"])/(?:Users|home)/[^\s'\"/]+/")
EMAIL = re.compile(r"\b[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
TAILSCALE_HOST = re.compile(r"(?i)\b[a-z0-9-]+(?:\.[a-z0-9-]+)*\.ts\.net\b")
PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA |PGP )?PRIVATE KEY-----")
TOKEN_PATTERNS = (
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{30,}\b"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
)
SAFE_EMAIL_DOMAINS = {"example.com", "example.org", "example.net", "users.noreply.github.com"}
SYNTHETIC_WINDOWS_FIXTURE_FILES = {
    "src/comfyui_remote_panel/doctor.py",
    "tests/test_doctor.py",
}


def repository_files() -> list[Path]:
    try:
        result = subprocess.run(
            [
                "git",
                "-c",
                f"safe.directory={ROOT.as_posix()}",
                "ls-files",
                "--cached",
                "--others",
                "--exclude-standard",
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return [ROOT / line for line in result.stdout.splitlines() if line]
    except (OSError, subprocess.CalledProcessError):
        return [path for path in ROOT.rglob("*") if path.is_file()]


def _strip_known_synthetic_windows_fixtures(relative: str, text: str) -> str:
    """Remove only deliberate Doctor redaction fixtures from privacy scanning.

    The Doctor tests intentionally contain fake absolute paths to prove report
    redaction. Old reachable blobs also contain an assertion for a bare fake
    drive-root token. Those exact synthetic fixtures are ignored; other paths,
    including other paths in the same files, are still scanned normally.
    """
    if relative not in SYNTHETIC_WINDOWS_FIXTURE_FILES:
        return text

    prefixes = (
        "C:" + "\\Users\\Alice",
        "C:" + "\\\\Users\\\\Alice",
        "G:" + "\\AI-project",
        "G:" + "\\\\AI-project",
        "G:" + "\\AI\\ComfyUI_H3_Portable",
        "G:" + "\\\\AI\\\\ComfyUI_H3_Portable",
        "G:" + "\\AI\\ComfyUI",
        "G:" + "\\\\AI\\\\ComfyUI",
    )
    for prefix in prefixes:
        text = text.replace(prefix, "<SYNTHETIC_PATH>")

    # Historical test_doctor.py asserted that a fake G:\ drive prefix was absent
    # from the redacted report. Match only the exact quoted source token so a real
    # path elsewhere in this file would still be reported.
    if relative == "tests/test_doctor.py":
        historical_drive_assertion_token = '"' + "G:" + "\\\\" + '"'
        text = text.replace(historical_drive_assertion_token, '"<SYNTHETIC_DRIVE>"')

    return text


def _known_synthetic_tailscale_host(host: str) -> bool:
    # An older revision of this scanner contained this literal as a test marker.
    # Construct it from pieces so the scanner does not match its own source.
    return host.lower() == ("tail123" + ".ts.net")


def _privacy_findings(relative: str, text: str) -> list[str]:
    failures: list[str] = []

    path_scan_text = DOCUMENTED_WINDOWS_PLACEHOLDER.sub("<DOCUMENTED_PATH>/", text)
    path_scan_text = _strip_known_synthetic_windows_fixtures(relative, path_scan_text)
    if WINDOWS_ABSOLUTE.search(path_scan_text):
        failures.append(f"Windows absolute path: {relative}")
    if POSIX_HOME_ABSOLUTE.search(text):
        failures.append(f"user-home absolute path: {relative}")

    for match in EMAIL.finditer(text):
        domain = match.group(1).lower()
        if domain not in SAFE_EMAIL_DOMAINS:
            failures.append(f"non-example email address: {relative}")
            break

    for match in TAILSCALE_HOST.finditer(text):
        host = match.group(0).lower()
        synthetic_test = relative.startswith("tests/")
        documented_placeholder = "your-device.your-tailnet.ts.net" in host
        historical_scanner_fixture = _known_synthetic_tailscale_host(host)
        if not synthetic_test and not documented_placeholder and not historical_scanner_fixture:
            failures.append(f"non-placeholder Tailscale hostname: {relative}")
            break

    if PRIVATE_KEY.search(text):
        failures.append(f"private key material: {relative}")

    for pattern in TOKEN_PATTERNS:
        if pattern.search(text):
            failures.append(f"credential-like token: {relative}")
            break

    return failures


def main() -> int:
    failures: list[str] = []
    for path in repository_files():
        if not path.is_file() or any(part in SKIP_PARTS for part in path.relative_to(ROOT).parts):
            continue
        relative = path.relative_to(ROOT).as_posix()
        basename = path.name.lower()
        if basename in BANNED_BASENAMES or basename == ".env" or basename.startswith(".env."):
            failures.append(f"machine-specific/runtime file is tracked: {relative}")
            continue
        if path.suffix.lower() in BANNED_SUFFIXES:
            failures.append(f"banned artifact: {relative}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            failures.append(f"unexpected binary file: {relative}")
            continue
        failures.extend(_privacy_findings(relative, text))

    if failures:
        print("Repository safety check failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print("Repository safety check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
