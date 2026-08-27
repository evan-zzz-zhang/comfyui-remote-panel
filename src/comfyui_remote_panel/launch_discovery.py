from __future__ import annotations

from dataclasses import dataclass
import locale
from pathlib import Path
import shlex


@dataclass(frozen=True)
class ComfyStartOption:
    label: str
    command: tuple[str, ...]


def _read_batch_text(path: Path) -> str | None:
    encodings = ["utf-8-sig", locale.getpreferredencoding(False), "gb18030"]
    seen: set[str] = set()
    for encoding in encodings:
        key = encoding.lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            return path.read_text(encoding=encoding)
        except (UnicodeDecodeError, OSError):
            continue
    return None


def _clean_token(token: str) -> str:
    value = token.strip()
    if len(value) >= 2 and value[0] == value[-1] == '"':
        value = value[1:-1]
    return value


def _portable_python_token(token: str) -> bool:
    value = _clean_token(token).replace("/", "\\").lower().lstrip(".\\")
    return value.endswith("python_embeded\\python.exe")


def _portable_main_token(token: str) -> bool:
    value = _clean_token(token).replace("/", "\\").lower().lstrip(".\\")
    return value == "comfyui\\main.py"


def _command_from_batch_line(
    line: str,
    *,
    python_executable: Path,
) -> tuple[str, ...] | None:
    stripped = line.strip()
    if not stripped or stripped.startswith(("::", ":")):
        return None
    lower = stripped.lower()
    if lower.startswith(("rem ", "echo ", "@echo ")):
        return None

    try:
        parts = [_clean_token(part) for part in shlex.split(stripped, posix=False)]
    except ValueError:
        return None
    if not parts:
        return None

    try:
        python_index = next(index for index, token in enumerate(parts) if _portable_python_token(token))
    except StopIteration:
        return None
    tail = parts[python_index + 1 :]
    if not any(_portable_main_token(token) for token in tail):
        return None
    # Directly launching Python is preferable to wrapping cmd.exe around a .bat,
    # but only when the batch invocation is static. Environment-variable based
    # launch lines should be left alone rather than guessed incorrectly.
    if any("%" in token for token in tail):
        return None

    normalized: list[str] = [str(python_executable)]
    for token in tail:
        if _portable_main_token(token):
            normalized.append("ComfyUI/main.py")
        else:
            normalized.append(token)
    return tuple(normalized)


def discover_portable_start_options(
    root: Path,
    python_executable: Path | None,
) -> list[ComfyStartOption]:
    if python_executable is None or not python_executable.is_file() or not root.is_dir():
        return []

    options: list[ComfyStartOption] = []
    seen_commands: set[tuple[str, ...]] = set()
    for batch in sorted(root.glob("*.bat"), key=lambda path: path.name.casefold()):
        text = _read_batch_text(batch)
        if text is None:
            continue
        command = None
        for line in text.splitlines():
            command = _command_from_batch_line(line, python_executable=python_executable)
            if command is not None:
                break
        if command is None or command in seen_commands:
            continue
        seen_commands.add(command)
        options.append(ComfyStartOption(batch.name, command))
    return options
