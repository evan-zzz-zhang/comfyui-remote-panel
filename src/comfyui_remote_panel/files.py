from __future__ import annotations

import asyncio
import os
import re
import shutil
import stat
import uuid
import warnings
from pathlib import Path
from typing import Any

from PIL import Image, UnidentifiedImageError


MAX_IMAGE_BYTES = 25 * 1024 * 1024
MAX_VIDEO_BYTES = 200 * 1024 * 1024
MAX_AUDIO_BYTES = 50 * 1024 * 1024
MAX_IMAGE_SIDE = 8192
MAX_IMAGE_PIXELS = 40_000_000
FORMAT_EXTENSIONS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
VIDEO_SIGNATURES = {b"\x1aE\xdf\xa3": ".webm"}
_JOB_DIR_PATTERN = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.I)
_FLAT_FILE_PATTERN = re.compile(r"^rp_(?:[0-9a-f]{12}|legacy_[0-9a-f-]+)_.+", re.I)


class FileValidationError(ValueError):
    pass


class StorageCapacityError(RuntimeError):
    pass


class FileStore:
    def __init__(self, input_root: Path, output_root: Path, data_dir: Path):
        self.input_root = input_root.resolve()
        self.output_root = output_root.resolve()
        self.temp_root = (data_dir / "tmp").resolve()
        self._worker_limit = asyncio.Semaphore(2)

    async def _run_blocking(self, function: Any, *args: Any) -> Any:
        async with self._worker_limit:
            return await asyncio.to_thread(function, *args)

    def initialize(self) -> None:
        for directory in (self.input_root, self.output_root, self.temp_root):
            directory.mkdir(parents=True, exist_ok=True)
            if directory.is_symlink():
                raise RuntimeError(f"managed directory must not be a link: {directory}")

    async def save_upload(self, job_id: str, role: str, part: Any) -> dict[str, Any]:
        kind = self.role_kind(role)
        if kind is None:
            raise FileValidationError("invalid image role")
        limit = {"image": MAX_IMAGE_BYTES, "video": MAX_VIDEO_BYTES, "audio": MAX_AUDIO_BYTES}[kind]
        temp = self.temp_root / f"{uuid.uuid4().hex}.upload"
        size = 0
        try:
            with temp.open("xb") as handle:
                while True:
                    chunk = await part.read_chunk(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > limit:
                        labels = {"image": "单张图片不能超过 25MB", "video": "单个视频不能超过 200MB", "audio": "单个音频不能超过 50MB"}
                        raise FileValidationError(labels[kind])
                    handle.write(chunk)
            return await self._run_blocking(self._validate_and_store, temp, job_id, role, kind)
        except Exception:
            temp.unlink(missing_ok=True)
            raise

    def _validate_and_store(self, temp: Path, job_id: str, role: str, kind: str) -> dict[str, Any]:
        extension = self._validate_image(temp) if kind == "image" else self._validate_media(temp, kind)
        destination = self._safe_child(self.input_root, self.flat_input_name(job_id, role, extension))
        os.replace(temp, destination)
        return {"role": role, "path": destination, "size_bytes": destination.stat().st_size}

    @staticmethod
    def storage_key(job_id: str) -> str:
        compact = re.sub(r"[^0-9a-f]", "", str(job_id).lower())
        if len(compact) < 12:
            raise FileValidationError("invalid job id")
        return f"rp_{compact[:12]}"

    @classmethod
    def flat_input_name(cls, job_id: str, role: str, extension: str) -> str:
        if cls.role_kind(role) is None:
            raise FileValidationError("invalid input role")
        return f"{cls.storage_key(job_id)}_{role.replace('_', '-')}{extension.lower()}"

    @classmethod
    def flat_output_name(cls, job_id: str) -> str:
        return f"{cls.storage_key(job_id)}_result.mp4"

    @classmethod
    def comfy_output_prefix(cls, job_id: str) -> str:
        return cls.storage_key(job_id)

    @staticmethod
    def role_kind(role: str) -> str | None:
        if role in {"first", "last"} or role.startswith("image_") and role[6:].isdigit():
            return "image"
        if role.startswith("video_") and role[6:].isdigit():
            return "video"
        if role.startswith("audio_") and role[6:].isdigit():
            return "audio"
        return None

    def _validate_media(self, path: Path, kind: str) -> str:
        with path.open("rb") as handle:
            header = handle.read(64)
        if kind == "video":
            if header.startswith(b"\x1aE\xdf\xa3"):
                return ".webm"
            if len(header) >= 12 and header[4:8] == b"ftyp":
                return ".mov" if header[8:12] == b"qt  " else ".mp4"
            raise FileValidationError("仅支持真实的 MP4、MOV、WebM 视频")
        if kind == "audio":
            if header.startswith(b"RIFF") and header[8:12] == b"WAVE":
                return ".wav"
            if header.startswith(b"fLaC"):
                return ".flac"
            if header.startswith(b"OggS"):
                return ".ogg"
            if header.startswith(b"ID3") or len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0:
                return ".mp3"
            if len(header) >= 12 and header[4:8] == b"ftyp":
                return ".m4a"
            raise FileValidationError("仅支持真实的 WAV、MP3、FLAC、OGG、M4A 音频")
        raise FileValidationError("unsupported media kind")

    def _validate_image(self, path: Path) -> str:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(path) as image:
                    image_format = image.format
                    width, height = image.size
                    frames = getattr(image, "n_frames", 1)
                    image.verify()
            if image_format not in FORMAT_EXTENSIONS:
                raise FileValidationError("仅支持 JPG、PNG、WebP 图片")
            if frames != 1:
                raise FileValidationError("不支持动画或多帧图片")
            if max(width, height) > MAX_IMAGE_SIDE or width * height > MAX_IMAGE_PIXELS:
                raise FileValidationError("图片尺寸超过 8192 边长或 4000 万像素限制")
            with Image.open(path) as image:
                image.load()
            return FORMAT_EXTENSIONS[image_format]
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
            raise FileValidationError("图片内容无效或无法安全解码") from exc

    def copy_input(self, source: Path, new_job_id: str, role: str) -> dict[str, Any]:
        if self.role_kind(role) is None:
            raise FileValidationError("invalid input role")
        source = source.resolve(strict=True)
        self._assert_managed_file(source, self.input_root)
        destination = self._safe_child(self.input_root, self.flat_input_name(new_job_id, role, source.suffix))
        shutil.copy2(source, destination)
        return {"role": role, "path": destination, "size_bytes": destination.stat().st_size}

    async def copy_input_async(self, source: Path, new_job_id: str, role: str) -> dict[str, Any]:
        return await self._run_blocking(self.copy_input, source, new_job_id, role)

    async def ensure_capacity(
        self, incoming_bytes: int, tracked_bytes: int, minimum_free_bytes: int,
        output_reserve_bytes: int, max_tracked_bytes: int | None,
    ) -> None:
        await self._run_blocking(
            self._ensure_capacity, incoming_bytes, tracked_bytes, minimum_free_bytes,
            output_reserve_bytes, max_tracked_bytes,
        )

    def _ensure_capacity(
        self, incoming_bytes: int, tracked_bytes: int, minimum_free_bytes: int,
        output_reserve_bytes: int, max_tracked_bytes: int | None,
    ) -> None:
        required = max(0, incoming_bytes) + minimum_free_bytes + output_reserve_bytes
        free = min(shutil.disk_usage(root).free for root in {self.input_root, self.output_root, self.temp_root})
        if free < required:
            raise StorageCapacityError("磁盘可用空间不足，未接受新任务")
        if max_tracked_bytes is not None and tracked_bytes + incoming_bytes + output_reserve_bytes > max_tracked_bytes:
            raise StorageCapacityError("应用存储配额不足，未接受新任务")

    def comfy_input_name(self, path: Path) -> str:
        path = path.resolve(strict=True)
        self._assert_managed_file(path, self.input_root)
        return f"h3_remote/{path.relative_to(self.input_root).as_posix()}"

    def register_output(self, job_id: str, descriptor: dict[str, Any]) -> Path:
        if descriptor.get("type", "output") != "output":
            raise FileValidationError("unexpected output type")
        subfolder = descriptor.get("subfolder", "")
        filename = descriptor.get("filename")
        if not isinstance(subfolder, str) or not isinstance(filename, str) or not filename:
            raise FileValidationError("invalid output descriptor")
        expected_prefix = self.storage_key(job_id)
        normalized_subfolder = subfolder.replace("\\", "/").strip("/")
        if normalized_subfolder != "h3_remote" or Path(filename).name != filename:
            raise FileValidationError("output is outside the managed flat directory")
        if not filename.lower().startswith(expected_prefix.lower() + "_"):
            raise FileValidationError("output does not belong to the job")
        path = self._safe_child(self.output_root, filename)
        final = self._safe_child(self.output_root, self.flat_output_name(job_id))
        if not path.exists() and final.exists():
            path = final
        self._assert_managed_file(path.resolve(strict=True), self.output_root)
        if path.suffix.lower() != ".mp4" or final.suffix.lower() != ".mp4":
            raise FileValidationError("output is not an MP4 file")
        return path

    def finalize_output(self, job_id: str, path: Path) -> Path:
        source = path.resolve(strict=True)
        self._assert_managed_file(source, self.output_root)
        if source.suffix.lower() != ".mp4":
            raise FileValidationError("output is not an MP4 file")
        destination = self._safe_child(self.output_root, self.flat_output_name(job_id))
        if source == destination:
            return destination
        if destination.exists():
            self._assert_managed_file(destination.resolve(strict=True), self.output_root)
            return destination
        os.replace(source, destination)
        return destination

    def delete_exact(self, path: Path, role: str) -> None:
        root = self.output_root if role == "output" else self.input_root
        resolved = path.resolve(strict=True)
        self._assert_managed_file(resolved, root)
        resolved.unlink()

    def validate_output_file(self, path: Path) -> Path:
        resolved = path.resolve(strict=True)
        self._assert_managed_file(resolved, self.output_root)
        if resolved.suffix.lower() != ".mp4":
            raise FileValidationError("output is not an MP4 file")
        return resolved

    def cleanup_untracked(self, files: list[dict[str, Any]]) -> None:
        for file in files:
            try:
                self.delete_exact(Path(file["path"]), file["role"])
            except (OSError, FileValidationError):
                pass

    async def migrate_legacy(self, records: list[dict[str, Any]]) -> list[dict[str, str]]:
        return await self._run_blocking(self._migrate_legacy, records)

    def _migrate_legacy(self, records: list[dict[str, Any]]) -> list[dict[str, str]]:
        """Flatten tracked and untracked UUID folders without following links."""
        changes: list[dict[str, str]] = []
        tracked_by_path = {
            os.path.normcase(str(Path(record["path"]).resolve())): record
            for record in records
        }
        recovered: set[tuple[str, str]] = set()
        for record in records:
            if record.get("status") in {"submitting", "queued", "running"}:
                continue
            source = Path(record["path"])
            root = self.output_root if record["role"] == "output" else self.input_root
            target_name = (
                self.flat_output_name(record["job_id"])
                if record["role"] == "output"
                else self.flat_input_name(record["job_id"], record["role"], source.suffix)
            )
            target = self._safe_child(root, target_name)
            if not source.exists() and target.exists():
                changes.append({
                    "job_id": str(record["job_id"]),
                    "role": str(record["role"]),
                    "old_path": str(source),
                    "new_path": str(target),
                })
                recovered.add((str(record["job_id"]), str(record["role"])))
        for root in (self.input_root, self.output_root):
            for directory in root.iterdir():
                if not directory.is_dir() or not _JOB_DIR_PATTERN.fullmatch(directory.name):
                    continue
                if self._is_link_like(directory):
                    continue
                for source in directory.iterdir():
                    if self._is_link_like(source) or not source.is_file():
                        continue
                    record = tracked_by_path.get(os.path.normcase(str(source.resolve())))
                    if record is not None and record.get("status") in {"submitting", "queued", "running"}:
                        continue
                    if record is not None and (str(record["job_id"]), str(record["role"])) in recovered:
                        continue
                    if record is not None:
                        target_name = (
                            self.flat_output_name(record["job_id"])
                            if record["role"] == "output"
                            else self.flat_input_name(record["job_id"], record["role"], source.suffix)
                        )
                    else:
                        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", source.name).strip(".-") or "file"
                        target_name = f"rp_legacy_{directory.name}_{safe_name}"
                    target = self._safe_child(root, target_name)
                    if source.resolve() != target.resolve():
                        if target.exists():
                            continue
                        try:
                            os.replace(source, target)
                        except OSError as exc:
                            warnings.warn(f"无法迁移旧素材 {source} 到 {target}：{exc}", RuntimeWarning, stacklevel=2)
                            continue
                    if record is not None:
                        changes.append({
                            "job_id": str(record["job_id"]),
                            "role": str(record["role"]),
                            "old_path": str(source),
                            "new_path": str(target),
                        })
                try:
                    directory.rmdir()
                except OSError:
                    pass
        return changes

    async def scan_orphans(self, known_paths: set[Path], execute: bool = False) -> list[dict[str, str]]:
        return await self._run_blocking(self._scan_orphans, known_paths, execute)

    def _scan_orphans(self, known_paths: set[Path], execute: bool) -> list[dict[str, str]]:
        """Inspect only app-owned flat files, legacy UUID folders and upload temps."""
        known = {os.path.normcase(str(path.resolve())) for path in known_paths}
        findings: list[dict[str, str]] = []
        for root in (self.input_root, self.output_root):
            for candidate in root.iterdir():
                if not candidate.is_file() or not _FLAT_FILE_PATTERN.fullmatch(candidate.name):
                    continue
                if self._is_link_like(candidate):
                    findings.append({"path": str(candidate), "action": "refused_link_or_non_file"})
                    continue
                if os.path.normcase(str(candidate.resolve())) in known:
                    continue
                action = "would_delete"
                if execute:
                    candidate.unlink()
                    action = "deleted"
                findings.append({"path": str(candidate), "action": action})
            for directory in root.iterdir():
                if not directory.is_dir() or not _JOB_DIR_PATTERN.fullmatch(directory.name):
                    continue
                if self._is_link_like(directory):
                    findings.append({"path": str(directory), "action": "refused_link"})
                    continue
                for candidate in directory.iterdir():
                    if self._is_link_like(candidate) or not candidate.is_file():
                        findings.append({"path": str(candidate), "action": "refused_link_or_non_file"})
                        continue
                    if os.path.normcase(str(candidate.resolve())) in known:
                        continue
                    action = "would_delete"
                    if execute:
                        candidate.unlink()
                        action = "deleted"
                    findings.append({"path": str(candidate), "action": action})
                if execute:
                    try:
                        directory.rmdir()
                    except OSError:
                        pass
        for candidate in self.temp_root.iterdir():
            if candidate.suffix != ".upload":
                continue
            if self._is_link_like(candidate) or not candidate.is_file():
                findings.append({"path": str(candidate), "action": "refused_link_or_non_file"})
                continue
            action = "would_delete"
            if execute:
                candidate.unlink()
                action = "deleted"
            findings.append({"path": str(candidate), "action": action})
        return findings

    @staticmethod
    def _is_link_like(path: Path) -> bool:
        info = path.lstat()
        attributes = getattr(info, "st_file_attributes", 0)
        return stat.S_ISLNK(info.st_mode) or bool(attributes & 0x400)

    @staticmethod
    def _safe_child(root: Path, *parts: str) -> Path:
        candidate = root.joinpath(*parts).resolve()
        if os.path.commonpath((str(root), str(candidate))) != str(root):
            raise FileValidationError("path escapes managed directory")
        return candidate

    @staticmethod
    def _assert_managed_file(path: Path, root: Path) -> None:
        if os.path.commonpath((str(root), str(path))) != str(root):
            raise FileValidationError("file is outside managed directory")
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
            raise FileValidationError("managed path is not a regular file")
