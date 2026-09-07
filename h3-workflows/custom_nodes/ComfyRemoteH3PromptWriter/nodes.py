from __future__ import annotations

import math
import copy
import json
import os
import re
import wave
from pathlib import Path
from uuid import uuid4

import av
import numpy as np
import folder_paths
from comfy.cli_args import args
from PIL import Image
from comfy_api.latest import Types, io, ui
from .ref2va_contract import (
    REF2VA_FPS,
    REF2VA_MAX_DURATION,
    REF2VA_MIN_DURATION,
    audio_duration as _contract_audio_duration,
    h3_length as _contract_h3_length,
    normalize_reference_video as _contract_normalize_reference_video,
    validate_synced_audio as _contract_validate_synced_audio,
)

from .backend.assembly import AssemblyError, assemble_request
from .backend.media import CACHE_ROOT, STORE, MediaError
from .backend.models.contract import ModelError
from .backend.models.ollama_backend import BACKEND as OLLAMA_BACKEND


FALLBACK_OLLAMA_MODELS = ("gemma4:e4b", "gemma3:4b", "qwen2.5vl:7b")
H3_ASPECT_RATIOS = {
    "1:1": 1.0,
    "2:3": 2 / 3,
    "3:2": 3 / 2,
    "3:4": 3 / 4,
    "4:3": 4 / 3,
    "9:16": 9 / 16,
    "16:9": 16 / 9,
    "21:9": 21 / 9,
}
REF2VA_TASK_TYPES = {
    "keyframe completion", "reference generation", "video editing",
    "video continuation", "audio reuse", "audio reference",
}


def _available_ollama_models() -> list[str]:
    """Return installed vision-capable Ollama models, recommended model first."""
    try:
        detected = OLLAMA_BACKEND.detect()
        names = [
            str(model["remote_model"])
            for model in detected.get("compatible_models", [])
            if model.get("remote_model")
        ]
    except Exception:
        names = []
    ordered = [name for name in FALLBACK_OLLAMA_MODELS if name in names]
    ordered.extend(name for name in names if name not in ordered)
    return ordered or list(FALLBACK_OLLAMA_MODELS)


def _has_image(image) -> bool:
    return image is not None and hasattr(image, "shape") and len(image.shape) >= 4 and int(image.shape[0]) > 0


def _has_audio(audio) -> bool:
    waveform = audio.get("waveform") if isinstance(audio, dict) else None
    return waveform is not None and hasattr(waveform, "shape") and int(waveform.shape[-1]) > 0


def _socket_sort_key(name) -> tuple[int, str]:
    text = str(name)
    try:
        return int(text.rsplit("_", 1)[-1]), text
    except (TypeError, ValueError):
        return 10**9, text


def _audio_duration(audio) -> float | None:
    return _contract_audio_duration(audio) if _has_audio(audio) else None


def _image_dimensions(image) -> tuple[int, int] | None:
    if not _has_image(image):
        return None
    return int(image.shape[2]), int(image.shape[1])


def _normalize_reference_video(video, source_fps, target_duration_seconds, audio=None):
    """Resample reference frames onto H3's fixed 24 FPS timeline.

    GetVideoComponents returns the source frame rate separately from the IMAGE
    tensor.  The native H3 Ref2VA node assumes 24 FPS, so passing a 30 FPS
    tensor unchanged changes the temporal meaning of the reference.  Nearest
    frame selection preserves the original duration while avoiding a costly
    interpolation pass before the VAE.
    """
    if not _has_image(video):
        raise ValueError("REF2VA_VIDEO_EMPTY: reference video frames are required")
    normalized, synced_audio, info = _contract_normalize_reference_video(
        video,
        source_fps,
        target_duration_seconds,
        audio,
    )
    return normalized, synced_audio, info


def _canonical_aspect_ratio(width: int, height: int) -> str:
    actual = max(1, width) / max(1, height)
    return min(H3_ASPECT_RATIOS, key=lambda name: abs(math.log(actual / H3_ASPECT_RATIOS[name])))


def _dimensions_for_ratio(base_width: int, base_height: int, ratio: float) -> tuple[int, int]:
    area = max(32 * 32, int(base_width) * int(base_height))
    width = max(32, round(math.sqrt(area * ratio) / 32) * 32)
    height = max(32, round(math.sqrt(area / ratio) / 32) * 32)
    return width, height


def _save_tensor_image(image, session_id: str, filename: str) -> Path:
    asset_dir = CACHE_ROOT / session_id / str(uuid4())
    asset_dir.mkdir(parents=True, exist_ok=False)
    path = asset_dir / filename
    pixels = image[0].detach().cpu().clamp(0, 1).mul(255).byte().numpy()
    Image.fromarray(pixels).save(path, format="PNG")
    return path


def _save_tensor_video(video, session_id: str, filename: str) -> Path:
    asset_dir = CACHE_ROOT / session_id / str(uuid4())
    asset_dir.mkdir(parents=True, exist_ok=False)
    path = asset_dir / filename
    frames = video.detach().cpu().clamp(0, 1).mul(255).byte().numpy()
    height, width = int(frames.shape[1]), int(frames.shape[2])
    with av.open(str(path), mode="w") as container:
        stream = container.add_stream("libx264", rate=24)
        stream.width = width
        stream.height = height
        stream.pix_fmt = "yuv420p"
        for pixels in frames:
            frame = av.VideoFrame.from_ndarray(pixels[..., :3], format="rgb24")
            for packet in stream.encode(frame):
                container.mux(packet)
        for packet in stream.encode():
            container.mux(packet)
    return path


def _save_audio(audio, session_id: str, filename: str) -> Path:
    asset_dir = CACHE_ROOT / session_id / str(uuid4())
    asset_dir.mkdir(parents=True, exist_ok=False)
    path = asset_dir / filename
    waveform = audio["waveform"][0].detach().cpu().float().clamp(-1, 1)
    samples = waveform.transpose(0, 1).mul(32767).round().numpy().astype(np.int16)
    channels = int(samples.shape[1]) if samples.ndim == 2 else 1
    with wave.open(str(path), "wb") as output:
        output.setnchannels(channels)
        output.setsampwidth(2)
        output.setframerate(int(audio["sample_rate"]))
        output.writeframes(samples.tobytes())
    return path


