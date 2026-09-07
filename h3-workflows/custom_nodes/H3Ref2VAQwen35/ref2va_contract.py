"""Shared, model-independent Ref2VA media and prompt contract helpers.

This module intentionally has no ComfyUI node dependencies.  The Ollama and
Qwen3.5 integrations use it so that prompt-only tests and native H3 execution
operate on the same normalized reference media.
"""

from __future__ import annotations

import math
from typing import Any


REF2VA_FPS = 24.0
REF2VA_MIN_DURATION = 2.0
REF2VA_MAX_DURATION = 15.0
REF2VA_NORMALIZE_PROOF = "REF2VA_NORMALIZED_V1"


def h3_length(seconds: float) -> int:
    duration = float(seconds)
    if not math.isfinite(duration) or not REF2VA_MIN_DURATION <= duration <= REF2VA_MAX_DURATION:
        raise ValueError(
            f"Ref2VA duration must be between {REF2VA_MIN_DURATION:g} and "
            f"{REF2VA_MAX_DURATION:g} seconds."
        )
    frames = max(5, round(duration * REF2VA_FPS))
    return int(frames + (5 - frames % 17) % 17)


def align_ref_count_down(frame_count: int) -> int:
    count = int(frame_count)
    while count >= 5 and count % 17 != 5:
        count -= 1
    return count


def audio_duration(audio: dict[str, Any] | None) -> float | None:
    if not isinstance(audio, dict):
        return None
    waveform = audio.get("waveform")
    sample_rate = audio.get("sample_rate")
    try:
        if waveform is None or int(sample_rate) <= 0:
            return None
        return float(waveform.shape[-1]) / float(sample_rate)
    except (AttributeError, TypeError, ValueError, ZeroDivisionError):
        return None


def _sync_audio(audio: dict[str, Any] | None, duration: float):
    if audio is None:
        return None, "no paired audio", None
    waveform = audio.get("waveform") if isinstance(audio, dict) else None
    try:
        import torch

        sample_rate = int(audio["sample_rate"])
        if sample_rate <= 0:
            raise ValueError("paired audio sample rate must be positive")
        target_samples = max(1, int(round(float(duration) * sample_rate)))
        current_samples = int(waveform.shape[-1])
        if current_samples >= target_samples:
            normalized_waveform = waveform[..., :target_samples].clone()
            report = f"audio trimmed {current_samples}->{target_samples} samples @ {sample_rate}Hz"
        else:
            padding = torch.zeros(
                *waveform.shape[:-1],
                target_samples - current_samples,
                dtype=waveform.dtype,
                device=waveform.device,
            )
            normalized_waveform = torch.cat([waveform, padding], dim=-1)
            report = f"audio padded with silence {current_samples}->{target_samples} samples @ {sample_rate}Hz"
        result = dict(audio)
        result["waveform"] = normalized_waveform
        result["sample_rate"] = sample_rate
        return result, report, target_samples / sample_rate
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise ValueError(f"Invalid paired audio: {error}") from error


def normalize_reference_video(images, source_fps, target_duration_seconds: float, audio=None):
    """Normalize one reference video to the exact H3 reference contract.

    The source timeline is sampled at 24fps, capped by the requested output
    duration, and aligned down to ``17k+5`` frames.  A source shorter than the
    requested duration keeps its real duration; video frames are never padded.
    Paired audio is trimmed or padded to the resulting normalized duration.
    """

    try:
        fps = float(source_fps)
    except (TypeError, ValueError) as error:
        raise ValueError("REF2VA_SOURCE_FPS_REQUIRED: source FPS must be provided") from error
    if not math.isfinite(fps) or fps <= 0:
        raise ValueError(f"REF2VA_SOURCE_FPS_INVALID: {source_fps!r}")
    if images is None or not hasattr(images, "shape") or len(images.shape) < 1:
        raise ValueError("REF2VA_VIDEO_EMPTY: reference video frames are required")

    source_frames = int(images.shape[0])
    if source_frames <= 0:
        raise ValueError("REF2VA_VIDEO_EMPTY: reference video contains no frames")
    target_length = h3_length(float(target_duration_seconds))
    source_duration = source_frames / fps
    nominal_24 = int(math.floor(source_duration * REF2VA_FPS + 1e-7))
    legal_count = align_ref_count_down(min(target_length, nominal_24))
    if legal_count < 5:
        raise ValueError(
            f"REF2VA_VIDEO_TOO_SHORT: {source_frames} frames at {fps:g}fps "
            "cannot produce a legal H3 reference video"
        )

    import torch

    times = torch.arange(legal_count, dtype=torch.float64) / REF2VA_FPS
    indices = torch.clamp(
        torch.floor(times * fps + 0.5).long(), 0, source_frames - 1
    )
    normalized = torch.index_select(images, 0, indices.to(images.device))
    normalized_duration = legal_count / REF2VA_FPS
    audio_out, audio_report, normalized_audio_duration = _sync_audio(audio, normalized_duration)
    proof = (
        f"{REF2VA_NORMALIZE_PROOF}|fps={REF2VA_FPS:.3f}|frames={legal_count}|"
        f"duration={normalized_duration:.6f}"
    )
    report = (
        f"{proof}; source={source_frames} frames @ {fps:.6f}fps ({source_duration:.3f}s); "
        f"target_h3_length={target_length}; unique_source_frames_used={len(set(indices.cpu().tolist()))}; "
        f"{audio_report}"
    )
    return normalized, audio_out, {
        "source_fps": fps,
        "normalized_fps": REF2VA_FPS,
        "source_frame_count": source_frames,
        "normalized_frame_count": legal_count,
        "source_duration_seconds": source_duration,
        "normalized_duration_seconds": normalized_duration,
        "audio_duration_seconds": normalized_audio_duration,
        "proof": proof,
        "report": report,
    }


def validate_synced_audio(audio: dict[str, Any] | None, video_duration_seconds: float, tolerance: float = 0.01):
    """Return a deterministic audio contract result suitable for a registry."""

    if audio is None:
        return {"present": False, "valid": True, "duration_seconds": None, "difference_seconds": None}
    duration = audio_duration(audio)
    if duration is None:
        return {"present": True, "valid": False, "duration_seconds": None, "difference_seconds": None}
    difference = abs(duration - float(video_duration_seconds))
    return {
        "present": True,
        "valid": difference <= float(tolerance),
        "duration_seconds": duration,
        "difference_seconds": difference,
    }


def validate_normalize_proof(proof: str, frame_count: int, duration_seconds: float) -> bool:
    expected = (
        f"{REF2VA_NORMALIZE_PROOF}|fps={REF2VA_FPS:.3f}|frames={int(frame_count)}|"
        f"duration={float(duration_seconds):.6f}"
    )
    return str(proof or "") == expected
