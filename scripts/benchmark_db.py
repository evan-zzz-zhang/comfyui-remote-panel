from __future__ import annotations

import argparse
import asyncio
import sqlite3
import tempfile
import time
from pathlib import Path

from comfyui_remote_panel.db import Database


async def benchmark(count: int) -> dict[str, float]:
    with tempfile.TemporaryDirectory(prefix="remote-panel-db-", ignore_cleanup_errors=True) as directory:
        path = Path(directory) / "panel.db"
        db = Database(path)
        await db.initialize()
        now = time.time()
        with sqlite3.connect(path) as connection:
            connection.executemany(
                """INSERT INTO jobs (
                    id, preset_id, status, mode, prompt, duration_seconds, aspect_ratio,
                    megapixels, seed, scheduler, sampler, steps, created_at, finished_at, updated_at
                ) VALUES (?, 'preset', 'succeeded', 'text', 'prompt', 5, '9:16', .4,
                          '1', 'beta', 'euler', 8, ?, ?, ?)""",
                ((f"job-{index}", now - index, now - index, now) for index in range(count)),
            )

        results: dict[str, float] = {}
        for name, operation in (
            ("list_page", lambda: db.list_jobs(1, 20)),
            ("recovery_query", db.succeeded_without_output),
            ("tracked_size", db.tracked_size),
        ):
            started = time.perf_counter()
            await operation()
            results[name] = (time.perf_counter() - started) * 1000
        return results


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("counts", nargs="*", type=int, default=[1000, 10000])
    args = parser.parse_args()
    for count in args.counts:
        timings = await benchmark(count)
        print(f"{count}: " + ", ".join(f"{name}={value:.1f}ms" for name, value in timings.items()))


if __name__ == "__main__":
    asyncio.run(main())
