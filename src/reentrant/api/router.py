"""A router, in about a hundred lines.

Paths match segment by segment, with ``:name`` capturing one segment. No
wildcards, no regular expressions, no middleware. This serves nine resources to
the two laptops in the download tent, and a hundred lines that will still work
in fifteen years is worth more than a dependency that will not.

Routes match **most specific first**: a literal segment beats a parameter, so
``/entries/search`` is found before ``/entries/:reference`` whatever order they
were added in. That rule lives here rather than in the caller because getting
it wrong produces a bug that appears the first time somebody is called Search.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from ..errors import NotFoundError, ValidationError

METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE"]

Handler = Callable[..., Any]


@dataclass(frozen=True)
class Route:
    method: str
    path: str
    handler: Handler
    segments: tuple[str, ...]

    @property
    def literals(self) -> int:
        return sum(1 for segment in self.segments if not segment.startswith(":"))


class MethodNotAllowed(ValidationError):
    status = 405


class Router:
    def __init__(self) -> None:
        self._routes: list[Route] = []

    def add(self, method: str, path: str, handler: Handler) -> "Router":
        upper = str(method).upper()
        if upper not in METHODS:
            raise ValidationError("unknown method", method=method, allowed=METHODS)
        segments = tuple(piece for piece in str(path).split("/") if piece)
        self._routes.append(Route(upper, path, handler, segments))
        return self

    def get(self, path: str, handler: Handler) -> "Router":
        return self.add("GET", path, handler)

    def post(self, path: str, handler: Handler) -> "Router":
        return self.add("POST", path, handler)

    def put(self, path: str, handler: Handler) -> "Router":
        return self.add("PUT", path, handler)

    def patch(self, path: str, handler: Handler) -> "Router":
        return self.add("PATCH", path, handler)

    def delete(self, path: str, handler: Handler) -> "Router":
        return self.add("DELETE", path, handler)

    def routes(self) -> list[Route]:
        """Every route, most specific first."""
        return sorted(self._routes, key=lambda route: (len(route.segments), -route.literals, route.path))

    def mount(self, prefix: str, other: "Router") -> "Router":
        for route in other.routes():
            self.add(route.method, f"{prefix.rstrip('/')}{route.path}", route.handler)
        return self

    def match(self, method: str, path: str) -> tuple[Handler, dict[str, str]]:
        """The handler for a request, and the captured parameters."""
        from urllib.parse import unquote

        wanted = [piece for piece in str(path).split("/") if piece]
        path_matched = False
        allowed: set[str] = set()

        for route in self.routes():
            if len(route.segments) != len(wanted):
                continue
            params: dict[str, str] = {}
            ok = True
            for segment, given in zip(route.segments, wanted):
                if segment.startswith(":"):
                    params[segment[1:]] = unquote(given)
                elif segment != given:
                    ok = False
                    break
            if not ok:
                continue
            path_matched = True
            allowed.add(route.method)
            if route.method == str(method).upper():
                return route.handler, params

        if path_matched:
            raise MethodNotAllowed("that method is not allowed here",
                                   path=path, allowed=sorted(allowed))
        raise NotFoundError("route not found", path=path)
