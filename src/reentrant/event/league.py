"""A league across several events.

A club league runs eight or ten fixtures over a winter and scores the best
``counting`` of them. Everything interesting is in that phrase:

* **Best, not first.** A runner who does all ten counts their best six, so
  turning up to more events can only help.
* **Only events that happened.** A fixture cancelled for snow is not a nought
  for everybody, it is simply not in the league.
* **Points come from the place within the class**, not from the time, because
  the courses are different lengths at different venues and comparing times
  across them means nothing.

A runner who is disqualified at one event scores nothing there, and that is a
nought which *does* count against them if it lands in their best six -- which
it will not, because a nought is never among anybody's best six unless they
have run fewer than six events.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..results.classify import Result, by_class
from ..results.handicap import points_for
from ..util.order import group_by, sorted_by
from ..util.validate import require_int, require_str

#: How many events count towards a runner's league total.
DEFAULT_COUNTING = 6


@dataclass
class LeagueEvent:
    """One fixture's contribution to the league."""

    name: str
    date: str
    results: list[Result] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.name = require_str(self.name, "name", max_len=80)
        self.date = require_str(self.date, "date", max_len=10, pattern=r"\d{4}-\d{2}-\d{2}")


@dataclass
class LeagueScore:
    """One runner's league standing."""

    name: str
    club: str
    class_code: str
    scores: list[dict[str, object]] = field(default_factory=list)
    counting: int = DEFAULT_COUNTING

    @property
    def counted(self) -> list[dict[str, object]]:
        return sorted_by(self.scores, lambda row: -int(row["points"]))[:self.counting]

    @property
    def points(self) -> int:
        return sum(int(row["points"]) for row in self.counted)

    @property
    def events(self) -> int:
        return len(self.scores)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "club": self.club,
            "class": self.class_code,
            "points": self.points,
            "events": self.events,
            "counted": [row["event"] for row in self.counted],
        }


def score_event(event: LeagueEvent, *, top: int = 100, step: int = 2) -> list[dict[str, object]]:
    """Points for everybody at one event, by place within their class."""
    rows: list[dict[str, object]] = []
    for class_code, block in by_class(event.results).items():
        for row in block:
            rows.append({
                "event": event.name,
                "date": event.date,
                "name": row.name,
                "club": row.club,
                "class": class_code,
                "place": row.place,
                "points": points_for(row.place, top=top, step=step) if row.place else 0,
            })
    return sorted_by(rows, "class", "-points", "name")


def build_league(events: list[LeagueEvent], *, counting: int = DEFAULT_COUNTING,
                 top: int = 100, step: int = 2) -> dict[str, list[LeagueScore]]:
    """The whole league, one table per class."""
    require_int(counting, "counting", minimum=1, maximum=50)

    everybody: dict[tuple[str, str], LeagueScore] = {}
    for event in sorted_by(events, "date", "name"):
        for row in score_event(event, top=top, step=step):
            key = (str(row["name"]), str(row["class"]))
            held = everybody.get(key)
            if held is None:
                held = LeagueScore(name=str(row["name"]), club=str(row["club"]),
                                   class_code=str(row["class"]), counting=counting)
                everybody[key] = held
            held.scores.append({"event": row["event"], "date": row["date"],
                                "place": row["place"], "points": row["points"]})

    tables = group_by(sorted_by(everybody.values(), "class_code"), lambda score: score.class_code)
    return {class_code: sorted_by(scores, "-points", "-events", "name")
            for class_code, scores in tables.items()}


def standings(league: dict[str, list[LeagueScore]], class_code: str) -> list[dict[str, object]]:
    """One class's table, with places."""
    rows = league.get(str(class_code).upper(), [])
    out = []
    place = 0
    previous: int | None = None
    for index, score in enumerate(rows, start=1):
        if score.points != previous:
            place = index
            previous = score.points
        out.append({**score.to_dict(), "place": place})
    return out
