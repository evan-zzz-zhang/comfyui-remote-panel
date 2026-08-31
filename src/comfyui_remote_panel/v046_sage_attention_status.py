from __future__ import annotations

import asyncio
from typing import Any

import psutil


SAGE_ATTENTION_FLAG = "--use-sage-attention"


def _listener_uses_sage_attention(lifecycle: Any) -> bool:
    """Report SageAttention only from the safely identified live listener."""
    try:
        process = lifecycle._verified_listener_process()
        if process is None:
            return False
        command_line = process.cmdline()
    except (OSError, psutil.Error):
        return False

    if not isinstance(command_line, (list, tuple)):
        return False
    return any(
        isinstance(value, str) and value.strip().lower() == SAGE_ATTENTION_FLAG
        for value in command_line[1:]
    )


def install() -> None:
    """Add actual ComfyUI SageAttention state to the metrics snapshot."""
    from . import metrics as metrics_module

    current = metrics_module.MetricsService._collect_once
    if getattr(current, "_v046_sage_attention_status", False):
        return

    original_collect_once = current

    async def collect_once_v046_sage_attention(self):
        snapshot = await original_collect_once(self)
        comfyui = snapshot.get("comfyui") if isinstance(snapshot, dict) else None
        if not isinstance(comfyui, dict):
            return snapshot

        uses_sage_attention = False
        if self.lifecycle is not None:
            uses_sage_attention = await asyncio.to_thread(
                _listener_uses_sage_attention,
                self.lifecycle,
            )
        comfyui["sage_attention"] = uses_sage_attention
        return snapshot

    collect_once_v046_sage_attention._v046_sage_attention_status = True  # type: ignore[attr-defined]
    metrics_module.MetricsService._collect_once = collect_once_v046_sage_attention