class H3ReferenceFrames:
    """Optional first/last frame sockets that return None when unconnected."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {},
            "optional": {
                "first_frame": ("IMAGE",),
                "last_frame": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("IMAGE", "IMAGE")
    RETURN_NAMES = ("first_frame", "last_frame")
    FUNCTION = "route"
    CATEGORY = "MiniMax H3/Prompt"

    def route(self, first_frame=None, last_frame=None):
        return (first_frame, last_frame)


class H3AspectRouter:
    """Resolve generation dimensions and the canonical H3 aspect label."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_width": ("INT", {"forceInput": True}),
                "base_height": ("INT", {"forceInput": True}),
                "aspect_source": (["output", "auto", "first_frame", "last_frame"], {"default": "output"}),
            },
            "optional": {
                "first_frame": ("IMAGE",),
                "last_frame": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("INT", "INT", "STRING")
    RETURN_NAMES = ("width", "height", "aspect_ratio")
    FUNCTION = "resolve"
    CATEGORY = "MiniMax H3/Prompt"

    def resolve(self, base_width: int, base_height: int, aspect_source: str, first_frame=None, last_frame=None):
        first_size = _image_dimensions(first_frame)
        last_size = _image_dimensions(last_frame)
        selected = None
        if aspect_source == "first_frame":
            selected = first_size
        elif aspect_source == "last_frame":
            selected = last_size
        elif aspect_source == "auto":
            selected = first_size or last_size

        if selected is None:
            width, height = int(base_width), int(base_height)
        else:
            width, height = _dimensions_for_ratio(base_width, base_height, selected[0] / selected[1])
        return (width, height, _canonical_aspect_ratio(width, height))


class H3RefPicture:
    """One optional picture item; duplicate the node to add another picture."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}, "optional": {"picture": ("IMAGE",)}}

    RETURN_TYPES = ("H3_REF_ITEM", "IMAGE")
    RETURN_NAMES = ("reference", "picture")
    FUNCTION = "route"
    CATEGORY = "MiniMax H3/Prompt"

    def route(self, picture=None):
        item = {"kind": "picture", "picture": picture} if _has_image(picture) else None
        return (item, picture)


class H3RefVideo:
    """One optional video item and its paired soundtrack; duplicate to add another video."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}, "optional": {"video": ("IMAGE",), "video_audio": ("AUDIO",)}}

    RETURN_TYPES = ("H3_REF_ITEM", "IMAGE", "AUDIO")
    RETURN_NAMES = ("reference", "video", "video_audio")
    FUNCTION = "route"
    CATEGORY = "MiniMax H3/Prompt"

    def route(self, video=None, video_audio=None):
        item = {"kind": "video", "video": video, "video_audio": video_audio} if _has_image(video) else None
        return (item, video, video_audio)


class H3RefAudio:
    """One optional standalone audio item; duplicate to add another audio reference."""

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {}, "optional": {"audio": ("AUDIO",)}}

    RETURN_TYPES = ("H3_REF_ITEM", "AUDIO")
    RETURN_NAMES = ("reference", "audio")
    FUNCTION = "route"
    CATEGORY = "MiniMax H3/Prompt"

    def route(self, audio=None):
        item = {"kind": "audio", "audio": audio} if _has_audio(audio) else None
        return (item, audio)


H3RefItemType = io.Custom("H3_REF_ITEM")
H3RefMediaType = io.Custom("H3_REF_MEDIA")


