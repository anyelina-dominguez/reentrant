"""The board outside the tent.

Results go up while the event is still running, which makes them **provisional**
in a way the final list is not: people are still out, the download queue is
twenty deep, and somebody's mispunch has not been looked at yet.

So the board says three things the final results do not:

* how many are still out on each course, because a leader with fifteen runners
  behind them is not a winner yet;
* that the list is provisional, in as many words;
* when it was last printed, so that nobody argues from the ten o'clock copy at
  half past twelve.

It is also short. A board is read standing up in the rain, so it shows the
first few in each class and the count of everybody else.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..event.event import Event
from ..results.classify import Result, by_class, by_course
from ..util.order import group_by, sorted_by
from ..util.text import heading, plural, table
from ..util.times import format_time_of_day

#: How many runners the board shows per class.
SHOWN = 5


@dataclass
class BoardState:
    """What the board is showing, and how provisional it is."""

    finished: int
    still_out: int
    at_seconds: int

    @property
    def provisional(self) -> bool:
        return self.still_out > 0

    def to_dict(self) -> dict[str, object]:
        return {
            "finished": self.finished,
            "still_out": self.still_out,
            "provisional": self.provisional,
            "at": format_time_of_day(self.at_seconds),
        }


def state(event: Event, results: list[Result], at_seconds: int) -> BoardState:
    finished = sum(1 for row in results if row.outcome not in ("dns",))
    return BoardState(finished=finished,
                      still_out=sum(1 for row in results if row.outcome == "dns"),
                      at_seconds=at_seconds)


def still_out_by_course(event: Event, results: list[Result]) -> list[dict[str, object]]:
    """How many are unaccounted for on each course."""
    waiting = [row for row in results if row.outcome == "dns"]
    counted = group_by(sorted_by(waiting, "course"), lambda row: row.course)
    rows = []
    for course in sorted_by(event.courses.names(), lambda name: name):
        rows.append({"course": course, "still_out": len(counted.get(course, []))})
    return rows


def board(event: Event, results: list[Result], at_seconds: int, *, shown: int = SHOWN) -> str:
    """The sheet that goes on the board."""
    told = state(event, results, at_seconds)
    lines = [heading(f"{event.name} -- results", 66)]
    lines.append("PROVISIONAL" if told.provisional else "FINAL")
    lines.append(f"printed {format_time_of_day(at_seconds)};  "
                 f"{told.finished} in, {told.still_out} still out")
    lines.append("")

    for class_code, block in sorted(by_class(results).items()):
        placed = [row for row in block if row.placed]
        if not placed:
            continue
        lines.append(heading(class_code, 34))
        lines.append(table([
            {"key": "place", "title": "", "align": "right", "width": 3},
            {"key": "name", "title": "name", "width": 24},
            {"key": "club", "title": "club", "width": 6},
            {"key": "time", "title": "time", "align": "right", "width": 8},
        ], [{"place": row.place, "name": row.name, "club": row.club, "time": row.time_text}
            for row in placed[:shown]]))
        if len(placed) > shown:
            lines.append(f"    and {plural(len(placed) - shown, 'other')}")
        lines.append("")

    waiting = [row for row in still_out_by_course(event, results) if row["still_out"]]
    if waiting:
        lines.append(heading("still out", 34))
        for row in waiting:
            lines.append(f"  {row['course']:<10} {plural(int(row['still_out']), 'runner')}")
    return "\n".join(lines)


def leaders(results: list[Result], *, by: str = "class") -> list[dict[str, object]]:
    """The current leader of each class or course, for a screen in the tent."""
    blocks = by_course(results) if by == "course" else by_class(results)
    rows = []
    for name, block in sorted(blocks.items()):
        first = next((row for row in block if row.place == 1), None)
        rows.append({
            "name": name,
            "leader": None if first is None else first.name,
            "time": None if first is None else first.time_text,
            "finishers": sum(1 for row in block if row.placed),
        })
    return rows
