"""Route traces.

After the event, runners draw the route they took onto the map. It is the best
part of the sport for anybody who likes arguing, and it produces one number
worth having: how much further they ran than the straight line.

A trace is a list of points with times on them. From it:

* **length** -- how far they actually ran, which on a technical course is
  routinely a third further than the straight line;
* **efficiency** -- the straight line over the length, between nought and one.
  A leg round a hill honestly has an efficiency of 0.7 and that is not a
  mistake, which is why the number is reported rather than judged;
* **legs** -- the trace cut at the controls, so that one leg of one runner can
  be set beside the same leg of another.

Nothing here knows what the terrain was. A route with an efficiency of 0.95
through a marsh may have been a much worse choice than one of 0.75 round it,
and no arithmetic will ever say so.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..errors import ValidationError
from ..util.order import sorted_by
from ..util.times import format_clock
from ..util.validate import require_int, require_list, require_number
from . import distance as geo
from .grid import Point


@dataclass(frozen=True)
class Fix:
    """One point on a trace, with the time it was reached."""

    point: Point
    at_seconds: int

    def __post_init__(self) -> None:
        if not isinstance(self.point, Point):
            raise ValidationError("a fix needs a position", field="point")
        object.__setattr__(self, "at_seconds",
                           require_int(self.at_seconds, "at_seconds", minimum=0, maximum=86_399))


@dataclass
class Route:
    """One runner's trace round one course."""

    entry: str
    fixes: list[Fix] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.fixes = sorted_by(require_list(self.fixes, "fixes", max_len=100_000), "at_seconds")

    def __len__(self) -> int:
        return len(self.fixes)

    @property
    def metres(self) -> float:
        """How far they ran, following the trace."""
        return geo.path_length([fix.point for fix in self.fixes]).metres

    @property
    def seconds(self) -> int:
        if len(self.fixes) < 2:
            return 0
        return self.fixes[-1].at_seconds - self.fixes[0].at_seconds

    @property
    def pace(self) -> float | None:
        """Seconds per kilometre along the trace, or ``None`` if it went nowhere."""
        run = self.metres
        return None if run <= 0 else self.seconds * 1000 / run

    def straight_metres(self) -> float:
        """The straight line from the first fix to the last."""
        if len(self.fixes) < 2:
            return 0.0
        return geo.between(self.fixes[0].point, self.fixes[-1].point).metres

    def efficiency(self) -> float | None:
        """Straight line over distance run, between nought and one."""
        run = self.metres
        return None if run <= 0 else round(self.straight_metres() / run, 4)

    def at(self, seconds: int) -> Point | None:
        """Where they were at a moment: the last fix at or before it."""
        found = None
        for fix in self.fixes:
            if fix.at_seconds <= seconds:
                found = fix.point
            else:
                break
        return found

    def between(self, start_seconds: int, end_seconds: int) -> "Route":
        """The part of the trace between two moments."""
        if end_seconds < start_seconds:
            raise ValidationError("that span runs backwards",
                                  start=start_seconds, end=end_seconds)
        return Route(entry=self.entry,
                     fixes=[fix for fix in self.fixes
                            if start_seconds <= fix.at_seconds <= end_seconds])

    def legs(self, punch_seconds: list[int]) -> list["Route"]:
        """Cut the trace at the punch times, one piece per leg."""
        marks = [self.fixes[0].at_seconds] + list(punch_seconds) if self.fixes else list(punch_seconds)
        return [self.between(start, end) for start, end in zip(marks, marks[1:])]

    def to_dict(self) -> dict[str, object]:
        return {
            "entry": self.entry,
            "fixes": len(self.fixes),
            "metres": round(self.metres),
            "straight": round(self.straight_metres()),
            "efficiency": self.efficiency(),
            "seconds": self.seconds,
            "time": format_clock(self.seconds),
        }


def compare(routes: list[Route]) -> list[dict[str, object]]:
    """Set several traces of the same leg side by side, shortest run first."""
    rows = []
    for route in routes:
        rows.append({
            "entry": route.entry,
            "metres": round(route.metres),
            "seconds": route.seconds,
            "time": format_clock(route.seconds),
            "efficiency": route.efficiency(),
            "pace": None if route.pace is None else round(route.pace),
        })
    return sorted_by(rows, "seconds", "metres", "entry")


def extra_distance(route: Route, straight_metres: float) -> float:
    """How much further than the straight line, as a fraction.

    ``0.3`` means they ran thirty per cent further, which is an ordinary
    figure on a technical course and a poor one on a track.
    """
    require_number(straight_metres, "straight_metres", minimum=0)
    if straight_metres <= 0:
        return 0.0
    return round((route.metres - straight_metres) / straight_metres, 4)