class H3RefCollector(io.ComfyNode):
    """Collect only connected reference items and assign dense Ref2VA tags."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="H3RefCollector",
            display_name="H3 Ref2VA Reference Collector",
            category="MiniMax H3/Prompt",
            inputs=[
                io.Autogrow.Input(
                    "items",
                    optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=H3RefItemType.Input("item"),
                        prefix="item_",
                        min=0,
                        max=15,
                    ),
                ),
            ],
            outputs=[H3RefMediaType.Output("references"), io.String.Output("tag_map")],
        )

    @classmethod
    def execute(cls, items=None) -> io.NodeOutput:
        connected = [item for item in (items or {}).values() if isinstance(item, dict)]
        pictures = [item["picture"] for item in connected if item.get("kind") == "picture" and _has_image(item.get("picture"))]
        videos = [item for item in connected if item.get("kind") == "video" and _has_image(item.get("video"))]
        audios = [item["audio"] for item in connected if item.get("kind") == "audio" and _has_audio(item.get("audio"))]

        lines = [f"<Picture {index}> = picture reference {index}" for index in range(1, len(pictures) + 1)]
        audio_index = 1
        for video_index, item in enumerate(videos, start=1):
            if _has_audio(item.get("video_audio")):
                lines.append(f"<Audio {audio_index}> = soundtrack paired with <Video {video_index}>")
                audio_index += 1
            lines.append(f"<Video {video_index}> = video reference {video_index}")
        for standalone_index, _audio in enumerate(audios, start=1):
            lines.append(f"<Audio {audio_index}> = standalone audio reference {standalone_index}")
            audio_index += 1

        references = {"pictures": pictures, "videos": videos, "audios": audios}
        tag_map = "\n".join(lines) if lines else "No reference media connected."
        return io.NodeOutput(references, tag_map)


class H3RefAspectRouter:
    """Resolve Ref2VA canvas from output settings, the picture, or the video."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "base_width": ("INT", {"forceInput": True}),
                "base_height": ("INT", {"forceInput": True}),
                "aspect_source": (["output", "auto", "picture", "video"], {"default": "output"}),
            },
            "optional": {
                "picture": ("IMAGE",),
                "video": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("INT", "INT", "STRING")
    RETURN_NAMES = ("width", "height", "aspect_ratio")
    FUNCTION = "resolve"
    CATEGORY = "MiniMax H3/Prompt"

    def resolve(self, base_width: int, base_height: int, aspect_source: str, picture=None, video=None):
        selected = None
        if aspect_source == "picture":
            selected = _image_dimensions(picture)
        elif aspect_source == "video":
            selected = _image_dimensions(video)
        elif aspect_source == "auto":
            selected = _image_dimensions(video) or _image_dimensions(picture)
        if selected is None:
            width, height = int(base_width), int(base_height)
        else:
            width, height = _dimensions_for_ratio(base_width, base_height, selected[0] / selected[1])
        return (width, height, _canonical_aspect_ratio(width, height))


class H3PromptStandardizer:
    """Convert a brief and optional keyframes into a MiniMax H3 prompt."""

    @classmethod
    def INPUT_TYPES(cls):
        ollama_models = _available_ollama_models()
        return {
            "required": {
                "creative_brief": ("STRING", {"forceInput": True}),
                "duration_seconds": ("FLOAT", {"forceInput": True}),
                "aspect_ratio": ("STRING", {"forceInput": True}),
                "ollama_model": (ollama_models, {"default": ollama_models[0]}),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 0xFFFFFFFFFFFFFFFF,
                        "control_after_generate": True,
                    },
                ),
                "unload_after": ("BOOLEAN", {"default": True}),
            },
            "optional": {
                "first_frame": ("IMAGE",),
                "last_frame": ("IMAGE",),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("H3 prompt",)
    FUNCTION = "standardize"
    CATEGORY = "MiniMax H3/Prompt"

    def standardize(
        self,
        creative_brief: str,
        duration_seconds: float,
        aspect_ratio: str,
        ollama_model: str,
        seed: int,
        unload_after: bool,
        first_frame=None,
        last_frame=None,
    ):
        brief = creative_brief.strip() if isinstance(creative_brief, str) else ""
        if not brief:
            raise ValueError("Creative brief is empty. Enter a plain-language video description first.")

        has_first = _has_image(first_frame)
        has_last = _has_image(last_frame)
        mode = "FL2VA" if has_first and has_last else "I2VA" if has_first else "L2VA" if has_last else "T2VA"
        session_id = str(uuid4())
        body = {
            "mode": mode,
            "creative_brief": brief,
            "duration_seconds": float(duration_seconds),
            "aspect_ratio": aspect_ratio,
            "session_id": session_id,
        }

        try:
            if has_first:
                first_path = _save_tensor_image(first_frame, session_id, "first_frame.png")
                STORE.add(session_id, mode, first_path.name, "image/png", first_path)
            if has_last:
                last_path = _save_tensor_image(last_frame, session_id, "last_frame.png")
                STORE.add(session_id, mode, last_path.name, "image/png", last_path)

            assembled = assemble_request(body)
            model = OLLAMA_BACKEND.probe_model(ollama_model.strip())
            runtime_plan = OLLAMA_BACKEND.preflight(
                model,
                assembled,
                context_profile="auto",
                kv_cache="auto",
                thinking=False,
            )
            OLLAMA_BACKEND.prepare_request()
            result = OLLAMA_BACKEND.generate(
                model,
                assembled,
                session_id,
                thinking=False,
                seed=int(seed),
                unload_after=bool(unload_after),
                context_profile="auto",
                kv_cache="auto",
                runtime_plan=runtime_plan,
            )
        except AssemblyError as error:
            raise ValueError(f"H3 prompt input error [{error.code}]: {error.message}") from error
        except MediaError as error:
            raise ValueError(f"H3 reference image error [{error.code}]: {error.message}") from error
        except ModelError as error:
            details = f" Details: {error.details}" if error.details else ""
            raise RuntimeError(f"H3 prompt generation failed [{error.code}]: {error.message}{details}") from error
        finally:
            STORE.clear(session_id)

        prompt = str(result.get("prompt") or "").strip()
        if not prompt:
            raise RuntimeError("H3 prompt generation returned an empty prompt.")
        return {
            "ui": {"text": [prompt]},
            "result": (prompt,),
            "request_capture": result.get("request_capture", {}),
        }


class H3Ref2VAPromptStandardizer:
    """Build a Reference-mode H3 prompt from the same compact media entry used by Ref2VA."""

    @classmethod
    def INPUT_TYPES(cls):
        ollama_models = _available_ollama_models()
        return {
            "required": {
                "creative_brief": ("STRING", {"forceInput": True}),
                "duration_seconds": ("FLOAT", {"forceInput": True}),
                "aspect_ratio": ("STRING", {"forceInput": True}),
                "references": ("H3_REF_MEDIA", {"forceInput": True}),
                "ollama_model": (ollama_models, {"default": ollama_models[0]}),
                "seed": (
                    "INT",
                    {
                        "default": 0,
                        "min": 0,
                        "max": 0xFFFFFFFFFFFFFFFF,
                        "control_after_generate": True,
                    },
                ),
                "unload_after": ("BOOLEAN", {"default": True}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("H3 prompt",)
    FUNCTION = "standardize"
    CATEGORY = "MiniMax H3/Prompt"

    def standardize(
        self,
        creative_brief: str,
        duration_seconds: float,
        aspect_ratio: str,
        references: dict,
        ollama_model: str,
        seed: int,
        unload_after: bool,
    ):
        brief = creative_brief.strip() if isinstance(creative_brief, str) else ""
        if not brief:
            raise ValueError("Creative brief is empty. Enter a plain-language video description first.")

        pictures = tuple(references.get("pictures", ()))
        videos = tuple(references.get("videos", ()))
        audios = tuple(references.get("audios", ()))
        session_id = str(uuid4())
        body = {
            "mode": "Reference",
            "creative_brief": brief,
            "duration_seconds": float(duration_seconds),
            "aspect_ratio": aspect_ratio,
            "session_id": session_id,
            "reference_role_lock": H3Ref2VAStandardizedConditioning._role_lock(references),
        }

        try:
            for index, picture in enumerate(pictures, start=1):
                if _has_image(picture):
                    path = _save_tensor_image(picture, session_id, f"picture_{index}.png")
                    STORE.add(session_id, "Reference", path.name, "image/png", path)

            for index, video_item in enumerate(videos, start=1):
                video = video_item.get("video")
                video_audio = video_item.get("video_audio")
                if _has_audio(video_audio):
                    path = _save_audio(video_audio, session_id, f"video_{index}_audio.wav")
                    STORE.add(session_id, "Reference", path.name, "audio/wav", path)
                if _has_image(video):
                    path = _save_tensor_video(video, session_id, f"video_{index}.mp4")
                    STORE.add(session_id, "Reference", path.name, "video/mp4", path)

            for index, audio in enumerate(audios, start=1):
                if _has_audio(audio):
                    path = _save_audio(audio, session_id, f"audio_{index}.wav")
                    STORE.add(session_id, "Reference", path.name, "audio/wav", path)

            assembled = assemble_request(body)
            model = OLLAMA_BACKEND.probe_model(ollama_model.strip())
            runtime_plan = OLLAMA_BACKEND.preflight(
                model,
                assembled,
                context_profile="auto",
                kv_cache="auto",
                thinking=False,
            )
            OLLAMA_BACKEND.prepare_request()
            result = OLLAMA_BACKEND.generate(
                model,
                assembled,
                session_id,
                thinking=False,
                seed=int(seed),
                unload_after=bool(unload_after),
                context_profile="auto",
                kv_cache="auto",
                runtime_plan=runtime_plan,
            )
        except AssemblyError as error:
            raise ValueError(f"H3 prompt input error [{error.code}]: {error.message}") from error
        except MediaError as error:
            raise ValueError(f"H3 reference media error [{error.code}]: {error.message}") from error
        except ModelError as error:
            details = f" Details: {error.details}" if error.details else ""
            raise RuntimeError(f"H3 prompt generation failed [{error.code}]: {error.message}{details}") from error
        finally:
            STORE.clear(session_id)

        prompt = str(result.get("prompt") or "").strip()
        if not prompt:
            raise RuntimeError("H3 prompt generation returned an empty prompt.")
        return {
            "ui": {"text": [prompt]},
            "result": (prompt,),
            "request_capture": result.get("request_capture", {}),
        }


def _validate_ref2va_prompt_contract(prompt: str, references: dict, duration_seconds: float) -> dict:
    """Check only deterministic facts; semantic quality remains model-dependent."""
    sections = [
        "subject_definitions:",
        "summary:",
        "retention_analysis:",
        "detailed_description:",
        "overall_soundscape:",
        "non_diegetic_music:",
    ]
    violations = []
    text = str(prompt or "").strip()
    positions = [text.find(section) for section in sections]
    if any(position < 0 for position in positions):
        violations.append({"type": "format", "detail": "missing required Ref2VA section"})
    elif positions != sorted(positions):
        violations.append({"type": "format", "detail": "Ref2VA sections are out of order"})
    if "```" in text or "<|im_" in text:
        violations.append({"type": "format", "detail": "model wrapper or markdown fence remains"})
    if "\\n" in text or "\\r" in text:
        violations.append({"type": "serialization", "detail": "literal newline escape remains"})
    if re.search(r"\b(?:TODO|TBD|PLACEHOLDER|<placeholder>)\b", text, flags=re.I):
        violations.append({"type": "placeholder", "detail": "placeholder text remains"})
    for match in re.finditer(r"\b(?:task|task_type|task type)\s*[:=]\s*([A-Za-z ]+)", text, flags=re.I):
        task = re.sub(r"\s+", " ", match.group(1).strip().lower())
        if task not in REF2VA_TASK_TYPES:
            violations.append({"type": "task_type", "detail": f"unsupported task type: {task}"})

    available = set()
    for index, _ in enumerate(references.get("pictures", ()), start=1):
        available.add(f"<Picture {index}>")
    for index, item in enumerate(references.get("videos", ()), start=1):
        available.add(f"<Video {index}>")
        if _has_audio(item.get("video_audio")):
            available.add(f"<Audio {sum(_has_audio(v.get('video_audio')) for v in references.get('videos', ())[:index])}>")
    audio_offset = sum(_has_audio(v.get("video_audio")) for v in references.get("videos", ()))
    for index, _ in enumerate(references.get("audios", ()), start=audio_offset + 1):
        available.add(f"<Audio {index}>")
    used = set(re.findall(r"<(?:Picture|Video|Audio)\s+\d+>", text))
    unknown = sorted(used - available)
    if unknown:
        violations.append({"type": "tag", "detail": "unknown reference tags: " + ", ".join(unknown)})

    timestamp_limit = float(duration_seconds) + 1e-6
    for match in re.finditer(r"(?<!\d)(\d{1,2}):(\d{2})(?:\.(\d{1,3}))?(?!\d)", text):
        # Aspect ratios such as 9:16 are part of the generation context, not
        # timestamps.  Do not reject a valid prompt merely because the ratio
        # matches the timestamp syntax used by the contract checker.
        ratio = f"{int(match.group(1))}:{match.group(2)}"
        if match.group(3) is None and ratio in H3_ASPECT_RATIOS:
            continue
        seconds = int(match.group(1)) * 60 + int(match.group(2))
        fraction = match.group(3) or "0"
        seconds += int(fraction.ljust(3, "0")) / 1000.0
        if seconds > timestamp_limit:
            violations.append({"type": "time_range", "detail": f"timestamp exceeds {duration_seconds:g}s: {match.group(0)}"})
            break
    return {"pass": not violations, "violations": violations}


def _validate_raw_ref2va_prompt(prompt: str, references: dict, duration_seconds: float) -> dict:
    """Apply deterministic reference/time checks without rewriting raw H3 text."""
    text = str(prompt or "").strip()
    if not text:
        return {"pass": False, "mode": "raw", "violations": [{"type": "empty", "detail": "Prompt is empty."}]}
    full = _validate_ref2va_prompt_contract(text, references, duration_seconds)
    allowed_types = {"tag", "time_range"}
    violations = [item for item in full["violations"] if item.get("type") in allowed_types]
    return {
        "pass": not violations,
        "mode": "raw",
        "violations": violations,
    }


class H3Ref2VAStandardizedConditioning(io.ComfyNode):
    """Native Ref2VA conditioning with optional prompt standardization and single-connect references."""

    @classmethod
    def define_schema(cls):
        models = _available_ollama_models()
        return io.Schema(
            node_id="H3Ref2VAStandardizedConditioning",
            display_name="MiniMax H3 Ref2VA + Prompt Standardizer",
            category="MiniMax H3/Prompt",
            inputs=[
                io.Clip.Input("clip"),
                io.Vae.Input("vae"),
                io.Vae.Input("audio_vae"),
                io.String.Input("creative_brief", multiline=True, dynamic_prompts=True),
                io.Int.Input("width", default=1344, min=32, max=16384, step=32),
                io.Int.Input("height", default=768, min=32, max=16384, step=32),
                io.Float.Input("duration_seconds", default=5.0, min=1.0, max=15.0, step=0.1),
                io.Boolean.Input("use_standardizer", default=True),
                io.Combo.Input("aspect_source", options=["output", "auto", "picture", "video"], default="auto"),
                io.Combo.Input("ollama_model", options=models, default=models[0]),
                io.Int.Input(
                    "prompt_seed",
                    default=0,
                    min=0,
                    max=0xFFFFFFFFFFFFFFFF,
                    control_after_generate=True,
                ),
                io.Boolean.Input("unload_after", default=True),
                io.Combo.Input("ref_image_size", options=["match", "max"], default="max"),
                io.Autogrow.Input(
                    "ref_images",
                    optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Image.Input("ref_image"), prefix="ref_image_", min=0, max=9
                    ),
                ),
                io.Autogrow.Input(
                    "ref_videos",
                    optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Image.Input("ref_video"), prefix="ref_video_", min=0, max=3
                    ),
                ),
                io.Autogrow.Input(
                    "ref_video_audios",
                    optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Audio.Input("ref_video_audio"), prefix="ref_video_audio_", min=0, max=3
                    ),
                ),
                io.Autogrow.Input(
                    "ref_video_fps",
                    optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Float.Input("ref_video_fps", default=24.0, min=1.0, max=120.0),
                        prefix="ref_video_fps_", min=0, max=3,
                    ),
                ),
                io.Autogrow.Input(
                    "ref_audios",
                    optional=True,
                    template=io.Autogrow.TemplatePrefix(
                        input=io.Audio.Input("ref_audio"), prefix="ref_audio_", min=0, max=3
                    ),
                ),
            ],
            outputs=[
                io.Conditioning.Output("positive"),
                io.Latent.Output("latent"),
                io.String.Output("final_prompt"),
                io.String.Output("tag_map"),
                io.String.Output("actual_size"),
                io.String.Output("standardized_prompt"),
                io.String.Output("reference_role_lock"),
                io.String.Output("standardizer_report"),
                io.String.Output("reference_manifest"),
                io.AnyType.Output("reference_bundle"),
                io.String.Output("generation_profile"),
                io.String.Output("fact_reports"),
                io.String.Output("validator_report"),
            ],
        )

    @staticmethod
    def _references(ref_images, ref_videos, ref_video_audios, ref_video_fps, ref_audios) -> dict:
        pictures = [
            values[name] for name in sorted(values, key=_socket_sort_key)
            if _has_image(values[name])
        ] if (values := (ref_images or {})) else []
        paired = ref_video_audios or {}
        fps_values = ref_video_fps or {}
        videos = []
        for name in sorted((ref_videos or {}), key=_socket_sort_key):
            video = ref_videos[name]
            if not _has_image(video):
                continue
            suffix = name.rsplit("_", 1)[-1]
            videos.append({
                "kind": "video",
                "name": name,
                "video": video,
                "video_audio": paired.get(f"ref_video_audio_{suffix}"),
                "fps": fps_values.get(f"ref_video_fps_{suffix}"),
            })
        audios = [
            values[name] for name in sorted(values, key=_socket_sort_key)
            if _has_audio(values[name])
        ] if (values := (ref_audios or {})) else []
        video_names = {item["name"] for item in videos}
        orphan_audio = sorted(
            name for name, audio in paired.items()
            if _has_audio(audio) and name.rsplit("_", 1)[-1] not in {
                video_name.rsplit("_", 1)[-1] for video_name in video_names
            }
        )
        return {"pictures": pictures, "videos": videos, "audios": audios, "orphan_audio": orphan_audio}

    @staticmethod
    def _tag_map(references: dict) -> str:
        pictures = references["pictures"]
        videos = references["videos"]
        audios = references["audios"]
        lines = [f"<Picture {index}> = picture reference {index}" for index in range(1, len(pictures) + 1)]
        audio_index = 1
        for video_index, item in enumerate(videos, start=1):
            if _has_audio(item.get("video_audio")):
                lines.append(f"<Audio {audio_index}> = soundtrack paired with <Video {video_index}>")
                audio_index += 1
            lines.append(f"<Video {video_index}> = video reference {video_index}")
        for standalone_index, _audio in enumerate(audios, start=1):
            lines.append(f"<Audio {audio_index}> = standalone audio reference {standalone_index}")
            audio_index += 1
        return "\n".join(lines) if lines else "No reference media connected."

    @staticmethod
    def _role_lock(references: dict) -> str:
        """Expose the non-negotiable source boundaries next to the prompt."""
        lines = [
            "Reference Fact / Role Lock (routing policy; user brief remains authoritative):",
            "- Source tags and reusable <Subject N> tags are different concepts; never renumber or merge them.",
        ]
        for index, _picture in enumerate(references["pictures"], start=1):
            lines.append(
                f"- <Picture {index}> ALLOWED: only roles explicitly assigned to this tag by the user's brief; "
                "MUST_NOT_TRANSFER: any unrequested observed fact or role."
            )
        audio_index = 1
        for index, item in enumerate(references["videos"], start=1):
            lines.append(
                f"- <Video {index}> ALLOWED: only roles explicitly assigned to this tag by the user's brief; "
                "MUST_NOT_TRANSFER: any unrequested observed fact or role."
            )
            if _has_audio(item.get("video_audio")):
                lines.append(
                    f"- <Audio {audio_index}> (paired with <Video {index}>) ALLOWED: only the user's explicitly declared audio role; "
                    "MUST_NOT_TRANSFER: invented speech, music, voice, or sound content."
                )
                audio_index += 1
        for index, _audio in enumerate(references["audios"], start=audio_index):
            lines.append(
                f"- <Audio {index}> ALLOWED: only the user's explicitly declared audio role; "
                "MUST_NOT_TRANSFER: invented audible content."
            )
        return "\n".join(lines)

    @staticmethod
    def _native_inputs(references: dict) -> tuple[dict, dict, dict, dict]:
        """Rebuild dense native dictionaries so sparse autogrow sockets cannot mispair tags."""
        images = {f"ref_image_{index}": image for index, image in enumerate(references["pictures"])}
        videos = {}
        paired_audio = {}
        for index, item in enumerate(references["videos"]):
            videos[f"ref_video_{index}"] = item["video"]
            if _has_audio(item.get("video_audio")):
                paired_audio[f"ref_video_audio_{index}"] = item["video_audio"]
        audios = {f"ref_audio_{index}": audio for index, audio in enumerate(references["audios"])}
        return images, videos, paired_audio, audios

    @classmethod
    def _execute_mode(
        cls,
        *,
        prompt_mode: str,
        standardize: bool,
        clip,
        vae,
        audio_vae,
        creative_brief,
        width,
        height,
        duration_seconds,
        aspect_source,
        ollama_model,
        prompt_seed,
        unload_after,
        ref_image_size,
        ref_images=None,
        ref_videos=None,
        ref_video_audios=None,
        ref_video_fps=None,
        ref_audios=None,
    ) -> io.NodeOutput:
        duration_seconds = float(duration_seconds)
        if not REF2VA_MIN_DURATION <= duration_seconds <= REF2VA_MAX_DURATION:
            raise ValueError(
                f"Ref2VA duration must be between {REF2VA_MIN_DURATION:g} and "
                f"{REF2VA_MAX_DURATION:g} seconds."
            )
        references = cls._references(ref_images, ref_videos, ref_video_audios, ref_video_fps, ref_audios)
        if references["orphan_audio"]:
            raise ValueError(
                "REF2VA_ORPHAN_PAIRED_AUDIO: " + ", ".join(references["orphan_audio"])
            )

        normalized_count = 0
        source_fps = []
        normalization = []
        for item in references["videos"]:
            if item.get("fps") is None:
                raise ValueError(
                    f"REF2VA_SOURCE_FPS_REQUIRED: {item['name']} must be connected to "
                    "the source FPS output of GetVideoComponents."
                )
            normalized, synced_audio, info = _normalize_reference_video(
                item["video"], item["fps"], duration_seconds, item.get("video_audio")
            )
            item["video"] = normalized
            item["video_audio"] = synced_audio
            item["normalized"] = info
            source_fps.append(info["source_fps"])
            normalized_count += int(
                info["source_frame_count"] != info["normalized_frame_count"]
                or abs(info["source_fps"] - REF2VA_FPS) > 1e-3
            )
            normalization.append(info)

        first_picture = references["pictures"][0] if references["pictures"] else None
        first_video = references["videos"][0]["video"] if references["videos"] else None
        selected = None
        aspect_source_used = "output"
        if aspect_source == "picture":
            selected = _image_dimensions(first_picture)
            aspect_source_used = "picture" if selected is not None else "output"
        elif aspect_source == "video":
            selected = _image_dimensions(first_video)
            aspect_source_used = "video" if selected is not None else "output"
        elif aspect_source == "auto":
            selected = _image_dimensions(first_video)
            if selected is not None:
                aspect_source_used = "video"
            else:
                selected = _image_dimensions(first_picture)
                if selected is not None:
                    aspect_source_used = "picture"
        if selected is not None:
            width, height = _dimensions_for_ratio(width, height, selected[0] / selected[1])
        width, height = int(width), int(height)
        aspect_ratio = _canonical_aspect_ratio(width, height)

        prompt = str(creative_brief or "").strip()
        standardized_prompt = ""
        standardizer_request_captures = []
        if standardize:
            original_brief = prompt
            generated = H3Ref2VAPromptStandardizer().standardize(
                prompt,
                duration_seconds,
                aspect_ratio,
                references,
                ollama_model,
                int(prompt_seed),
                bool(unload_after),
            )
            prompt = generated["result"][0]
            standardizer_request_captures.append(generated.get("request_capture", {}))
            standardized_prompt = prompt
            prompt_validation = _validate_ref2va_prompt_contract(prompt, references, duration_seconds)
            if not prompt_validation["pass"]:
                repair_brief = (
                    f"{original_brief}\n\n"
                    "REPAIR THE PREVIOUS OUTPUT. Return only a complete valid MiniMax H3 Ref2VA prompt. "
                    f"Fix these deterministic violations: {json.dumps(prompt_validation['violations'], ensure_ascii=False)}"
                )
                repaired = H3Ref2VAPromptStandardizer().standardize(
                    repair_brief,
                    duration_seconds,
                    aspect_ratio,
                    references,
                    ollama_model,
                    int(prompt_seed),
                    bool(unload_after),
                )
                prompt = repaired["result"][0]
                standardizer_request_captures.append(repaired.get("request_capture", {}))
                standardized_prompt = prompt
                prompt_validation = _validate_ref2va_prompt_contract(prompt, references, duration_seconds)
                if not prompt_validation["pass"]:
                    raise ValueError(
                        "REF2VA_PROMPT_CONTRACT_FAILED_AFTER_REPAIR: "
                        + json.dumps(prompt_validation, ensure_ascii=False)
                    )
        else:
            prompt_validation = _validate_raw_ref2va_prompt(prompt, references, duration_seconds)
            if not prompt_validation["pass"]:
                raise ValueError(
                    "REF2VA_RAW_PROMPT_CONTRACT_FAILED: "
                    + json.dumps(prompt_validation, ensure_ascii=False)
                )

        length = _contract_h3_length(duration_seconds)
        from comfy_extras.nodes_minimax_h3 import MiniMaxH3ReferenceToVideo

        native_images, native_videos, native_paired_audio, native_audios = cls._native_inputs(references)
        native = MiniMaxH3ReferenceToVideo.execute(
            clip,
            vae,
            audio_vae,
            prompt,
            width,
            height,
            length,
            ref_image_size,
            native_images,
            native_videos,
            native_paired_audio,
            native_audios,
        )
        manifest = []
        for index, _picture in enumerate(references["pictures"], start=1):
            manifest.append({"tag": f"<Picture {index}>", "kind": "image"})
        audio_index = 1
        for index, item in enumerate(references["videos"], start=1):
            paired_tag = None
            if _has_audio(item.get("video_audio")):
                paired_tag = f"<Audio {audio_index}>"
                audio_index += 1
                manifest.append({
                    "tag": paired_tag,
                    "kind": "paired_audio",
                    "paired_video_tag": f"<Video {index}>",
                    "duration_seconds": _audio_duration(item["video_audio"]),
                })
            info = item["normalized"]
            manifest.append({
                "tag": f"<Video {index}>",
                "kind": "video",
                "normalized_fps": REF2VA_FPS,
                "frame_count": info["normalized_frame_count"],
                "duration_seconds": info["normalized_duration_seconds"],
                "normalize_proof": info["proof"],
            })
        for index, audio in enumerate(references["audios"], start=audio_index):
            manifest.append({
                "tag": f"<Audio {index}>",
                "kind": "standalone_audio",
                "duration_seconds": _audio_duration(audio),
            })
        bundle = {
            "prompt_mode": prompt_mode,
            "ref_images": native_images,
            "ref_videos": native_videos,
            "ref_video_audios": native_paired_audio,
            "ref_audios": native_audios,
            "width": width,
            "height": height,
            "requested_duration": duration_seconds,
            "effective_duration": length / REF2VA_FPS,
            "length": length,
            "aspect_source": aspect_source,
            "aspect_source_used": aspect_source_used,
            "ref_image_size": str(ref_image_size),
            "manifest": manifest,
            "normalization": normalization,
            "tag_map": cls._tag_map(references),
            "standardizer_request_capture": (
                standardizer_request_captures if standardize else {"status": "not_used"}
            ),
        }
        role_map = cls._role_lock(references) if standardize else "[未使用：原始 Prompt 模式]"
        fact_reports = "[未使用：Ollama 模式不执行隔离事实分析]" if prompt_mode == "ollama" else "[未使用]"
        report = (
            f"prompt_mode={prompt_mode}; standardization={'enabled' if standardize else 'bypassed'}; "
            f"references=Pictures:{len(references['pictures'])}, Videos:{len(references['videos'])}, "
            f"PairedAudio:{sum(_has_audio(item.get('video_audio')) for item in references['videos'])}, "
            f"StandaloneAudio:{len(references['audios'])}; source_fps="
            f"{', '.join(f'{fps:g}' for fps in source_fps) if source_fps else 'none'}; "
            f"h3_fps={REF2VA_FPS:g}; normalized_videos={normalized_count}; "
            "sparse_socket_remap=dense; prompt_contract=pass."
        )
        return io.NodeOutput(
            native.result[0],
            native.result[1],
            prompt,
            cls._tag_map(references),
            f"{width} x {height} ({aspect_ratio})",
            standardized_prompt,
            role_map,
            report,
            json.dumps(manifest, ensure_ascii=False, indent=2),
            bundle,
            json.dumps({
                "prompt_mode": prompt_mode,
                "profile": "native_ref2va",
                "standardizer_request_capture_count": len(standardizer_request_captures),
            }, ensure_ascii=False),
            fact_reports,
            json.dumps(prompt_validation, ensure_ascii=False, indent=2),
        )

    @classmethod
    def execute(
        cls,
        clip,
        vae,
        audio_vae,
        creative_brief,
        width,
        height,
        duration_seconds,
        use_standardizer,
        aspect_source,
        ollama_model,
        prompt_seed,
        unload_after,
        ref_image_size,
        ref_images=None,
        ref_videos=None,
        ref_video_audios=None,
        ref_video_fps=None,
        ref_audios=None,
    ) -> io.NodeOutput:
        return cls._execute_mode(
            prompt_mode="ollama" if bool(use_standardizer) else "raw",
            standardize=bool(use_standardizer),
            clip=clip,
            vae=vae,
            audio_vae=audio_vae,
            creative_brief=creative_brief,
            width=width,
            height=height,
            duration_seconds=duration_seconds,
            aspect_source=aspect_source,
            ollama_model=ollama_model,
            prompt_seed=prompt_seed,
            unload_after=unload_after,
            ref_image_size=ref_image_size,
            ref_images=ref_images,
            ref_videos=ref_videos,
            ref_video_audios=ref_video_audios,
            ref_video_fps=ref_video_fps,
            ref_audios=ref_audios,
        )


