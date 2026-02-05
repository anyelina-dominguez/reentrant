"""The results list.

A results list has two halves and they are not the same thing:

* the **placed** runners, who completed the course, in time order with ties
  sharing a place;
* everybody else -- mispunched, retired, did not start -- listed after, in a
  fixed order, with no place at all.

The second half matters more than it looks. A runner who mispunched wants to
see their name on the list with the reason next to it, not to have vanished;
and a club scoring a league needs to know the difference between somebody who
did not start and somebody who tried and failed.

Ties genuinely happen -- times are whole seconds and courses are short -- and
two runners on the same time are both given the same place, with the next place
skipped. There is no tie-break. Orienteering does not have one, and inventing
one here would be inventing a result.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..entries.competitor import Entry
from ..util.order import rank, sorted_by
from ..util.times import behind, format_behind, format_clock
from ..util.validate import optional, require_int, require_one_of, require_str
from ..timing.validate import RunCheck

#: The order the unplaced appear in, after the placed runners.
UNPLACED_ORDER = ["mispunch", "over-time", "no-finish", "no-start", "dnf", "dns", "disqualified"]


@dataclass
class Result:
    """One person's run, as it goes on the list."""

    entry: str
    name: str
    club: str
    class_code: str
    course: str
    seconds: int | None = None
    outcome: str = "ok"
    place: int | None = None
    behind_seconds: int | None = None

    def __post_init__(self) -> None:
        self.entry = require_str(self.entry, "entry", max_len=16)
        self.name = require_str(self.name, "name", max_len=120)
        self.club = require_str(self.club, "club", min_len=0, max_len=40)
        self.class_code = require_str(self.class_code, "class_code", max_len=4)
        self.course = require_str(self.course, "course", max_len=40)
        self.seconds = optional(self.seconds, lambda v: require_int(v, "seconds", minimum=0))
        self.outcome = require_one_of(self.outcome, "outcome", ["ok"] + UNPLACED_ORDER)

    @property
    def placed(self) -> bool:
        return self.outcome == "ok" and self.seconds is not None

    @property
    def time_text(self) -> str:
        return format_clock(self.seconds)

    @property
    def behind_text(self) -> str:
        return "" if self.behind_seconds is None else format_behind(self.behind_seconds)

    def to_dict(self) -> dict[str, object]:
        return {
            "entry": self.entry,
            "name": self.name,
            "club": self.club,
            "class": self.class_code,
            "course": self.course,
            "seconds": self.seconds,
            "time": self.time_text,
            "outcome": self.outcome,
            "place": self.place,
            "behind": self.behind_seconds,
        }


def result_for(entry: Entry, check: RunCheck | None, seconds: int | None) -> Result:
    """One entry plus what happened to it."""
    if entry.state in ("dns", "dnf", "disqualified"):
        outcome = entry.state
    elif check is None:
        outcome = "dns"
    else:
        outcome = check.outcome
    return Result(
        entry=entry.reference,
        name=entry.competitor.listed_name,
        club=entry.competitor.club,
        class_code=entry.class_code,
        course=entry.course,
        seconds=seconds if outcome == "ok" else None,
        outcome=outcome,
    )


def classify(results: list[Result]) -> list[Result]:
    """Place the finishers and order everybody else behind them.

    Returns new Result objects; the ones passed in are left alone, because the
    same run appears in a class list and a course list and must not be given
    two different places by whichever was built second.
    """
    placed = [row for row in results if row.placed]
    unplaced = [row for row in results if not row.placed]

    out: list[Result] = []
    leader = min((row.seconds for row in placed), default=None)
    for place, row in rank(placed, lambda item: item.seconds):
        out.append(Result(
            entry=row.entry, name=row.name, club=row.club, class_code=row.class_code,
            course=row.course, seconds=row.seconds, outcome=row.outcome,
            place=place, behind_seconds=behind(leader, row.seconds),
        ))

    order = {outcome: index for index, outcome in enumerate(UNPLACED_ORDER)}
    for row in sorted_by(unplaced, lambda item: (order.get(item.outcome, 99), item.name)):
        out.append(Result(
            entry=row.entry, name=row.name, club=row.club, class_code=row.class_code,
            course=row.course, seconds=None, outcome=row.outcome,
        ))
    return out


def by_class(results: list[Result]) -> dict[str, list[Result]]:
    """The results list as it is pinned up: one block per class, each classified."""
    blocks: dict[str, list[Result]] = {}
    for row in sorted_by(results, "class_code"):
        blocks.setdefault(row.class_code, []).append(row)
    return {code: classify(rows) for code, rows in blocks.items()}


def by_course(results: list[Result]) -> dict[str, list[Result]]:
    """And the same again by course, which is what the planner wants to see."""
    blocks: dict[str, list[Result]] = {}
    for row in sorted_by(results, "course"):
        blocks.setdefault(row.course, []).append(row)
    return {name: classify(rows) for name, rows in blocks.items()}


def winner(results: list[Result]) -> Result | None:
    """The fastest placed run, or ``None`` when nobody completed the course."""
    placed = classify(results)
    return next((row for row in placed if row.place == 1), None)


def counts(results: list[Result]) -> dict[str, int]:
    """How many of each outcome, for the line under the results."""
    tally: dict[str, int] = {}
    for row in results:
        tally[row.outcome] = tally.get(row.outcome, 0) + 1
    return dict(sorted(tally.items()))
