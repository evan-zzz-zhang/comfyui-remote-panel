from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

from check_repository import (
    BANNED_BASENAMES,
    BANNED_SUFFIXES,
    ROOT,
    _privacy_findings,
)


SAFE_COMMIT_EMAIL_SUFFIXES = (
    "@users.noreply.github.com",
    "@noreply.github.com",
)


def _git(*args: str, text: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=text,
    )


def historical_objects() -> list[tuple[str, str]]:
    result = _git("rev-list", "--objects", "--all")
    objects: list[tuple[str, str]] = []
    for line in result.stdout.splitlines():
        object_id, separator, path = line.partition(" ")
        if separator and path:
            objects.append((object_id, path))
    return objects


def non_noreply_commit_emails() -> list[str]:
    result = _git("log", "--all", "--format=%ae%n%ce")
    emails = {
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip()
        and "@" in line
        and not line.strip().lower().endswith(SAFE_COMMIT_EMAIL_SUFFIXES)
    }
    return sorted(emails, key=str.casefold)


def scan_history() -> list[str]:
    failures: list[str] = []
    seen: set[tuple[str, str]] = set()

    for object_id, path_text in historical_objects():
        relative = Path(path_text).as_posix()
        key = (object_id, relative)
        if key in seen:
            continue
        seen.add(key)

        path = Path(relative)
        basename = path.name.lower()
        if basename in BANNED_BASENAMES or basename == ".env" or basename.startswith(".env."):
            failures.append(f"historical machine/runtime file: {relative}")
            continue
        if path.suffix.lower() in BANNED_SUFFIXES:
            failures.append(f"historical banned artifact: {relative}")
            continue

        try:
            kind = _git("cat-file", "-t", object_id).stdout.strip()
        except subprocess.CalledProcessError:
            continue
        if kind != "blob":
            continue

        try:
            data = _git("cat-file", "-p", object_id, text=False).stdout
        except subprocess.CalledProcessError:
            continue
        if not isinstance(data, bytes):
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            # Binary source files are reported by suffix/name checks when they are
            # known dangerous artifacts. Other historical binary build metadata is
            # ignored here rather than dumped to the terminal.
            continue

        for finding in _privacy_findings(relative, text):
            failures.append(f"historical {finding[0].lower() + finding[1:]}")

    return sorted(set(failures))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Scan all reachable Git history for public-release privacy risks.")
    parser.add_argument(
        "--strict-metadata",
        action="store_true",
        help="also fail when commit author/committer metadata contains non-noreply email addresses",
    )
    args = parser.parse_args(argv)

    try:
        failures = scan_history()
        metadata_emails = non_noreply_commit_emails()
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"History safety check could not run: {exc}")
        return 2

    if metadata_emails:
        print(
            "History metadata notice: non-noreply author/committer email address(es) exist. "
            "GitHub exposes commit metadata in a public repository. Review whether that is acceptable before publication."
        )
        if args.strict_metadata:
            failures.append(
                "non-noreply commit metadata email address(es) exist; use Git history rewriting only if you intentionally want to remove them"
            )

    if failures:
        print("Git history safety check failed:")
        print("\n".join(f"- {failure}" for failure in failures))
        return 1

    print("Git history content safety check passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
