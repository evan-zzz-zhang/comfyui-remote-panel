from __future__ import annotations

from typing import Any

from aiohttp import web


_SCRIPT_TAG = '<script src="/static/v048_ref2va_ui.js?v=0.4.8.3" defer></script>'


def install() -> None:
    """Inject the isolated Ref2VA family creation controls."""

    from . import app as app_module

    if getattr(app_module.create_app, "_v048_frontend", False):
        return
    original = app_module.create_app

    def create_app_v048_frontend(*args: Any, **kwargs: Any):
        application = original(*args, **kwargs)

        @web.middleware
        async def v048_frontend(request: web.Request, handler):
            response = await handler(request)
            if (
                request.method == "GET"
                and request.path == "/"
                and isinstance(response, web.Response)
                and response.content_type == "text/html"
                and _SCRIPT_TAG not in (response.text or "")
            ):
                html = response.text.replace("</body>", f"  {_SCRIPT_TAG}\n</body>")
                replacement = web.Response(text=html, status=response.status, content_type="text/html")
                for key, value in response.headers.items():
                    if key.lower() not in {"content-type", "content-length"}:
                        replacement.headers[key] = value
                return replacement
            return response

        application.middlewares.insert(0, v048_frontend)
        return application

    create_app_v048_frontend._v048_frontend = True  # type: ignore[attr-defined]
    app_module.create_app = create_app_v048_frontend
