"""The download tent.

A card is put on the reader and this happens:

1. find whose card it is;
2. work out when they started -- their punch, or the time they were drawn;
3. find the course their class runs;
4. check the punches against it;
5. work out the time, the splits, and what to print on the slip.

Every one of those steps can fail in a way the person standing at the desk has
to be told about in one sentence, so nothing here raises for an ordinary
problem. An unknown card, a missing start, a mispunch -- all of them come back
as a result with a reason on it. Exceptions are for the event being set up
wrongly, which is not something to discover at the desk.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..entries.competitor import Entry
from ..errors import NotFoundError
from ..results.classify import Result, result_for
from ..timing.punch import CardRead
from ..timing.validate import RunCheck, check_run, missing_report, splits
from ..util.text import table
from ..util.times import format_clock, format_time_of_day
from .event import Event


@dataclass
class Download:
    """What came of putting one card on the reader."""

    card: int
    entry: Entry | None = None
    course: str = ""
    check: RunCheck | None = None
    seconds: int | None = None
    start_seconds: int | None = None
    finish_seconds: int | None = None
    splits: list[dict[str, object]] = field(default_factory=list)
    problem: str = ""

    @property
    def ok(self) -> bool:
        return self.problem == "" and self.check is not None and self.check.ok

    @property
    def name(self) -> str:
        return "" if self.entry is None else self.entry.competitor.listed_name

    def to_result(self) -> Result | None:
        """The row this download puts on the results list."""
        if self.entry is None:
            return None
        return result_for(self.entry, self.check, self.seconds)

    def slip(self) -> str:
        """The strip of paper the runner is handed."""
        if self.entry is None:
            return f"card {self.card}: {self.problem}"
        lines = [
            f"{self.name}  ({self.entry.class_code})",
            f"{self.course}   card {self.card}",
        ]
        if self.start_seconds is not None:
            lines.append(f"start {format_time_of_day(self.start_seconds)}")
        if self.seconds is not None:
            lines.append(f"time  {format_clock(self.seconds)}")
        if not self.ok:
            lines.append(self.problem or "not classified")
        if self.splits:
            lines.append("")
            lines.append(table(
                [{"key": "number", "title": "#", "align": "right"},
                 {"key": "code", "title": "code"},
                 {"key": "leg", "title": "leg", "align": "right"},
                 {"key": "elapsed", "title": "total", "align": "right"}],
                [{"number": row["number"], "code": row["code"],
                  "leg": format_clock(int(row["leg_seconds"])),
                  "elapsed": format_clock(int(row["elapsed_seconds"]))}
                 for row in self.splits],
            ))
        return "\n".join(lines)


def process(event: Event, read: CardRead) -> Download:
    """Put one card through the desk."""
    entry = event.entries.by_card(read.card)
    if entry is None:
        return Download(card=read.card, problem="that card is not entered")

    try:
        course_name = event.entry_course(entry)
    except NotFoundError as error:
        return Download(card=read.card, entry=entry, problem=error.message)

    course = event.courses.get(course_name)
    if course is None:
        return Download(card=read.card, entry=entry, course=course_name,
                        problem=f"course {course_name} does not exist")

    start_seconds = read.start_seconds if read.start_seconds is not None else entry.start_seconds
    finish_seconds = read.finish_seconds

    check = check_run(course, read, start_seconds=start_seconds, finish_seconds=finish_seconds)
    seconds = read.elapsed(start_seconds, finish_seconds) if check.ok else None

    rows: list[dict[str, object]] = []
    if start_seconds is not None:
        rows = splits(check.matched, start_seconds, finish_seconds)

    return Download(
        card=read.card,
        entry=entry,
        course=course_name,
        check=check,
        seconds=seconds,
        start_seconds=start_seconds,
        finish_seconds=finish_seconds,
        splits=rows,
        problem="" if check.ok else missing_report(check, course),
    )


def process_all(event: Event, reads: list[CardRead]) -> list[Download]:
    """A whole download log, in the order the cards were read."""
    return [process(event, read) for read in reads]


def results_from(event: Event, downloads: list[Download]) -> list[Result]:
    """Every entry as a results row, including those who never downloaded.

    The entries with no download are the ones who are still out in the forest,
    and at the end of the day they are the reason the organiser walks the
    courses. They appear as non-starters until somebody says otherwise.
    """
    rows: list[Result] = []
    seen: set[str] = set()
    for download in downloads:
        row = download.to_result()
        if row is not None:
            rows.append(row)
            seen.add(row.entry)
    for entry in event.entries.all():
        if entry.reference not in seen:
            rows.append(result_for(entry, None, None))
    return rows


def outstanding(event: Event, downloads: list[Download]) -> list[Entry]:
    """Who has started and not come back."""
    seen = {download.entry.reference for download in downloads if download.entry is not None}
    return [entry for entry in event.entries.all()
            if entry.reference not in seen and entry.start_seconds is not None]
