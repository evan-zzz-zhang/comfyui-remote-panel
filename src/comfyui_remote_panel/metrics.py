from __future__ import annotations

import asyncio
import csv
import io
import shutil
import subprocess
import sys
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
        self._was_comfy_online = False
        self._comfy_failures = 0
        self._last_comfy_success_at: float | None = None
        self._collect_task: asyncio.Task[dict[str, Any]] | None = None

    async def collect(self) -> dict[str, Any]:
        if self._collect_task is None or self._collect_task.done():
            self._collect_task = asyncio.create_task(self._collect_once())
        return await asyncio.shield(self._collect_task)

    async def _collect_once(self) -> dict[str, Any]:
        memory = psutil.virtual_memory()
        disk = shutil.disk_usage(self.data_dir)
        comfy_online = False
        queue_count = None
        comfy_version = None
        stats: dict[str, Any] = {}
        fallback_gpus: list[dict[str, Any]] = []
        try:
            stats, queue = await asyncio.gather(self.comfy.system_stats(), self.comfy.queue())
            comfy_online = True
            self._comfy_failures = 0
            self._last_comfy_success_at = time.time()
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
            self._comfy_failures += 1

        gpus = await self._nvidia_gpus()
        if not gpus:
            gpus = fallback_gpus

        now = time.time()
        managed_process_alive = False
        if self.lifecycle is not None:
            managed_process_alive = await asyncio.to_thread(self.lifecycle.managed_process_alive)
        unresponsive = not comfy_online and managed_process_alive
        should_check_presets = comfy_online and (
            not self._was_comfy_online or now - self._last_preset_check >= 300
        )
        if should_check_presets:
            self._last_preset_check = now
            await self.comfy.validate_presets(list(self.presets.values()), stats)
        self._was_comfy_online = comfy_online

        control = self.lifecycle.snapshot(
            comfy_online,
            unresponsive=unresponsive,
            managed_process_alive=managed_process_alive,
            last_success_at=self._last_comfy_success_at,
        ) if self.lifecycle else {"enabled": False}
        device_state = control.get(
            "state", "online" if comfy_online else ("unresponsive" if unresponsive else "offline")
        )

        self.snapshot = {
            "timestamp": now,
            "uptime_seconds": round(now - self.started_at),
            "memory": {"used_bytes": memory.used, "total_bytes": memory.total, "percent": memory.percent},
            "disk": {"tracked_bytes": await self.db.tracked_size(), "free_bytes": disk.free, "total_bytes": disk.total},
            "comfyui": {
                "online": comfy_online,
                "version": comfy_version,
                "queue_count": queue_count,
                "state": device_state,
                "last_success_at": self._last_comfy_success_at,
                "control": control,
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
        subprocess_options: dict[str, Any] = {}
        if sys.platform == "win32":
            subprocess_options["creationflags"] = getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
                **subprocess_options,
            )
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
