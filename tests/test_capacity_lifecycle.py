import asyncio
import threading

import pytest

from comfyui_remote_panel.files import FileStore, StorageCapacityError


def storage(tmp_path, monkeypatch, free=100):
    value = FileStore(tmp_path / "input", tmp_path / "output", tmp_path / "data")
    value.initialize()
    usage = type("Usage", (), {"free": free})()
    monkeypatch.setattr("comfyui_remote_panel.files.shutil.disk_usage", lambda _: usage)
    return value, usage


async def test_pending_disk_reservations_prevent_overcommit(tmp_path, monkeypatch):
    files, _ = storage(tmp_path, monkeypatch)
    first = await files.reserve_capacity(80, 0, 0, 0, None)
    with pytest.raises(StorageCapacityError):
        await files.reserve_capacity(80, 0, 0, 0, None)
    await first.release()
    second = await files.reserve_capacity(80, 0, 0, 0, None)
    await second.release()


async def test_written_bytes_are_not_reserved_twice(tmp_path, monkeypatch):
    files, usage = storage(tmp_path, monkeypatch)
    first = await files.reserve_capacity(80, 0, 0, 0, None)
    await first.grow(60)
    first.written(60)
    usage.free = 40
    second = await files.reserve_capacity(20, 0, 0, 0, None)
    with pytest.raises(StorageCapacityError):
        await files.reserve_capacity(1, 0, 0, 0, None)
    await second.release()
    await first.release()


async def test_slow_upload_sees_completed_request_in_quota(tmp_path, monkeypatch):
    files, _ = storage(tmp_path, monkeypatch, free=1000)
    tracked = 0

    async def current_size():
        return tracked

    async def save():
        nonlocal tracked
        tracked = 80

    slow = await files.reserve_capacity(0, current_size, 0, 0, 100)
    fast = await files.reserve_capacity(80, current_size, 0, 0, 100)
    await fast.grow(80)
    fast.written(80)
    await fast.persist(save, 80)
    # The fast HTTP request can still be awaiting ComfyUI: its DB bytes must
    # count exactly once, without waiting for HTTP-finally to release it.
    await slow.grow(20)
    with pytest.raises(StorageCapacityError):
        await slow.grow(1)
    await slow.release()
    await fast.release()


async def test_cancelled_stream_removes_partial_upload(tmp_path, monkeypatch):
    files, _ = storage(tmp_path, monkeypatch, free=1000)
    reservation = await files.reserve_capacity(80, 0, 0, 0, None)

    class Part:
        count = 0

        async def read_chunk(self, _):
            self.count += 1
            if self.count == 1:
                return b"partial"
            raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        await files.save_upload("123456789abc", "image_0", Part(), reservation)
    await reservation.release()
    assert not list(files.temp_root.iterdir())
    assert not list(files.input_root.iterdir())
    assert files._reserved_capacity_bytes == 0


async def test_cancelled_copy_waits_for_worker_and_removes_only_copy(tmp_path, monkeypatch):
    files, _ = storage(tmp_path, monkeypatch, free=1000)
    source = files.input_root / "rp_aaaaaaaaaaaa_image-0.png"
    source.write_bytes(b"original")
    started, finish = threading.Event(), threading.Event()
    original_copy = files.copy_input

    def delayed_copy(*args):
        started.set()
        assert finish.wait(5)
        return original_copy(*args)

    monkeypatch.setattr(files, "copy_input", delayed_copy)
    reservation = await files.reserve_capacity(0, 0, 0, 0, None)
    task = asyncio.create_task(files.copy_input_async(source, "bbbbbbbbbbbb", "image_0", reservation))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    await reservation.release()
    assert source.read_bytes() == b"original"
    assert list(files.input_root.iterdir()) == [source]
    assert files._reserved_capacity_bytes == 0


async def test_cancelled_validation_cleans_final_file_after_worker_finishes(tmp_path, monkeypatch):
    files, _ = storage(tmp_path, monkeypatch, free=1000)
    started, finish = threading.Event(), threading.Event()
    original_validate = files._validate_and_store

    def delayed_validate(*args):
        started.set()
        assert finish.wait(5)
        return original_validate(*args)

    class Part:
        data = b"ID3" + b"x" * 20

        async def read_chunk(self, _):
            data, self.data = self.data, b""
            return data

    monkeypatch.setattr(files, "_validate_and_store", delayed_validate)
    task = asyncio.create_task(files.save_upload("123456789abc", "audio_0", Part()))
    try:
        assert await asyncio.to_thread(started.wait, 5)
        task.cancel()
        await asyncio.sleep(0)
        task.cancel()  # Shutdown can cancel a request more than once.
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        finish.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not list(files.temp_root.iterdir())
    assert not list(files.input_root.iterdir())


async def test_failed_copy_removes_partial_destination(tmp_path, monkeypatch):
    files, _ = storage(tmp_path, monkeypatch, free=1000)
    source = files.input_root / "rp_aaaaaaaaaaaa_image-0.png"
    source.write_bytes(b"original")

    def fail_copy(source, destination):
        destination.write_bytes(b"partial")
        raise OSError("simulated disk failure")

    monkeypatch.setattr("comfyui_remote_panel.files.shutil.copy2", fail_copy)
    reservation = await files.reserve_capacity(0, 0, 0, 0, None)
    with pytest.raises(OSError):
        await files.copy_input_async(source, "bbbbbbbbbbbb", "image_0", reservation)
    await reservation.release()
    assert list(files.input_root.iterdir()) == [source]
    assert source.read_bytes() == b"original"
