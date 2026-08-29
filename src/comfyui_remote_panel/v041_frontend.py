from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from aiohttp import web


_STYLE_TAG = '<link rel="stylesheet" href="/static/v041.css?v=0.4.1">'
_SCRIPT_TAG = '<script src="/static/v041_ui.js?v=0.4.1" defer></script>'


def install() -> None:
    """Load the v0.4.1 frontend without rewriting accepted v0.4 markup."""

    from . import app as app_module

    if getattr(app_module.create_app, "_v041_frontend", False):
        return

    original_create_app = app_module.create_app
    index_path = Path(__file__).with_name("static") / "index.html"

    def create_app_v041_frontend(*args: Any, **kwargs: Any):
        application = original_create_app(*args, **kwargs)

        @web.middleware
        async def v041_frontend(request: web.Request, handler):
            if request.method == "GET" and request.path == "/":
                html = await asyncio.to_thread(index_path.read_text, encoding="utf-8")
                if _STYLE_TAG not in html:
                    html = html.replace("</head>", f"  {_STYLE_TAG}\n</head>")
                if _SCRIPT_TAG not in html:
                    html = html.replace("</body>", f"  {_SCRIPT_TAG}\n</body>")
                return web.Response(text=html, content_type="text/html")
            return await handler(request)

        application.middlewares.append(v041_frontend)
        return application

    create_app_v041_frontend._v041_frontend = True  # type: ignore[attr-defined]
    app_module.create_app = create_app_v041_frontend
