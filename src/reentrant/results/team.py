"""Club team scoring.

A club league scores the **first ``counting`` runners from each club** on each
course. Their places are added up and the lowest total wins, which is cross
country scoring and behaves the way people expect: winning a course is worth
one point, and a club with nobody near the front loses by a mile.

Two rules that decide the awkward cases:

* **A club with fewer than ``counting`` finishers does not score.** Not zero,
  not a large penalty -- it is not a team. Listing it as incomplete is more
  useful than pretending it came last.
* **A tie is broken by the last scoring runner.** Two clubs on 24 points, one
  with places 2, 10, 12 and one with 6, 8, 10: the second wins, because their
  worst counter is better. It is the standard rule and it almost always breaks
  the tie.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..util.order import group_by, sorted_by
from ..util.validate import require_int
from .classify import Result, classify

#: How many runners from a club count towards its score.
DEFAULT_COUNTING = 3


@dataclass
class TeamScore:
    """One club's score on one course."""

    club: str
    course: str
    places: list[int] = field(default_factory=list)
    counting: int = DEFAULT_COUNTING
    finishers: int = 0

    @property
    def complete(self) -> bool:
        return len(self.places) >= self.counting

    @property
    def points(self) -> int | None:
        return sum(self.places[:self.counting]) if self.complete else None

    @property
    def last_counter(self) -> int | None:
        return self.places[self.counting - 1] if self.complete else None

    def to_dict(self) -> dict[str, object]:
        return {
            "club": self.club,
            "course": self.course,
            "points": self.points,
            "places": list(self.places[:self.counting]),
            "finishers": self.finishers,
            "complete": self.complete,
        }


def score_course(results: list[Result], *, counting: int = DEFAULT_COUNTING) -> list[TeamScore]:
    """Score one course's results by club, best team first."""
    require_int(counting, "counting", minimum=1, maximum=20)
    placed = [row for row in classify(results) if row.placed and row.club]
    course = placed[0].course if placed else ""

    scores = []
    for club, rows in group_by(sorted_by(placed, "place"), lambda row: row.club).items():
        scores.append(TeamScore(
            club=club,
            course=course,
            places=[int(row.place) for row in rows if row.place is not None],
            counting=counting,
            finishers=len(rows),
        ))

    complete = [score for score in scores if score.complete]
    incomplete = [score for score in scores if not score.complete]
    return (sorted_by(complete, "points", "last_counter", "club")
            + sorted_by(incomplete, "-finishers", "club"))


def score_event(results: list[Result], *, counting: int = DEFAULT_COUNTING) -> dict[str, list[TeamScore]]:
    """Every course scored separately, which is how a club league runs."""
    by_course = group_by(sorted_by(results, "course"), lambda row: row.course)
    return {course: score_course(rows, counting=counting) for course, rows in by_course.items()}


def club_totals(scored: dict[str, list[TeamScore]]) -> list[dict[str, object]]:
    """Add each club's course scores together, for the trophy.

    A club that failed to make a team on one course still counts on the others;
    the total is over the courses where they did score, and the number of them
    is reported so that two clubs on the same total can be told apart.
    """
    totals: dict[str, dict[str, object]] = {}
    for course, scores in scored.items():
        for score in scores:
            if score.points is None:
                continue
            held = totals.setdefault(score.club, {"club": score.club, "points": 0, "courses": 0})
            held["points"] = int(held["points"]) + score.points
            held["courses"] = int(held["courses"]) + 1
    return sorted_by(list(totals.values()), "-courses", "points", "club")
