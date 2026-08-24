"""Local-only browser smoke fixture; never used by the production server."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

from aiohttp import web


STATIC = Path(__file__).resolve().parents[1] / "src" / "comfyui_remote_panel" / "static"
POST_COUNT = 0
METRICS_COUNT = 0


def job(index: int) -> dict:
    return {
        "id": f"job-{index}", "preset_id": "smoke", "preset_name": "Smoke",
        "status": "succeeded", "mode": "纯文字", "prompt": f"browser job {index}",
        "duration_seconds": 5, "aspect_ratio": "9:16", "megapixels": 0.4,
        "seed": str(2**53 + index), "scheduler": "beta", "sampler": "euler",
        "steps": 8, "created_at": time.time() - index, "elapsed_seconds": 1,
        "size_bytes": 100, "has_video": index == 0, "progress_percent": 100,
        "stage": "已完成", "error_summary": None,
    }


async def index(_request: web.Request) -> web.FileResponse:
    return web.FileResponse(STATIC / "index.html")


async def presets(_request: web.Request) -> web.Response:
    option = {"values": {"beta": {}}, "default": "beta"}
    return web.json_response({"items": [{
        "id": "smoke", "name": "Smoke", "description": "Browser smoke",
        "family": "fl2va", "available": True,
        "parameters": {"scheduler": option, "sampler": {"values": {"euler": {}}, "default": "euler"}, "steps": {"minimum": 1, "maximum": 50, "default": 8}},
    }]})


async def metrics(_request: web.Request) -> web.Response:
    global METRICS_COUNT
    METRICS_COUNT += 1
    return web.json_response(metrics_payload())


def metrics_payload() -> dict:
    return {
        "comfyui": {"online": True, "version": "test", "queue_count": 0, "control": {"enabled": False}},
        "gpus": [], "memory": {}, "disk": {}, "presets": {"smoke": {"available": True}}, "uptime_seconds": 1,
    }


async def jobs(request: web.Request) -> web.Response:
    page = int(request.query.get("page", "1"))
    items = [job(index) for index in range(25)]
    start = (page - 1) * 20
    return web.json_response({"items": items[start:start + 20], "pagination": {"page": page, "page_size": 20, "total": 25, "has_more": start + 20 < 25}})


async def create_job(request: web.Request) -> web.Response:
    global POST_COUNT
    POST_COUNT += 1
    await request.read()
    await asyncio.sleep(4)
    return web.json_response(job(99), status=201)


async def count(_request: web.Request) -> web.Response:
    return web.json_response({"posts": POST_COUNT, "metrics": METRICS_COUNT})


async def events(request: web.Request) -> web.StreamResponse:
    response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
    await response.prepare(request)
    import json
    payload = json.dumps({"jobs": [], "metrics": metrics_payload()}, ensure_ascii=False)
    await response.write(f"event: snapshot\ndata: {payload}\n\n".encode())
    try:
        while True:
            await asyncio.sleep(15)
            await response.write(b": keepalive\n\n")
    except (ConnectionResetError, asyncio.CancelledError):
        return response


app = web.Application(client_max_size=1024 * 1024)
app.router.add_get("/", index)
app.router.add_static("/static", STATIC)
app.router.add_get("/api/presets", presets)
app.router.add_get("/api/metrics", metrics)
app.router.add_get("/api/jobs", jobs)
app.router.add_post("/api/jobs", create_job)
app.router.add_get("/api/events", events)
app.router.add_get("/test/count", count)


if __name__ == "__main__":
    web.run_app(app, host="127.0.0.1", port=8765, print=None)
