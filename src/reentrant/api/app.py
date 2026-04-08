"""The whole http surface, assembled in one place.

One file to read to find out what this server answers.
"""

from __future__ import annotations

from typing import Any

from .router import Router
from .routes.entries import entry_routes
from .routes.event import event_routes
from .routes.desk import desk_routes
from .routes.results import result_routes


def build_router() -> Router:
    router = Router()
    router.get("/health", lambda **_: {"ok": True})
    router.mount("", event_routes())
    router.mount("", entry_routes())
    router.mount("", result_routes())
    router.mount("", desk_routes())
    return router


def paths() -> list[str]:
    """Every route, as ``METHOD /path``, for the docs and the ``routes`` command."""
    return [f"{route.method} {route.path}" for route in build_router().routes()]