def _fixed_ref2va_schema(node_id: str, display_name: str, ollama: bool) -> io.Schema:
    models = _available_ollama_models()
    inputs = [
        io.Clip.Input("clip"),
        io.Vae.Input("vae"),
        io.Vae.Input("audio_vae"),
        io.String.Input("creative_brief", multiline=True, dynamic_prompts=True),
        io.Int.Input("width", default=1344, min=32, max=16384, step=32),
        io.Int.Input("height", default=768, min=32, max=16384, step=32),
        io.Float.Input("duration_seconds", default=5.0, min=REF2VA_MIN_DURATION, max=REF2VA_MAX_DURATION, step=0.1),
    ]
    if ollama:
        inputs.extend([
            io.Combo.Input("ollama_model", options=models, default=models[0]),
            io.Int.Input("prompt_seed", default=0, min=0, max=0xFFFFFFFFFFFFFFFF, control_after_generate=True),
            io.Boolean.Input("unload_after", default=True),
        ])
    inputs.extend([
        io.Combo.Input("aspect_source", options=["output", "auto", "picture", "video"], default="auto"),
        io.Combo.Input("ref_image_size", options=["match", "max"], default="max"),
        io.Autogrow.Input(
            "ref_images", optional=True,
            template=io.Autogrow.TemplatePrefix(input=io.Image.Input("ref_image"), prefix="ref_image_", min=0, max=9),
        ),
        io.Autogrow.Input(
            "ref_videos", optional=True,
            template=io.Autogrow.TemplatePrefix(input=io.Image.Input("ref_video"), prefix="ref_video_", min=0, max=3),
        ),
        io.Autogrow.Input(
            "ref_video_audios", optional=True,
            template=io.Autogrow.TemplatePrefix(input=io.Audio.Input("ref_video_audio"), prefix="ref_video_audio_", min=0, max=3),
        ),
        io.Autogrow.Input(
            "ref_video_fps", optional=True,
            template=io.Autogrow.TemplatePrefix(
                input=io.Float.Input("ref_video_fps", min=1.0, max=120.0),
                prefix="ref_video_fps_", min=0, max=3,
            ),
        ),
        io.Autogrow.Input(
            "ref_audios", optional=True,
            template=io.Autogrow.TemplatePrefix(input=io.Audio.Input("ref_audio"), prefix="ref_audio_", min=0, max=3),
        ),
    ])
    return io.Schema(
        node_id=node_id,
        display_name=display_name,
        category="MiniMax H3/Ref2VA",
        inputs=inputs,
        outputs=[
            io.Conditioning.Output("positive"), io.Latent.Output("latent"),
            io.String.Output("final_prompt"), io.String.Output("tag_map"),
            io.String.Output("actual_size"), io.String.Output("standardized_prompt"),
            io.String.Output("reference_role_lock"), io.String.Output("standardizer_report"),
            io.String.Output("reference_manifest"), io.AnyType.Output("reference_bundle"),
            io.String.Output("generation_profile"), io.String.Output("fact_reports"),
            io.String.Output("validator_report"),
        ],
    )


