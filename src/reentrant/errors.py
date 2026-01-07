"""The error vocabulary the whole of reentrant speaks.

Four kinds, because the http layer has to turn them into four status codes and
there is no fifth thing it knows how to say:

``ValidationError``
    the caller sent something that is not a legal value

``NotFoundError``
    the caller named something that does not exist

``ConflictError``
    the caller asked for something the records forbid

``RuleError``
    the rules of the sport forbid it

The last two are worth keeping apart even though both come back as a 409. A
``ConflictError`` means "there is already a competitor with that card number";
a ``RuleError`` means "that run missed control 104 and cannot be classified".
One is about the shape of the records and the other is about orienteering, and
when the download tent has a queue it matters which.
"""

from __future__ import annotations

from typing import Any


class ReentrantError(Exception):
    """Base class: carries a message and whatever detail explains it."""

    status = 500

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        return {"error": type(self).__name__, "message": self.message, **self.details}

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"{type(self).__name__}({self.message!r}, {self.details!r})"


class ValidationError(ReentrantError):
    status = 400


class NotFoundError(ReentrantError):
    status = 404


class ConflictError(ReentrantError):
    status = 409


class RuleError(ReentrantError):
    """A rule of the sport, rather than a rule of the database."""

    status = 409


class SchemaError(ReentrantError):
    """Raised while reading a stored file rather than while serving a request."""

    status = 500


def status_of(error: BaseException) -> int:
    """The http status an error should become."""
    return getattr(error, "status", 500)
