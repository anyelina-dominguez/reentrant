"""Race time, which is a number of whole seconds and nothing else.

Everything timed in this system is an integer number of seconds since the
event's zero time. Not a float, not a ``timedelta``, not a wall clock. Three
reasons, all learned the hard way by somebody:

* splits add up. A course whose legs sum to one second less than the total time
  because of float rounding produces a protest, and the protest is upheld.
* the SI download gives whole seconds, and inventing precision the timing kit
  does not have is dishonest.
* a race can start before midnight and finish after it, and anything anchored
  to a calendar clock has to special-case that. Seconds since zero do not.

Times are *displayed* as ``mm:ss`` under an hour and ``h:mm:ss`` over it, which
is what a results list looks like, and parsed back from either.
"""

from __future__ import annotations

import re

from ..errors import ValidationError

_PART = re.compile(r"^\d{1,4}$")

#: What the results list prints where there is no time at all.
NO_TIME = "-----"


def parse_clock(text: str, field: str = "time") -> int:
    """Seconds from ``mm:ss`` or ``h:mm:ss``.

    Minutes may run past sixty in the two-field form, because a results list
    prints a seventy-three minute run as ``73:12`` at least as often as it
    prints ``1:13:12``. In the three-field form they may not: ``1:73:12`` is
    somebody's typo, not a time.
    """
    if not isinstance(text, str):
        raise ValidationError(f"{field} must be a clock reading", field=field)
    parts = text.strip().split(":")
    if len(parts) not in (2, 3) or not all(_PART.match(part) for part in parts):
        raise ValidationError(f"{field} is not a clock reading", field=field, value=text)
    numbers = [int(part) for part in parts]
    if numbers[-1] > 59:
        raise ValidationError(f"{field} has more than sixty seconds", field=field, value=text)
    if len(numbers) == 3:
        hours, minutes, seconds = numbers
        if minutes > 59:
            raise ValidationError(f"{field} has more than sixty minutes", field=field, value=text)
    else:
        hours, (minutes, seconds) = 0, numbers
    return hours * 3600 + minutes * 60 + seconds


def format_clock(seconds: int | None, *, always_hours: bool = False) -> str:
    """``mm:ss`` under the hour, ``h:mm:ss`` over it."""
    if seconds is None:
        return NO_TIME
    if seconds < 0:
        return "-" + format_clock(-seconds, always_hours=always_hours)
    hours, rest = divmod(int(seconds), 3600)
    minutes, secs = divmod(rest, 60)
    if hours or always_hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


def parse_time_of_day(text: str, field: str = "time of day") -> int:
    """Seconds since midnight, from a ``hh:mm:ss`` start time."""
    seconds = parse_clock(text, field)
    if seconds >= 24 * 3600:
        raise ValidationError(f"{field} is past midnight", field=field, value=text)
    return seconds


def format_time_of_day(seconds: int) -> str:
    """``hh:mm:ss``, wrapping past midnight rather than growing an hours field."""
    return format_clock(int(seconds) % (24 * 3600), always_hours=True).rjust(8, "0")


def difference(start: int, finish: int) -> int:
    """Elapsed seconds, allowing for a finish after midnight.

    A start at 23:50:00 and a finish at 00:12:00 is twenty-two minutes, not
    minus twenty-three hours and change.
    """
    elapsed = int(finish) - int(start)
    return elapsed if elapsed >= 0 else elapsed + 24 * 3600


def total(seconds: list[int | None]) -> int | None:
    """Sum, where a single missing part makes the whole thing missing."""
    if any(value is None for value in seconds):
        return None
    return sum(int(value) for value in seconds)  # type: ignore[arg-type]


def behind(leader: int | None, other: int | None) -> int | None:
    """How far behind the leader, or ``None`` when either has no time."""
    if leader is None or other is None:
        return None
    return int(other) - int(leader)


def format_behind(seconds: int | None) -> str:
    """``+1:23`` for a deficit, ``0:00`` for the leader."""
    if seconds is None:
        return NO_TIME
    if seconds == 0:
        return "0:00"
    return ("+" if seconds > 0 else "-") + format_clock(abs(seconds))


def per_kilometre(seconds: int | None, metres: int) -> int | None:
    """Minutes-per-kilometre pace, in seconds, rounded to the nearest second."""
    if seconds is None or metres <= 0:
        return None
    return round(seconds * 1000 / metres)