class H3Ref2VARawConditioning(H3Ref2VAStandardizedConditioning):
    """Fixed raw-Prompt entry; no standardizer toggle or model dependency."""

    @classmethod
    def define_schema(cls):
        return _fixed_ref2va_schema(
            "H3Ref2VARawConditioning",
            "H3 Ref2VA — Raw Prompt",
            False,
        )

    @classmethod
    def execute(
        cls, clip, vae, audio_vae, creative_brief, width, height, duration_seconds,
        aspect_source, ref_image_size, ref_images=None, ref_videos=None,
        ref_video_audios=None, ref_video_fps=None, ref_audios=None,
    ):
        return cls._execute_mode(
            prompt_mode="raw", standardize=False, clip=clip, vae=vae, audio_vae=audio_vae,
            creative_brief=creative_brief, width=width, height=height,
            duration_seconds=duration_seconds, aspect_source=aspect_source,
            ollama_model="", prompt_seed=0, unload_after=True, ref_image_size=ref_image_size,
            ref_images=ref_images, ref_videos=ref_videos, ref_video_audios=ref_video_audios,
            ref_video_fps=ref_video_fps, ref_audios=ref_audios,
        )


class H3Ref2VAOllamaConditioning(H3Ref2VAStandardizedConditioning):
    """Fixed Ollama entry; standardization is always enabled."""

    @classmethod
    def define_schema(cls):
        return _fixed_ref2va_schema(
            "H3Ref2VAOllamaConditioning",
            "H3 Ref2VA — Ollama Prompt Standardization",
            True,
        )

    @classmethod
    def execute(
        cls, clip, vae, audio_vae, creative_brief, width, height, duration_seconds,
        ollama_model, prompt_seed, unload_after, aspect_source, ref_image_size,
        ref_images=None, ref_videos=None, ref_video_audios=None, ref_video_fps=None,
        ref_audios=None,
    ):
        return cls._execute_mode(
            prompt_mode="ollama", standardize=True, clip=clip, vae=vae, audio_vae=audio_vae,
            creative_brief=creative_brief, width=width, height=height,
            duration_seconds=duration_seconds, aspect_source=aspect_source,
            ollama_model=ollama_model, prompt_seed=prompt_seed, unload_after=unload_after,
            ref_image_size=ref_image_size, ref_images=ref_images, ref_videos=ref_videos,
            ref_video_audios=ref_video_audios, ref_video_fps=ref_video_fps, ref_audios=ref_audios,
        )


