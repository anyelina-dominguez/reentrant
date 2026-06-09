"""The call-up.

Runners are called forward in stages before their slot: to the queue at minus
four minutes, to the map box at minus one, to the line at zero. The person
holding the list wants one thing -- who should be standing where, right now --
and gets it from here.

The stages are the ones a British start uses. They exist because a start lane
of four hundred people is a queue whose length is fixed by the interval, and
anybody who is not in the right box at the right minute holds up everybody
behind them.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..entries.competitor import Entry
from ..util.order import sorted_by
from ..util.times import difference, format_time_of_day
from ..util.validate import require_int

#: Minutes before the slot at which each stage happens.
STAGES = [("queue", 4), ("map box", 1), ("line", 0)]


@dataclass(frozen=True)
class CallUp:
    """One runner, and where they should be."""

    entry: str
    name: str
    course: str
    start_seconds: int
    stage: str
    minutes_away: int

    def to_dict(self) -> dict[str, object]:
        return {
            "entry": self.entry,
            "name": self.name,
            "course": self.course,
            "start": format_time_of_day(self.start_seconds),
            "stage": self.stage,
            "minutes_away": self.minutes_away,
        }


def _stage_for(minutes_away: int) -> str | None:
    for name, minutes in STAGES:
        if minutes_away >= minutes:
            return name
    return None


def call_up(entries: list[Entry], now_seconds: int, *,
            course_of=None) -> list[CallUp]:
    """Who should be where at this moment, nearest to starting first.

    ``course_of`` resolves an entry to the course it runs; without it the
    entry's own course is used.
    """
    require_int(now_seconds, "now_seconds", minimum=0, maximum=86_399)
    rows = []
    for entry in entries:
        if entry.start_seconds is None:
            continue
        away = difference(now_seconds, entry.start_seconds)
        if away > 24 * 3600 - 1:
            continue
        minutes = away // 60
        stage = _stage_for(minutes)
        if stage is None or minutes > STAGES[0][1]:
            continue
        rows.append(CallUp(
            entry=entry.reference,
            name=entry.competitor.listed_name,
            course=course_of(entry) if course_of else entry.course,
            start_seconds=entry.start_seconds,
            stage=stage,
            minutes_away=minutes,
        ))
    return sorted_by(rows, "minutes_away", "name")


def missing_from(entries: list[Entry], now_seconds: int, present: set[str]) -> list[Entry]:
    """Who is due at the line and is not there.

    The list the start official reads out, and the only reason the call-up is
    written down at all.
    """
    due = {row.entry for row in call_up(entries, now_seconds) if row.stage == "line"}
    return sorted_by([entry for entry in entries
                      if entry.reference in due and entry.reference not in present],
                     lambda entry: entry.competitor.listed_name)
