"""References, and the codes an event actually uses.

Two different things live here and they are not the same:

* a **control code** is written on the kite in the forest, is between 31 and
  999 by convention (31 upwards so that a code cannot be confused with a
  control number on the map), and is unique within an event.
* a **reference** is ours -- ``ENT-0042``, ``CRS-0003`` -- minted from a
  counter so that two runs of the same import produce the same references.
"""

from __future__ import annotations

import re
from typing import Iterable

from ..errors import ValidationError

CONTROL_CODE = re.compile(r"^\d{2,3}$")
REFERENCE = re.compile(r"^[A-Z]{2,4}-\d{3,5}$")

#: Codes below this are reserved: on a map, the number by the circle is the
#: control's position in the course, and a code of 12 reads as "twelfth".
LOWEST_CONTROL_CODE = 31

START_CODE = "S1"
FINISH_CODE = "F1"

#: The clear and check boxes, which are on the card but never on a course.
ADMIN_CODES = ("C1", "K1")


class Sequence:
    """A counter that can be wound forward past references read from a file."""

    def __init__(self, start: int = 1) -> None:
        self._next = start

    def take(self) -> int:
        value = self._next
        self._next += 1
        return value

    def peek(self) -> int:
        return self._next

    def observe(self, value: int | None) -> None:
        if isinstance(value, int) and value >= self._next:
            self._next = value + 1


def reference(prefix: str, number: int, width: int = 4) -> str:
    return f"{prefix}-{number:0{width}d}"


def is_reference(value: object) -> bool:
    return isinstance(value, str) and bool(REFERENCE.fullmatch(value))


def require_reference(value: object, field: str) -> str:
    if not is_reference(value):
        raise ValidationError(f"{field} is not a reference", field=field)
    return str(value)


def require_control_code(value: object, field: str = "code") -> str:
    """A control code: two or three digits, thirty-one or above."""
    text = str(value).strip() if value is not None else ""
    if text in (START_CODE, FINISH_CODE) or text in ADMIN_CODES:
        return text
    if not CONTROL_CODE.fullmatch(text):
        raise ValidationError(f"{field} must be a two or three digit control code",
                              field=field, value=text)
    if int(text) < LOWEST_CONTROL_CODE:
        raise ValidationError(
            f"{field} must be {LOWEST_CONTROL_CODE} or above, so it cannot be read as a control number",
            field=field, value=text)
    return text


def next_free_code(used: Iterable[str], *, start: int = LOWEST_CONTROL_CODE) -> str:
    """The lowest unused control code at or above ``start``."""
    taken = {str(code) for code in used}
    for candidate in range(start, 1000):
        if str(candidate) not in taken:
            return str(candidate)
    raise ValidationError("there are no control codes left", used=len(taken))
