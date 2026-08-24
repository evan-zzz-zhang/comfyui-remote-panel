from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from comfyui_remote_panel.files import MAX_IMAGE_BYTES, FileStore, FileValidationError


def store(tmp_path: Path) -> FileStore:
    value = FileStore(tmp_path / "input", tmp_path / "output", tmp_path / "data")
    value.initialize()
    return value


@pytest.mark.parametrize(("image_format", "extension"), [("JPEG", ".jpg"), ("PNG", ".png"), ("WEBP", ".webp")])
def test_validates_real_image_formats(tmp_path, image_format, extension):
    path = tmp_path / "upload.bin"
    Image.new("RGB", (32, 32), "red").save(path, format=image_format)
    assert store(tmp_path)._validate_image(path) == extension


def test_rejects_format_spoof(tmp_path):
    path = tmp_path / "fake.png"
    path.write_bytes(b"not an image")
    with pytest.raises(FileValidationError):
        store(tmp_path)._validate_image(path)


def test_rejects_animated_webp(tmp_path):
    path = tmp_path / "animated.webp"
    frames = [Image.new("RGB", (8, 8), color) for color in ("red", "blue")]
    frames[0].save(path, save_all=True, append_images=frames[1:], format="WEBP", duration=100)
    with pytest.raises(FileValidationError, match="多帧"):
        store(tmp_path)._validate_image(path)


@pytest.mark.parametrize(("kind", "data", "extension"), [
    ("video", b"\x00\x00\x00\x18ftypisom" + b"\x00" * 20, ".mp4"),
    ("video", b"\x1aE\xdf\xa3" + b"\x00" * 20, ".webm"),
    ("audio", b"RIFF\x24\x00\x00\x00WAVEfmt " + b"\x00" * 20, ".wav"),
    ("audio", b"ID3" + b"\x00" * 20, ".mp3"),
    ("audio", b"fLaC" + b"\x00" * 20, ".flac"),
])
def test_validates_media_by_content_not_filename(tmp_path, kind, data, extension):
    path = tmp_path / "spoofed.bin"
    path.write_bytes(data)
    assert store(tmp_path)._validate_media(path, kind) == extension


@pytest.mark.parametrize("kind", ["video", "audio"])
def test_rejects_invalid_media_signatures(tmp_path, kind):
    path = tmp_path / "fake.bin"
    path.write_bytes(b"not media")
    with pytest.raises(FileValidationError):
        store(tmp_path)._validate_media(path, kind)


def test_delete_rejects_outside_file(tmp_path):
    value = store(tmp_path)
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(b"video")
    with pytest.raises(FileValidationError):
        value.delete_exact(outside, "output")
    assert outside.exists()


def test_register_output_requires_exact_job_subfolder(tmp_path):
    value = store(tmp_path)
    output = value.output_root / "job" / "video_00001.mp4"
    output.parent.mkdir()
    output.write_bytes(b"video")
    descriptor = {"filename": output.name, "subfolder": "h3_remote/job", "type": "output"}
    assert value.register_output("job", descriptor) == output
    with pytest.raises(FileValidationError):
        value.register_output("other", descriptor)


@pytest.mark.asyncio
async def test_oversize_stream_is_rejected_and_temp_file_is_removed(tmp_path):
    class OversizePart:
        remaining = MAX_IMAGE_BYTES + 1

        async def read_chunk(self, size):
            if self.remaining <= 0:
                return b""
            amount = min(size, self.remaining)
            self.remaining -= amount
            return b"x" * amount

    value = store(tmp_path)
    with pytest.raises(FileValidationError, match="25MB"):
        await value.save_upload("job", "first", OversizePart())
    assert list(value.temp_root.iterdir()) == []