def _normalize_prompt_text(text) -> str:
    value = "" if text is None else str(text)
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = value.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\r", "\n")
    return value.strip()


PERSISTENCE_NODES = {
    180: "raw_user_request",
    181: "standardized_prompt",
    182: "final_prompt_used",
    184: "reference_tag_map",
    185: "reference_fact_role_lock",
    186: "actual_output_size",
}


def _mutate_workflow_for_persistence(workflow, payload):
    if not isinstance(workflow, dict):
        return workflow
    for node in workflow.get("nodes", []):
        try:
            key = PERSISTENCE_NODES.get(int(node.get("id")))
        except (TypeError, ValueError):
            key = None
        if key:
            value = payload.get(key, "")
            if key == "standardized_prompt" and not value:
                value = "[标准化已跳过；本次直接使用用户输入。]"
            node["widgets_values"] = [_normalize_prompt_text(value)]
    return workflow


def _persisted_metadata(extra_pnginfo, prompt, payload):
    metadata = copy.deepcopy(extra_pnginfo) if isinstance(extra_pnginfo, dict) else {}
    workflow_blob = metadata.get("workflow")
    if isinstance(workflow_blob, dict):
        metadata["workflow"] = _mutate_workflow_for_persistence(copy.deepcopy(workflow_blob), payload)
    elif isinstance(workflow_blob, str):
        try:
            parsed = json.loads(workflow_blob)
            if isinstance(parsed, dict):
                metadata["workflow"] = _mutate_workflow_for_persistence(parsed, payload)
        except Exception:
            pass
    metadata["h3_ref2va_ollama_prompt_writer"] = copy.deepcopy(payload)
    metadata["h3_ref2va_run"] = copy.deepcopy(payload)
    if prompt is not None:
        metadata["prompt"] = prompt
    return metadata


