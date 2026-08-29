from __future__ import annotations

from typing import Any

from aiohttp import web


_SCRIPT_TAG = '<script src="/static/v042_ui.js?v=0.4.2" defer></script>'


def install() -> None:
    """Inject the v0.4.2 FL2VA UI after the accepted v0.4.1 frontend."""

    from . import app as app_module

    if getattr(app_module.create_app, "_v042_frontend", False):
        return

    original_create_app = app_module.create_app

    def create_app_v042_frontend(*args: Any, **kwargs: Any):
        application = original_create_app(*args, **kwargs)

        @web.middleware
        async def v042_frontend(request: web.Request, handler):
            response = await handler(request)
            if (
                request.method == "GET"
                and request.path == "/"
                and isinstance(response, web.Response)
                and response.content_type == "text/html"
            ):
                html = response.text
                if html and _SCRIPT_TAG not in html:
                    html = html.replace("</body>", f"  {_SCRIPT_TAG}\n</body>")
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

        application.middlewares.insert(0, v042_frontend)
        return application

    create_app_v042_frontend._v042_frontend = True  # type: ignore[attr-defined]
    app_module.create_app = create_app_v042_frontend
