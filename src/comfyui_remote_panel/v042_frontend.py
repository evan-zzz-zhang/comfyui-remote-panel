from __future__ import annotations

from typing import Any

from aiohttp import web


_PATCH_TAG = '<script src="/static/v042_patch.js?v=0.4.2.4" defer></script>'


def install() -> None:
    """Keep the task-detail patch available; H3 creation is owned by the v0.4.8 runtime."""

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
                if html:
                    missing = [tag for tag in (_PATCH_TAG,) if tag not in html]
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

        application.middlewares.insert(0, v042_frontend)
        return application

    create_app_v042_frontend._v042_frontend = True  # type: ignore[attr-defined]
    app_module.create_app = create_app_v042_frontend
