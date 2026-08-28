from __future__ import annotations

from typing import Any


def install() -> None:
    """Make v0.4 frontend updates visible immediately after a restart.

    During active development the same /static URLs change frequently. Mobile
    browsers can otherwise keep an older JS/CSS response and combine it with a
    newer HTML/backend version. Keep v0.4 static responses uncached; a future
    production build can switch to content-hashed asset filenames instead.
    """

    from . import app as app_module

    if getattr(app_module.create_app, "_v04_no_store_static", False):
        return

    original_create_app = app_module.create_app

    def create_app_v04(*args: Any, **kwargs: Any):
        application = original_create_app(*args, **kwargs)

        async def no_store_static(request, response) -> None:
            if request.path.startswith("/static/"):
                response.headers["Cache-Control"] = "no-store, max-age=0"
                response.headers["Pragma"] = "no-cache"
                response.headers["Expires"] = "0"

        application.on_response_prepare.append(no_store_static)
        return application

    create_app_v04._v04_no_store_static = True  # type: ignore[attr-defined]
    app_module.create_app = create_app_v04
