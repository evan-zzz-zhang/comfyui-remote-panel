"""Download the separately licensed official prompt guides; never execute them."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.request import urlopen


def verified_content(data: bytes, expected: str) -> bytes:
    data = data.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError("Official resource checksum mismatch; nothing written")
    return data


def download(root: Path) -> None:
    entries = json.loads((root / "resources.json").read_text(encoding="utf-8"))
    for item in entries:
        destination = (root / item["path"]).resolve()
        if not destination.is_relative_to(root.resolve()):
            raise ValueError("Resource destination escapes the bundle")
        if destination.exists():
            verified_content(destination.read_bytes(), item["sha256"])
            print(f"Verified {item['path']}")
            continue
        with urlopen(item["url"], timeout=60) as response:
            content = verified_content(response.read(), item["sha256"])
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Do not replace an existing installation's resources.
        with destination.open("xb") as output:
            output.write(content)
        print(f"Downloaded {item['path']}")


if __name__ == "__main__":
    download(Path(__file__).resolve().parent)
