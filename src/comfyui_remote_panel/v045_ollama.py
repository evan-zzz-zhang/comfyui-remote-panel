from __future__ import annotations

import asyncio
import os
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import aiohttp
from aiohttp import web


_OLLAMA_SCRIPT_TAG = '<script src="/static/v045_ollama_ui.js?v=0.4.5.1" defer></script>'
_GENERATION_SYNC_SCRIPT_TAG = '<script src="/static/v045_generation_sync.js?v=0.4.5.0" defer></script>'
_DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"


def _ollama_base_url() -> str:
    value = os.environ.get("OLLAMA_HOST", _DEFAULT_OLLAMA_URL).strip() or _DEFAULT_OLLAMA_URL
    if "://" not in value:
        value = "http://" + value
    parts = urlsplit(value)
    if parts.hostname in {"0.0.0.0", "::"}:
        port = f":{parts.port}" if parts.port else ""
        parts = parts._replace(netloc=f"127.0.0.1{port}")
        value = urlunsplit(parts)
    return value.rstrip("/")


async def _fetch_ollama_models() -> list[str]:
    timeout = aiohttp.ClientTimeout(total=4, connect=2)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(_ollama_base_url() + "/api/tags") as response:
                payload = await response.json(content_type=None)
                if response.status >= 400:
                    raise RuntimeError(f"HTTP {response.status}")
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, RuntimeError) as exc:
        raise RuntimeError("Ollama 暂时无法连接") from exc

    models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(models, list):
        raise RuntimeError("Ollama 返回了无效的模型列表")

    names: list[str] = []
    seen: set[str] = set()
    for item in models:
        if not isinstance(item, dict):
            continue
        raw = item.get("name") or item.get("model")
        if not isinstance(raw, str):
            continue
        name = raw.strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def install() -> None:
    """Expose local Ollama models and load the v0.4.5 frontend compatibility layers."""

    from . import app as app_module

    if getattr(app_module.create_app, "_v045_ollama", False):
        return

    original_create_app = app_module.create_app

    def create_app_v045_ollama(*args: Any, **kwargs: Any):
        application = original_create_app(*args, **kwargs)

        async def list_ollama_models(_: web.Request) -> web.Response:
            try:
                names = await _fetch_ollama_models()
            except RuntimeError as exc:
                return web.json_response(
                    {"error": {"code": "ollama_unavailable", "message": str(exc)}},
                    status=503,
                )
            return web.json_response({"items": names})

        application.router.add_get("/api/ollama/models", list_ollama_models)

        @web.middleware
        async def v045_ollama_frontend(request: web.Request, handler):
            response = await handler(request)
            if (
                request.method == "GET"
                and request.path == "/"
                and isinstance(response, web.Response)
                and response.content_type == "text/html"
            ):
                html = response.text
                if html:
                    missing = [
                        tag for tag in (_OLLAMA_SCRIPT_TAG, _GENERATION_SYNC_SCRIPT_TAG)
                        if tag not in html
                    ]
                    if missing:
                        html = html.replace("</body>", "  " + "\n  ".join(missing) + "\n</body>")
                        replacement = web.Response(
                            text=html,
                            status=response.status,
                            content_type="text/html",
                        )
                        for key, value in response.headers.items():
                            if key.lower() not in {"content-type", "content-length"}:
                                replacement.headers[key] = value
                        return replacement
            return response

        application.middlewares.insert(0, v045_ollama_frontend)
        return application

    create_app_v045_ollama._v045_ollama = True  # type: ignore[attr-defined]
    app_module.create_app = create_app_v045_ollama
