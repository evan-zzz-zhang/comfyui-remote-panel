from __future__ import annotations

from typing import Any

from aiohttp import web


_SCRIPT_TAGS = (
    '<script src="/static/v046_fl2va_ui.js?v=0.4.7.1" defer></script>\n'
    '  <script src="/static/v046_job_runtime_ui.js?v=0.4.6.3" defer></script>\n'
    '  <script src="/static/v046_workflow_selection_guard.js?v=0.4.6.2" defer></script>\n'
    '  <script src="/static/v046_force_stop_ui.js?v=0.4.6.2" defer></script>\n'
    '  <script src="/static/v046_sage_attention_status.js?v=0.4.6.1" defer></script>'
)


def install() -> None:
    """Inject the v0.4.6 frontend patches."""

    from . import app as app_module

    if getattr(app_module.create_app, "_v046_frontend", False):
        return

    original_create_app = app_module.create_app

    def create_app_v046_frontend(*args: Any, **kwargs: Any):
        application = original_create_app(*args, **kwargs)

        @web.middleware
        async def v046_frontend(request: web.Request, handler):
            response = await handler(request)
            if (
                request.method == "GET"
                and request.path == "/"
                and isinstance(response, web.Response)
                and response.content_type == "text/html"
            ):
                html = response.text
                if html and "/static/v046_workflow_selection_guard.js" not in html:
                    html = html.replace("</body>", f"  {_SCRIPT_TAGS}\n</body>")
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

        application.middlewares.insert(0, v046_frontend)
        return application

    create_app_v046_frontend._v046_frontend = True  # type: ignore[attr-defined]
    app_module.create_app = create_app_v046_frontend
