"""Relays.

A relay team is an ordered list of runners, one per leg, each running their own
course. The team's time is the sum of its legs, and the team is classified only
if **every** leg counts -- one mispunch anywhere and the whole team is out,
which is what makes relays what they are.

Two things about the arithmetic:

**The changeover is the previous leg's finish.** A leg's time is measured from
when the runner before them finished, not from when they personally started
running, because the few seconds in the changeover box belong to somebody.
The first leg runs from the mass start.

**A team may be short.** A three-leg team with two runners is not disqualified,
it simply has no time -- the missing leg is reported as such, which is
different from a mispunch and reads differently on the results.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..errors import ValidationError
from ..util.order import rank, sorted_by
from ..util.times import format_clock
from ..util.validate import require_int, require_list, require_str


@dataclass
class RelayLeg:
    """One runner's leg of a relay."""

    number: int
    entry: str
    name: str
    seconds: int | None = None
    outcome: str = "ok"

    def __post_init__(self) -> None:
        self.number = require_int(self.number, "number", minimum=1, maximum=20)
        self.entry = require_str(self.entry, "entry", max_len=16)
        self.name = require_str(self.name, "name", max_len=120)
        if self.seconds is not None:
            self.seconds = require_int(self.seconds, "seconds", minimum=0)

    @property
    def counts(self) -> bool:
        return self.outcome == "ok" and self.seconds is not None


@dataclass
class RelayTeam:
    """A team, its legs, and what they add up to."""

    name: str
    club: str
    legs: list[RelayLeg] = field(default_factory=list)
    expected_legs: int = 3

    def __post_init__(self) -> None:
        self.name = require_str(self.name, "name", max_len=60)
        self.club = require_str(self.club, "club", min_len=0, max_len=40)
        self.legs = sorted_by(require_list(self.legs, "legs", max_len=20), "number")
        self.expected_legs = require_int(self.expected_legs, "expected_legs", minimum=1, maximum=20)
        numbers = [leg.number for leg in self.legs]
        if len(set(numbers)) != len(numbers):
            raise ValidationError("two runners on the same leg", team=self.name)

    @property
    def missing_legs(self) -> list[int]:
        run = {leg.number for leg in self.legs}
        return [number for number in range(1, self.expected_legs + 1) if number not in run]

    @property
    def outcome(self) -> str:
        if self.missing_legs:
            return "short"
        broken = [leg for leg in self.legs if not leg.counts]
        if broken:
            return broken[0].outcome if broken[0].outcome != "ok" else "no-time"
        return "ok"

    @property
    def seconds(self) -> int | None:
        if self.outcome != "ok":
            return None
        return sum(int(leg.seconds) for leg in self.legs)  # type: ignore[arg-type]

    @property
    def time_text(self) -> str:
        return format_clock(self.seconds)

    def cumulative(self) -> list[dict[str, object]]:
        """Each leg with the running total after it, which is what the
        changeover board shows."""
        rows: list[dict[str, object]] = []
        running: int | None = 0
        for leg in self.legs:
            if running is not None and leg.counts:
                running += int(leg.seconds)  # type: ignore[arg-type]
            else:
                running = None
            rows.append({
                "number": leg.number,
                "entry": leg.entry,
                "name": leg.name,
                "seconds": leg.seconds,
                "time": format_clock(leg.seconds),
                "elapsed": format_clock(running),
                "outcome": leg.outcome,
            })
        return rows

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "club": self.club,
            "legs": [{"number": leg.number, "entry": leg.entry, "name": leg.name,
                      "seconds": leg.seconds, "outcome": leg.outcome} for leg in self.legs],
            "expected_legs": self.expected_legs,
            "seconds": self.seconds,
            "outcome": self.outcome,
        }


def classify_relay(teams: list[RelayTeam]) -> list[dict[str, object]]:
    """Place the complete teams and list the rest behind them."""
    complete = [team for team in teams if team.outcome == "ok"]
    others = [team for team in teams if team.outcome != "ok"]

    rows: list[dict[str, object]] = []
    for place, team in rank(complete, lambda item: item.seconds):
        rows.append({**team.to_dict(), "place": place, "time": team.time_text})
    for team in sorted_by(others, "outcome", "name"):
        rows.append({**team.to_dict(), "place": None, "time": team.time_text})
    return rows


def leg_positions(teams: list[RelayTeam], number: int) -> list[dict[str, object]]:
    """Who was where at one changeover, in order.

    A team that has not reached this leg yet is left out entirely; a team whose
    earlier leg failed is included with no time, because the changeover board
    shows them coming through even though they are out of the running.
    """
    require_int(number, "number", minimum=1, maximum=20)
    rows = []
    for team in teams:
        legs = [leg for leg in team.legs if leg.number <= number]
        if len(legs) < number:
            continue
        elapsed: int | None = 0
        for leg in legs:
            if elapsed is not None and leg.counts:
                elapsed += int(leg.seconds)  # type: ignore[arg-type]
            else:
                elapsed = None
        rows.append({"team": team.name, "club": team.club,
                     "seconds": elapsed, "time": format_clock(elapsed)})
    placed = [row for row in rows if row["seconds"] is not None]
    unplaced = [row for row in rows if row["seconds"] is None]
    out = [{**row, "place": place}
           for place, row in rank(placed, lambda item: item["seconds"])]
    out.extend({**row, "place": None} for row in sorted_by(unplaced, "team"))
    return out
