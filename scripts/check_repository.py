from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", ".venv", ".pytest_cache", "__pycache__", "build", "dist", "data"}
BANNED_SUFFIXES = {".safetensors", ".ckpt", ".pt", ".pth", ".mp4", ".mov", ".webm", ".png", ".jpg", ".jpeg", ".webp", ".db", ".sqlite", ".log"}
WINDOWS_ABSOLUTE = re.compile(r"(?i)(?:^|[\s='\"])[a-z]:[\\/]")


def repository_files() -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        return [ROOT / line for line in result.stdout.splitlines() if line]
    except (OSError, subprocess.CalledProcessError):
        return [path for path in ROOT.rglob("*") if path.is_file()]


def main() -> int:
    failures: list[str] = []
    for path in repository_files():
        if not path.is_file() or any(part in SKIP_PARTS for part in path.relative_to(ROOT).parts):
            continue
        relative = path.relative_to(ROOT).as_posix()
        if relative == "config.toml":
            failures.append("machine-specific config is tracked: config.toml")
            continue
        if path.suffix.lower() in BANNED_SUFFIXES:
            failures.append(f"banned artifact: {relative}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            failures.append(f"unexpected binary file: {relative}")
            continue
        if WINDOWS_ABSOLUTE.search(text):
            failures.append(f"Windows absolute path: {relative}")
    if failures:
        print("Repository safety check failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1
    print("Repository safety check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
