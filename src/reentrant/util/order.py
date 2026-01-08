"""Sorting, pinned.

Every list this system hands back is sorted by a key built here, and every key
ends in a field that cannot tie -- a card number, a control code, a reference.
That is deliberate. Two runs of the results processor over the same download
have to produce the same result list in the same order, and "whatever order the
dictionary iterated in" is not a rule anyone can check against a protest.

``by`` builds a key function from field names. A name may be prefixed with
``-`` to sort descending, which works for numbers and for anything else by
inverting the comparison rather than by negating the value.
"""

from __future__ import annotations

from typing import Any, Callable, Iterable, Sequence, TypeVar

T = TypeVar("T")


class _Descending:
    """Wraps a value so that sorting it ascending sorts the value descending."""

    __slots__ = ("value",)

    def __init__(self, value: Any) -> None:
        self.value = value

    def __lt__(self, other: "_Descending") -> bool:
        # Absent stays last whichever way the key runs: a competitor with no
        # time is not the fastest, and reversing the order must not make them so.
        if isinstance(self.value, _Absent):
            return False
        if isinstance(other.value, _Absent):
            return True
        return _compare(other.value, self.value)

    def __eq__(self, other: object) -> bool:  # pragma: no cover - completeness
        return isinstance(other, _Descending) and other.value == self.value


class _Absent:
    """Sorts after every real value, whichever direction the key runs."""

    __slots__ = ()

    def __lt__(self, other: Any) -> bool:
        return False

    def __gt__(self, other: Any) -> bool:
        return not isinstance(other, _Absent)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, _Absent)

    def __hash__(self) -> int:  # pragma: no cover - completeness
        return hash("_Absent")


ABSENT = _Absent()


def _compare(left: Any, right: Any) -> bool:
    if isinstance(left, _Absent):
        return False
    if isinstance(right, _Absent):
        return True
    return left < right


def _value(item: Any, name: str) -> Any:
    got = getattr(item, name, None) if not isinstance(item, dict) else item.get(name)
    return ABSENT if got is None else got


def by(*keys: str | Callable[[Any], Any]) -> Callable[[Any], tuple[Any, ...]]:
    """A sort key from field names, ``-name`` for descending, or callables."""

    def key(item: Any) -> tuple[Any, ...]:
        parts: list[Any] = []
        for entry in keys:
            if callable(entry):
                got = entry(item)
                parts.append(ABSENT if got is None else got)
                continue
            descending = entry.startswith("-")
            got = _value(item, entry[1:] if descending else entry)
            parts.append(_Descending(got) if descending else got)
        return tuple(parts)

    return key


def sorted_by(items: Iterable[T], *keys: str | Callable[[Any], Any]) -> list[T]:
    """Sort a copy, so callers never find their own list rearranged."""
    return sorted(items, key=by(*keys))


def group_by(items: Iterable[T], key: Callable[[T], Any]) -> dict[Any, list[T]]:
    """Group into a dict, insertion-ordered by first appearance."""
    groups: dict[Any, list[T]] = {}
    for item in items:
        groups.setdefault(key(item), []).append(item)
    return groups


def first_by(items: Sequence[T], *keys: str | Callable[[Any], Any]) -> T | None:
    ordered = sorted_by(items, *keys)
    return ordered[0] if ordered else None


def partition(items: Iterable[T], predicate: Callable[[T], bool]) -> tuple[list[T], list[T]]:
    """Split into (kept, dropped), both in the original order."""
    kept: list[T] = []
    dropped: list[T] = []
    for item in items:
        (kept if predicate(item) else dropped).append(item)
    return kept, dropped


def rank(items: Sequence[T], key: Callable[[T], Any]) -> list[tuple[int, T]]:
    """Rank with ties sharing a place and the next place skipped.

    Two runners tied for second are both second, and the next is fourth. That
    is how a results list reads, and it is not what ``enumerate`` gives you.
    """
    ordered = sorted(items, key=key)
    out: list[tuple[int, T]] = []
    place = 0
    previous: Any = object()
    for index, item in enumerate(ordered, start=1):
        current = key(item)
        if current != previous:
            place = index
            previous = current
        out.append((place, item))
    return out
