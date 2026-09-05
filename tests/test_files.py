from __future__ import annotations

from pathlib import Path

import pytest
from PIL import Image

from comfyui_remote_panel.files import (
    MAX_IMAGE_BYTES,
    FileStore,
    FileValidationError,
    StorageCapacityError,
)


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


def test_register_output_requires_flat_managed_subfolder(tmp_path):
    value = store(tmp_path)
    job_id = "123e4567-e89b-42d3-a456-426614174000"
    output = value.output_root / f"{value.storage_key(job_id)}_00001_.mp4"
    output.write_bytes(b"video")
    descriptor = {"filename": output.name, "subfolder": "h3_remote", "type": "output"}
    assert value.register_output(job_id, descriptor) == output
    with pytest.raises(FileValidationError):
        value.register_output("223e4567-e89b-42d3-a456-426614174000", descriptor)


def test_flat_output_is_finalized_without_a_job_directory(tmp_path):
    value = store(tmp_path)
    job_id = "123e4567-e89b-42d3-a456-426614174000"
    source = value.output_root / f"{value.storage_key(job_id)}_00001_.mp4"
    source.write_bytes(b"video")

    final = value.finalize_output(job_id, source)

    assert final == value.output_root / f"{value.storage_key(job_id)}_result.mp4"
    assert final.read_bytes() == b"video"
    assert not source.exists()


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


@pytest.mark.asyncio
async def test_unknown_length_upload_grows_capacity_reservation_from_actual_chunks(tmp_path, monkeypatch):
    value = store(tmp_path)
    image_data = Path(tmp_path / "source.png")
    Image.new("RGB", (32, 32), "red").save(image_data, format="PNG")
    payload = image_data.read_bytes()
    monkeypatch.setattr(
        "comfyui_remote_panel.files.shutil.disk_usage",
        lambda _path: type("Usage", (), {"free": 10**9})(),
    )
    reservation = await value.reserve_capacity(0, 0, 0, 0, len(payload))

    class ChunkedPart:
        def __init__(self, chunks):
            self.chunks = iter(chunks)

        async def read_chunk(self, _size):
            return next(self.chunks, b"")

    try:
        saved = await value.save_upload(
            "123e4567-e89b-42d3-a456-426614174000",
            "first",
            ChunkedPart([payload[:3], payload[3:]]),
            reservation,
        )
        assert saved["size_bytes"] == len(payload)
        assert Path(saved["path"]).exists()
    finally:
        await reservation.release()


@pytest.mark.asyncio
async def test_capacity_reservations_block_concurrent_requests_and_release(tmp_path, monkeypatch):
    value = store(tmp_path)
    monkeypatch.setattr(
        "comfyui_remote_panel.files.shutil.disk_usage",
        lambda _path: type("Usage", (), {"free": 10**9})(),
    )
    first = await value.reserve_capacity(8, 0, 0, 0, 10)
    with pytest.raises(StorageCapacityError):
        await value.reserve_capacity(3, 0, 0, 0, 10)
    await first.release()
    second = await value.reserve_capacity(10, 0, 0, 0, 10)
    await second.release()


@pytest.mark.asyncio
async def test_retry_copy_reserves_actual_source_size(tmp_path, monkeypatch):
    value = store(tmp_path)
    source = value.input_root / "rp_aaaaaaaaaaaa_image-0.png"
    source.write_bytes(b"x" * 12)
    monkeypatch.setattr(
        "comfyui_remote_panel.files.shutil.disk_usage",
        lambda _path: type("Usage", (), {"free": 10**9})(),
    )
    reservation = await value.reserve_capacity(0, 0, 0, 0, 11)
    try:
        with pytest.raises(StorageCapacityError):
            await value.copy_input_async(source, "bbbbbbbbbbbb", "image_0", reservation)
        assert not (value.input_root / "rp_bbbbbbbbbbbb_image-0.png").exists()
    finally:
        await reservation.release()


@pytest.mark.asyncio
async def test_orphan_scan_is_dry_run_then_exact_delete(tmp_path):
    value = store(tmp_path)
    job_dir = value.input_root / "123e4567-e89b-42d3-a456-426614174000"
    job_dir.mkdir()
    tracked = job_dir / "tracked.png"
    orphan = job_dir / "orphan.png"
    tracked.write_bytes(b"tracked")
    orphan.write_bytes(b"orphan")

    report = await value.scan_orphans({tracked})
    assert report == [{"path": str(orphan), "action": "would_delete"}]
    assert orphan.exists()

    report = await value.scan_orphans({tracked}, execute=True)
    assert report == [{"path": str(orphan), "action": "deleted"}]
    assert tracked.exists() and not orphan.exists()


@pytest.mark.asyncio
async def test_flat_orphan_scan_only_targets_panel_prefix(tmp_path):
    value = store(tmp_path)
    orphan = value.output_root / "rp_123456789abc_result.mp4"
    user_file = value.output_root / "my-video.mp4"
    orphan.write_bytes(b"orphan")
    user_file.write_bytes(b"user")

    report = await value.scan_orphans(set())

    assert report == [{"path": str(orphan), "action": "would_delete"}]
    assert orphan.exists() and user_file.exists()


@pytest.mark.asyncio
async def test_legacy_uuid_files_are_flattened_without_losing_untracked_files(tmp_path):
    value = store(tmp_path)
    job_id = "123e4567-e89b-42d3-a456-426614174000"
    input_dir = value.input_root / job_id
    output_dir = value.output_root / job_id
    input_dir.mkdir()
    output_dir.mkdir()
    tracked_input = input_dir / f"{job_id}-first.png"
    tracked_output = output_dir / "video_00001_.mp4"
    untracked = output_dir / "old-preview.mp4"
    tracked_input.write_bytes(b"input")
    tracked_output.write_bytes(b"output")
    untracked.write_bytes(b"preview")

    changes = await value.migrate_legacy([
        {"job_id": job_id, "role": "first", "path": tracked_input, "size_bytes": 5},
        {"job_id": job_id, "role": "output", "path": tracked_output, "size_bytes": 6},
    ])

    assert {item["role"] for item in changes} == {"first", "output"}
    assert (value.input_root / value.flat_input_name(job_id, "first", ".png")).read_bytes() == b"input"
    assert (value.output_root / value.flat_output_name(job_id)).read_bytes() == b"output"
    assert list(value.input_root.glob(f"{job_id}*")) == []
    assert list(value.output_root.glob(f"{job_id}*")) == []
    assert list(value.output_root.glob("rp_legacy_*.mp4"))


@pytest.mark.asyncio
async def test_storage_admission_rejects_low_free_space(tmp_path, monkeypatch):
    value = store(tmp_path)
    usage = type("Usage", (), {"free": 99})()
    monkeypatch.setattr("comfyui_remote_panel.files.shutil.disk_usage", lambda _path: usage)
    with pytest.raises(Exception, match="空间不足"):
        await value.ensure_capacity(1, 0, 50, 50, None)