class H3Ref2VARunMetadataPackOllama(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="H3Ref2VARunMetadataPackOllama",
            display_name="H3 Ref2VA Ollama Run Metadata Pack",
            category="MiniMax H3/Prompt",
            inputs=[
                io.String.Input("raw_user_request", multiline=True, force_input=True),
                io.String.Input("standardized_prompt", multiline=True, force_input=True),
                io.String.Input("final_prompt_used", multiline=True, force_input=True),
                io.String.Input("reference_tag_map", multiline=True, force_input=True),
                io.String.Input("reference_fact_role_lock", multiline=True, force_input=True),
                io.String.Input("actual_output_size", force_input=True),
                io.String.Input("writer_report", multiline=True, force_input=True),
            ],
            outputs=[io.AnyType.Output(display_name="run_metadata")],
        )

    @classmethod
    def execute(cls, raw_user_request, standardized_prompt, final_prompt_used,
                reference_tag_map, reference_fact_role_lock, actual_output_size, writer_report):
        return io.NodeOutput({
            "raw_user_request": _normalize_prompt_text(raw_user_request),
            "standardized_prompt": _normalize_prompt_text(standardized_prompt),
            "final_prompt_used": _normalize_prompt_text(final_prompt_used),
            "standardization_enabled": bool(_normalize_prompt_text(standardized_prompt)),
            "reference_tag_map": _normalize_prompt_text(reference_tag_map),
            "reference_fact_role_lock": _normalize_prompt_text(reference_fact_role_lock),
            "actual_output_size": _normalize_prompt_text(actual_output_size),
            "writer_report": _normalize_prompt_text(writer_report),
            "mode": "Ref2VA",
            "writer_version": "ollama-ref2va-v2",
        })


class H3Ref2VASaveVideoWithMetadataOllama(io.ComfyNode):
    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="H3Ref2VASaveVideoWithMetadataOllama",
            display_name="H3 Ref2VA Save Video + Ollama Prompt Metadata",
            category="MiniMax H3/Prompt",
            is_output_node=True,
            inputs=[
                io.Video.Input("video"),
                io.AnyType.Input("run_metadata"),
                io.String.Input("filename_prefix", default="videos/H3_Ref2VA_Ollama-%year%-%month%-%day%"),
                io.Combo.Input("format", options=["auto", "mp4", "mkv", "webm"], default="auto"),
                io.Combo.Input("codec", options=["auto", "h264", "av1"], default="auto"),
            ],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
            outputs=[io.Video.Output()],
        )

    @classmethod
    def execute(cls, video, run_metadata, filename_prefix, format, codec):
        payload = copy.deepcopy(run_metadata if isinstance(run_metadata, dict) else {})
        for key in ("raw_user_request", "standardized_prompt", "final_prompt_used",
                    "reference_tag_map", "reference_fact_role_lock", "actual_output_size", "writer_report"):
            payload[key] = _normalize_prompt_text(payload.get(key, ""))
        format_name = str(format or "auto").casefold()
        codec_name = str(codec or "auto").casefold()
        if format_name not in {"auto", "mp4", "mkv", "webm"}:
            raise ValueError(f"Unsupported video format: {format}")
        if codec_name not in {"auto", "h264", "av1"}:
            raise ValueError(f"Unsupported video codec: {codec}")
        if format_name == "webm" and codec_name == "h264":
            raise ValueError("WebM does not support H.264 in this saver.")
        if format_name == "auto":
            format_name = "webm" if codec_name == "av1" else "mp4"
        width, height = video.get_dimensions()
        full_output_folder, filename, counter, subfolder, _ = folder_paths.get_save_image_path(
            filename_prefix, folder_paths.get_output_directory(), width, height,
        )
        metadata = None
        if not args.disable_metadata:
            metadata = _persisted_metadata(cls.hidden.extra_pnginfo, cls.hidden.prompt, payload) or None
        file = f"{filename}_{counter:05}_.{Types.VideoContainer.get_extension(format_name)}"
        video.save_to(os.path.join(full_output_folder, file), format=Types.VideoContainer(format_name),
                      codec=Types.VideoCodec(codec_name), metadata=metadata)
        return io.NodeOutput(video, ui=ui.PreviewVideo([ui.SavedResult(file, subfolder, io.FolderType.output)]))


