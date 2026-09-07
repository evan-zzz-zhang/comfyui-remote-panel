from __future__ import annotations

from typing import Any

from aiohttp import web


def install() -> None:
    """Keep the compatibility installer; v0.4.8 H3 creation is in the base index."""

    from . import app as app_module

    if getattr(app_module.create_app, "_v048_frontend", False):
        return
    original = app_module.create_app

    def create_app_v048_frontend(*args: Any, **kwargs: Any):
        application = original(*args, **kwargs)

        return application

    create_app_v048_frontend._v048_frontend = True  # type: ignore[attr-defined]
    app_module.create_app = create_app_v048_frontend
