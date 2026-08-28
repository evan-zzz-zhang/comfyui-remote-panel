from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from .files import FileValidationError, FORMAT_EXTENSIONS


RESOLUTION_POLICIES = {"auto", "original"}
TARGET_MEGAPIXELS = (0.5, 1.0, 1.5, 2.0)


def normalize_resolution_policy(value: Any, default: str = "original") -> str:
    policy = str(value or default).lower()
    if policy not in RESOLUTION_POLICIES:
        raise FileValidationError("参考图分辨率策略无效")
    return policy


def normalize_target_megapixels(value: Any, default: float = 1.0) -> float:
    if value is None or value == "":
        return float(default)
    try:
        target = float(value)
    except (TypeError, ValueError) as exc:
        raise FileValidationError("参考图目标分辨率必须是数字") from exc
    if target not in TARGET_MEGAPIXELS:
        raise FileValidationError("参考图目标分辨率必须是 0.5 / 1.0 / 1.5 / 2.0 MP")
    return target


def target_size(width: int, height: int, target_megapixels: float) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        raise FileValidationError("图片尺寸无效")
    target_pixels = int(float(target_megapixels) * 1_000_000)
    source_pixels = width * height
    if source_pixels <= target_pixels:
        return width, height
    scale = (target_pixels / source_pixels) ** 0.5
    target_width = max(1, int(width * scale))
    target_height = max(1, int(height * scale))
    # Integer rounding should never push the result above the requested MP.
    while target_width * target_height > target_pixels:
        if target_width >= target_height and target_width > 1:
            target_width -= 1
        elif target_height > 1:
            target_height -= 1
        else:
            break
    return target_width, target_height


def _save_image(image: Image.Image, path: Path, image_format: str) -> None:
    temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.resize")
    try:
        if image_format == "JPEG":
            if image.mode not in {"RGB", "L"}:
                background = Image.new("RGB", image.size, "white")
                if "A" in image.getbands():
                    background.paste(image, mask=image.getchannel("A"))
                else:
                    background.paste(image.convert("RGB"))
                image = background
            image.save(temp, format="JPEG", quality=95, optimize=True, subsampling=0)
        elif image_format == "PNG":
            image.save(temp, format="PNG", optimize=True)
        elif image_format == "WEBP":
            image.save(temp, format="WEBP", quality=95, method=6)
        else:
            raise FileValidationError("仅支持 JPG、PNG、WebP 图片")
        with Image.open(temp) as check:
            check.verify()
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def process_image(
    path: Path,
    *,
    policy: str,
    target_megapixels: float | None = None,
) -> dict[str, Any]:
    policy = normalize_resolution_policy(policy)
    target = normalize_target_megapixels(target_megapixels) if policy == "auto" else None
    try:
        with Image.open(path) as source:
            image_format = str(source.format or "")
            if image_format not in FORMAT_EXTENSIONS:
                raise FileValidationError("仅支持 JPG、PNG、WebP 图片")
            orientation = source.getexif().get(274, 1)
            oriented = ImageOps.exif_transpose(source)
            oriented.load()
            source_width, source_height = oriented.size

        effective_width, effective_height = source_width, source_height
        resized = False
        orientation_applied = False

        if policy == "auto":
            effective_width, effective_height = target_size(source_width, source_height, float(target))
            resized = (effective_width, effective_height) != (source_width, source_height)
            orientation_applied = orientation not in {None, 1}
            if resized or orientation_applied:
                with Image.open(path) as source:
                    prepared = ImageOps.exif_transpose(source)
                    prepared.load()
                    if resized:
                        prepared = prepared.resize(
                            (effective_width, effective_height),
                            Image.Resampling.LANCZOS,
                        )
                    _save_image(prepared, path, image_format)

        return {
            "source_width": source_width,
            "source_height": source_height,
            "effective_width": effective_width,
            "effective_height": effective_height,
            "resolution_policy": policy,
            "target_megapixels": target,
            "resized": resized,
            "orientation_applied": orientation_applied,
        }
    except FileValidationError:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise FileValidationError("参考图缩放失败，未生成损坏文件") from exc