class H3Ref2VAUnifiedMetadataPack(io.ComfyNode):
    """Pack the same observable run contract for raw, Ollama, and Qwen3.5 modes."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="H3Ref2VAUnifiedMetadataPack",
            display_name="H3 Ref2VA Unified Run Metadata",
            category="MiniMax H3/Ref2VA",
            inputs=[
                io.String.Input("raw_user_request", multiline=True, force_input=True),
                io.String.Input("standardized_prompt", multiline=True, force_input=True),
                io.String.Input("final_prompt_used", multiline=True, force_input=True),
                io.String.Input("reference_tag_map", multiline=True, force_input=True),
                io.String.Input("role_map", multiline=True, force_input=True),
                io.String.Input("fact_reports", multiline=True, force_input=True),
                io.String.Input("validator_report", multiline=True, force_input=True),
                io.String.Input("actual_output_size", force_input=True),
                io.String.Input("writer_report", multiline=True, force_input=True),
                io.String.Input("reference_manifest", multiline=True),
                io.String.Input("generation_profile", multiline=True, default=""),
                io.AnyType.Input("reference_bundle"),
            ],
            outputs=[io.AnyType.Output(display_name="run_metadata")],
        )

    @classmethod
    def execute(
        cls, raw_user_request, standardized_prompt, final_prompt_used,
        reference_tag_map, role_map, fact_reports, validator_report,
        actual_output_size, writer_report, reference_manifest, generation_profile,
        reference_bundle,
    ):
        mode = "raw"
        try:
            profile = json.loads(str(generation_profile or "{}"))
            mode = str(profile.get("prompt_mode") or mode)
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
        fact_text = _normalize_prompt_text(fact_reports)
        if mode == "raw" and fact_text and not fact_text.startswith("[未使用"):
            mode = "qwen35"
        elif mode == "raw" and _normalize_prompt_text(standardized_prompt):
            mode = "ollama"
        bundle = reference_bundle if isinstance(reference_bundle, dict) else {}
        request_capture = copy.deepcopy(bundle.get("standardizer_request_capture", {"status": "not_used"}))
        if mode == "qwen35" and request_capture == {"status": "not_used"}:
            try:
                writer_payload = json.loads(str(writer_report or "{}"))
                if isinstance(writer_payload, dict) and writer_payload.get("request_capture") is not None:
                    request_capture = {
                        "pipeline": "qwen35_reference_standardization",
                        "calls": copy.deepcopy(writer_payload["request_capture"]),
                    }
            except (TypeError, ValueError, json.JSONDecodeError):
                pass
        payload = {
            "prompt_mode": mode,
            "raw_user_request": _normalize_prompt_text(raw_user_request),
            "standardized_prompt": _normalize_prompt_text(standardized_prompt),
            "final_prompt_used": _normalize_prompt_text(final_prompt_used),
            "reference_tag_map": _normalize_prompt_text(reference_tag_map),
            "role_map": _normalize_prompt_text(role_map),
            "fact_reports": _normalize_prompt_text(fact_reports),
            "validator_report": _normalize_prompt_text(validator_report),
            "actual_output_size": _normalize_prompt_text(actual_output_size),
            "writer_report": _normalize_prompt_text(writer_report),
            "reference_manifest": _normalize_prompt_text(reference_manifest) or json.dumps(
                (reference_bundle or {}).get("manifest", []) if isinstance(reference_bundle, dict) else [],
                ensure_ascii=False,
                indent=2,
            ),
            "generation_profile": _normalize_prompt_text(generation_profile),
            "reference_manifest_data": copy.deepcopy(bundle.get("manifest", [])),
            "reference_normalization": copy.deepcopy(bundle.get("normalization", [])),
            "standardizer_request_capture": request_capture,
            "requested_duration": bundle.get("requested_duration"),
            "effective_duration": bundle.get("effective_duration"),
            "width": bundle.get("width"),
            "height": bundle.get("height"),
            "length": bundle.get("length"),
            "aspect_source": bundle.get("aspect_source"),
            "aspect_source_used": bundle.get("aspect_source_used"),
            "ref_image_size": bundle.get("ref_image_size"),
            "mode": "Ref2VA",
            "writer_version": "ref2va-unified-v1",
        }
        return io.NodeOutput(payload)


class H3Ref2VASaveVideoWithMetadata(H3Ref2VASaveVideoWithMetadataOllama):
    """Generic saver used by all final workflows."""

    @classmethod
    def define_schema(cls):
        return io.Schema(
            node_id="H3Ref2VASaveVideoWithMetadata",
            display_name="H3 Ref2VA Save Video + Unified Metadata",
            category="MiniMax H3/Ref2VA",
            is_output_node=True,
            inputs=[
                io.Video.Input("video"), io.AnyType.Input("run_metadata"),
                io.String.Input("filename_prefix", default="videos/H3_Ref2VA-%year%-%month%-%day%"),
                io.Combo.Input("format", options=["auto", "mp4", "mkv", "webm"], default="auto"),
                io.Combo.Input("codec", options=["auto", "h264", "av1"], default="auto"),
            ],
            hidden=[io.Hidden.prompt, io.Hidden.extra_pnginfo],
            outputs=[io.Video.Output()],
        )


NODE_CLASS_MAPPINGS = {
    "H3ReferenceFrames": H3ReferenceFrames,
    "H3AspectRouter": H3AspectRouter,
    "H3PromptStandardizer": H3PromptStandardizer,
    "H3Ref2VAStandardizedConditioning": H3Ref2VAStandardizedConditioning,
    "H3Ref2VARawConditioning": H3Ref2VARawConditioning,
    "H3Ref2VAOllamaConditioning": H3Ref2VAOllamaConditioning,
    "H3Ref2VARunMetadataPackOllama": H3Ref2VARunMetadataPackOllama,
    "H3Ref2VASaveVideoWithMetadataOllama": H3Ref2VASaveVideoWithMetadataOllama,
    "H3Ref2VAUnifiedMetadataPack": H3Ref2VAUnifiedMetadataPack,
    "H3Ref2VASaveVideoWithMetadata": H3Ref2VASaveVideoWithMetadata,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "H3ReferenceFrames": "H3 Reference Frames (Optional)",
    "H3AspectRouter": "H3 Aspect Source",
    "H3PromptStandardizer": "MiniMax H3 Prompt Standardizer",
    "H3Ref2VAStandardizedConditioning": "MiniMax H3 Ref2VA + Prompt Standardizer",
    "H3Ref2VARawConditioning": "H3 Ref2VA — Raw Prompt",
    "H3Ref2VAOllamaConditioning": "H3 Ref2VA — Ollama Prompt Standardization",
    "H3Ref2VARunMetadataPackOllama": "H3 Ref2VA Ollama Run Metadata Pack",
    "H3Ref2VASaveVideoWithMetadataOllama": "H3 Ref2VA Save Video + Ollama Prompt Metadata",
    "H3Ref2VAUnifiedMetadataPack": "H3 Ref2VA Unified Run Metadata",
    "H3Ref2VASaveVideoWithMetadata": "H3 Ref2VA Save Video + Unified Metadata",
}
