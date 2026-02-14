"""Drive the http surface without a socket.

Tests use this rather than starting a server: the same router, the same
handlers, the same statuses and bodies, with no port to clash on and no process
to clean up. Anything that behaves differently here from over a real socket is
a bug in :mod:`reentrant.api.http`, and the api tests run a handful of requests
through an actual server to keep the two honest.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import parse_qs, urlparse

from .app import build_router
from .context import Context
from .http import handle
from .router import Router


class TestApp:
    def __init__(self, context: Context, router: Router | None = None) -> None:
        self.context = context
        self.router = router or build_router()

    def request(self, method: str, path: str, body: Any = None) -> tuple[int, Any]:
        parsed = urlparse(path)
        query = {key: values[0] for key, values in parse_qs(parsed.query).items()}
        return handle(self.router, self.context, method, parsed.path, query, body)

    def get(self, path: str) -> tuple[int, Any]:
        return self.request("GET", path)

    def post(self, path: str, body: Any = None) -> tuple[int, Any]:
        return self.request("POST", path, body)

    def put(self, path: str, body: Any = None) -> tuple[int, Any]:
        return self.request("PUT", path, body)

    def patch(self, path: str, body: Any = None) -> tuple[int, Any]:
        return self.request("PATCH", path, body)

    def delete(self, path: str, body: Any = None) -> tuple[int, Any]:
        return self.request("DELETE", path, body)


def test_app(context: Context, router: Router | None = None) -> TestApp:
    return TestApp(context, router)
