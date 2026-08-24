from __future__ import annotations

import asyncio
import csv
import io
import shutil
import time
from typing import Any

import psutil

from .comfy import ComfyClient, ComfyError
from .db import Database
from .events import EventBus
from .lifecycle import ComfyLifecycle
from .preset import Preset


class MetricsService:
    def __init__(
        self,
        db: Database,
        comfy: ComfyClient,
        presets: dict[str, Preset],
        events: EventBus,
        data_dir,
        interval: float,
        nvidia_timeout: float,
        lifecycle: ComfyLifecycle | None = None,
    ):
        self.db = db
        self.comfy = comfy
        self.presets = presets
        self.events = events
        self.data_dir = data_dir
        self.interval = interval
        self.nvidia_timeout = nvidia_timeout
        self.lifecycle = lifecycle
        self.started_at = time.time()
        self.snapshot: dict[str, Any] = {}
        self._stop = asyncio.Event()
        self._last_preset_check = 0.0

    async def collect(self) -> dict[str, Any]:
        memory = psutil.virtual_memory()
        disk = shutil.disk_usage(self.data_dir)
        comfy_online = False
        queue_count = None
        comfy_version = None
        fallback_gpus: list[dict[str, Any]] = []
        try:
            stats, queue = await asyncio.gather(self.comfy.system_stats(), self.comfy.queue())
            comfy_online = True
            comfy_version = stats.get("system", {}).get("comfyui_version")
            queue_count = len(queue.get("queue_running", [])) + len(queue.get("queue_pending", []))
            for index, device in enumerate(stats.get("devices", [])):
                total = device.get("vram_total")
                free = device.get("vram_free")
                fallback_gpus.append({
                    "index": index,
                    "name": device.get("name"),
                    "utilization_percent": None,
                    "memory_used_bytes": total - free if isinstance(total, int) and isinstance(free, int) else None,
                    "memory_total_bytes": total,
                    "temperature_c": None,
                    "power_w": None,
                })
        except ComfyError:
            pass

        gpus = await self._nvidia_gpus()
        if not gpus:
            gpus = fallback_gpus

        now = time.time()
        if comfy_online and now - self._last_preset_check >= 30:
            self._last_preset_check = now
            for preset in self.presets.values():
                await self.comfy.validate_preset(preset)

        self.snapshot = {
            "timestamp": now,
            "uptime_seconds": round(now - self.started_at),
            "memory": {"used_bytes": memory.used, "total_bytes": memory.total, "percent": memory.percent},
            "disk": {"tracked_bytes": await self.db.tracked_size(), "free_bytes": disk.free, "total_bytes": disk.total},
            "comfyui": {
                "online": comfy_online,
                "version": comfy_version,
                "queue_count": queue_count,
                "control": self.lifecycle.snapshot(comfy_online) if self.lifecycle else {"enabled": False},
            },
            "gpus": gpus,
            "presets": {preset.id: {"available": preset.available, "diagnostics": preset.diagnostics} for preset in self.presets.values()},
        }
        return self.snapshot

    async def _nvidia_gpus(self) -> list[dict[str, Any]]:
        command = (
            "nvidia-smi",
            "--query-gpu=index,name,utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
            "--format=csv,noheader,nounits",
        )
        try:
            process = await asyncio.create_subprocess_exec(*command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        except OSError:
            return []
        try:
            stdout, _ = await asyncio.wait_for(process.communicate(), timeout=self.nvidia_timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.communicate()
            return []
        if process.returncode != 0:
            return []
        result: list[dict[str, Any]] = []
        def number(value: str) -> float | None:
            try:
                return float(value)
            except ValueError:
                return None
        for row in csv.reader(io.StringIO(stdout.decode(errors="replace"))):
            if len(row) != 7:
                continue
            values = [value.strip() for value in row]
            util, used, total, temperature, power = (number(value) for value in values[2:])
            try:
                index = int(values[0])
            except ValueError:
                continue
            result.append({
                "index": index, "name": values[1], "utilization_percent": util,
                "memory_used_bytes": int(used * 1024 * 1024) if used is not None else None,
                "memory_total_bytes": int(total * 1024 * 1024) if total is not None else None,
                "temperature_c": temperature, "power_w": power,
            })
        return result

    async def loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.events.publish("metrics", await self.collect())
            except Exception:
                pass
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.interval)
            except asyncio.TimeoutError:
                pass

    def stop(self) -> None:
        self._stop.set()
