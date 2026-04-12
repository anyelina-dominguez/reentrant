"""The two order statistics used in more than one place.

They are here rather than in :mod:`reentrant.util.times` because they are not
about time -- the same functions serve seeing, splits and course lengths -- and
because both have an awkward empty case that is better decided once.
"""

from __future__ import annotations

from typing import Sequence


def _half_up(value: float) -> int:
    """Round half away from zero, which is what a person means by "round".

    Python's built-in rounds half to even, so ``round(2.5)`` is 2 -- correct
    for statistics and surprising in a results list, where the median of four
    runners on 1, 2, 3 and 4 minutes should read as 3 rather than 2.
    """
    return int(value + 0.5) if value >= 0 else -int(-value + 0.5)


def median_of(values: Sequence[float]) -> int | None:
    """The middle value, rounded to a whole number, or ``None`` for nothing.

    Rounded because every caller here is dealing in whole seconds, and an even
    number of runners would otherwise produce a median half a second long.
    """
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return _half_up(ordered[middle])
    return _half_up((ordered[middle - 1] + ordered[middle]) / 2)


def percentile_of(values: Sequence[float], fraction: float) -> int | None:
    """The value below which ``fraction`` of the sample sits, interpolated."""
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return _half_up(ordered[0])
    position = max(0.0, min(1.0, fraction)) * (len(ordered) - 1)
    low = int(position)
    high = min(low + 1, len(ordered) - 1)
    share = position - low
    return _half_up(ordered[low] + (ordered[high] - ordered[low]) * share)
