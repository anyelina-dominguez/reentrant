"""Argument checking, in one place.

Every one of these returns the value it checked, so they read as part of an
assignment::

    self.code = require_str(code, "code", max_len=8)

The point of doing it at the edge is that a bad value fails with the field name
attached, rather than three calls later as a ``TypeError`` inside a comparison.
"""

from __future__ import annotations

import re
from typing import Any, Callable, Iterable, Sequence, TypeVar

from ..errors import ValidationError

T = TypeVar("T")


def fail(message: str, **details: Any) -> None:
    raise ValidationError(message, **details)


def require(value: Any, field: str) -> Any:
    if value is None:
        fail(f"{field} is required", field=field)
    return value


def require_str(
    value: Any,
    field: str,
    *,
    min_len: int = 1,
    max_len: int = 500,
    pattern: str | re.Pattern[str] | None = None,
    strip: bool = True,
) -> str:
    if not isinstance(value, str):
        fail(f"{field} must be a string", field=field)
    text = value.strip() if strip else value
    if len(text) < min_len:
        fail(f"{field} must be at least {min_len} character{'' if min_len == 1 else 's'}", field=field)
    if len(text) > max_len:
        fail(f"{field} must be at most {max_len} characters", field=field)
    if pattern is not None and not re.fullmatch(pattern, text):
        fail(f"{field} is not in the expected form", field=field)
    return text


def require_int(
    value: Any,
    field: str,
    *,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    # bool is an int in Python, and a boolean where a count belongs is a bug.
    if isinstance(value, bool) or not isinstance(value, int):
        if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
            value = int(value)
        else:
            fail(f"{field} must be a whole number", field=field)
    if minimum is not None and value < minimum:
        fail(f"{field} must be at least {minimum}", field=field)
    if maximum is not None and value > maximum:
        fail(f"{field} must be at most {maximum}", field=field)
    return int(value)


def require_number(
    value: Any,
    field: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        if isinstance(value, str):
            try:
                value = float(value.strip())
            except ValueError:
                fail(f"{field} must be a number", field=field)
        else:
            fail(f"{field} must be a number", field=field)
    number = float(value)
    if number != number or number in (float("inf"), float("-inf")):
        fail(f"{field} must be a finite number", field=field)
    if minimum is not None and number < minimum:
        fail(f"{field} must be at least {minimum}", field=field)
    if maximum is not None and number > maximum:
        fail(f"{field} must be at most {maximum}", field=field)
    return number


def require_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        fail(f"{field} must be true or false", field=field)
    return value


def require_one_of(value: T, field: str, allowed: Sequence[T]) -> T:
    if value not in allowed:
        fail(f"{field} must be one of {', '.join(str(item) for item in allowed)}",
             field=field, allowed=list(allowed))
    return value


def require_list(value: Any, field: str, *, min_len: int = 0, max_len: int = 100_000) -> list[Any]:
    if not isinstance(value, (list, tuple)):
        fail(f"{field} must be a list", field=field)
    items = list(value)
    if len(items) < min_len:
        fail(f"{field} must have at least {min_len} entries", field=field)
    if len(items) > max_len:
        fail(f"{field} must have at most {max_len} entries", field=field)
    return items


def require_mapping(value: Any, field: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"{field} must be an object", field=field)
    return value


def optional(value: Any, check: Callable[[Any], T]) -> T | None:
    """Absent values pass straight through; present ones are checked."""
    return None if value is None else check(value)


def unique(values: Iterable[T]) -> list[T]:
    seen: dict[T, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return list(seen)
