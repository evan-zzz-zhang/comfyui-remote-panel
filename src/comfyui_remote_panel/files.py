from __future__ import annotations

import os
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


class FileValidationError(ValueError):
    pass


class FileStore:
    def __init__(self, input_root: Path, output_root: Path, data_dir: Path):
        self.input_root = input_root.resolve()
        self.output_root = output_root.resolve()
        self.temp_root = (data_dir / "tmp").resolve()

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
            extension = self._validate_image(temp) if kind == "image" else self._validate_media(temp, kind)
            job_dir = self._safe_child(self.input_root, job_id)
            job_dir.mkdir(parents=True, exist_ok=True)
            destination = self._safe_child(job_dir, f"{job_id}-{role.replace('_', '-')}{extension}")
            os.replace(temp, destination)
            return {"role": role, "path": destination, "size_bytes": destination.stat().st_size}
        except Exception:
            temp.unlink(missing_ok=True)
            raise

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
        destination_dir = self._safe_child(self.input_root, new_job_id)
        destination_dir.mkdir(parents=True, exist_ok=True)
        destination = self._safe_child(destination_dir, f"{new_job_id}-{role.replace('_', '-')}{source.suffix.lower()}")
        shutil.copy2(source, destination)
        return {"role": role, "path": destination, "size_bytes": destination.stat().st_size}

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
        expected = f"h3_remote/{job_id}"
        normalized_subfolder = subfolder.replace("\\", "/").strip("/")
        if normalized_subfolder != expected:
            raise FileValidationError("output is outside the job directory")
        path = self._safe_child(self.output_root, job_id, Path(filename).name)
        self._assert_managed_file(path.resolve(strict=True), self.output_root)
        if path.suffix.lower() != ".mp4":
            raise FileValidationError("output is not an MP4 file")
        return path

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
