"""Parse a request, call a handler, write JSON.

Handlers are plain functions of ``(params, query, body, context)`` returning a
value, or a ``(status, value)`` pair. They know nothing about sockets, which is
what lets :mod:`reentrant.api.testapp` drive exactly the same code without one.

Errors carry their own status. Anything that does not is a 500 with its class
name, because an error nobody anticipated is a bug and hiding it helps no one.
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

from ..errors import ValidationError, status_of
from .router import Router

MAX_BODY = 4 * 1024 * 1024


def handle(router: Router, context: Any, method: str, path: str,
           query: dict[str, str] | None = None, body: Any = None) -> tuple[int, Any]:
    """Run one request through the router, returning ``(status, body)``."""
    try:
        handler, params = router.match(method, path)
        result = handler(params=params, query=query or {}, body=body, context=context)
        if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], int):
            return result
        return (201 if str(method).upper() == "POST" else 200), result
    except Exception as error:  # noqa: BLE001 - every error becomes a response
        status = status_of(error)
        if hasattr(error, "to_dict"):
            return status, error.to_dict()  # type: ignore[attr-defined]
        return status, {"error": type(error).__name__, "message": str(error)}


def _query_of(url: str) -> dict[str, str]:
    parsed = urlparse(url)
    return {key: values[0] for key, values in parse_qs(parsed.query).items()}


def make_handler(router: Router, context: Any):
    """A :mod:`http.server` request handler bound to a router and a context."""

    class RequestHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: Any) -> None:  # pragma: no cover - quiet
            pass

        def _respond(self, status: int, payload: Any) -> None:
            text = json.dumps(payload, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("content-type", "application/json; charset=utf-8")
            self.send_header("content-length", str(len(text)))
            self.end_headers()
            self.wfile.write(text)

        def _body(self) -> Any:
            length = int(self.headers.get("content-length") or 0)
            if length <= 0:
                return None
            if length > MAX_BODY:
                raise ValidationError("that request body is too large")
            raw = self.rfile.read(length).decode("utf-8").strip()
            if not raw:
                return None
            try:
                return json.loads(raw)
            except json.JSONDecodeError:
                raise ValidationError("the request body is not valid JSON") from None

        def _run(self, method: str) -> None:
            try:
                body = self._body()
            except ValidationError as error:
                self._respond(error.status, error.to_dict())
                return
            path = urlparse(self.path).path
            status, payload = handle(router, context, method, path, _query_of(self.path), body)
            self._respond(status, payload)

        def do_GET(self) -> None:  # noqa: N802
            self._run("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._run("POST")

        def do_PUT(self) -> None:  # noqa: N802
            self._run("PUT")

        def do_PATCH(self) -> None:  # noqa: N802
            self._run("PATCH")

        def do_DELETE(self) -> None:  # noqa: N802
            self._run("DELETE")

    return RequestHandler


def serve(router: Router, context: Any, *, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    """Start a server. Port 0 binds a free one, which the caller reads back."""
    return ThreadingHTTPServer((host, port), make_handler(router, context))
