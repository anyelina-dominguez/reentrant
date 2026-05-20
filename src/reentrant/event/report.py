"""The organiser's report.

Written the week after, sent to the club committee and to whoever is planning
the next one. It is the only document that says whether the event worked, and
it is short on purpose: three numbers, a verdict per course, and the things
that went wrong.

Everything in it comes from the records rather than from anybody's memory,
which is the point. A report that says "the download queue was fine" when
eleven people waited twenty minutes is worse than no report.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..courses.statistics import CourseStatistics, event_statistics, report_lines
from ..results.classify import Result, counts
from ..results.protest import ComplaintBook
from ..util.text import heading, plural, table
from ..util.validate import require_str
from .event import Event


@dataclass
class EventReport:
    """What is written up afterwards."""

    event: str
    date: str
    entries: int
    starters: int
    finishers: int
    courses: list[CourseStatistics] = field(default_factory=list)
    outcomes: dict[str, int] = field(default_factory=dict)
    complaints: int = 0
    upheld: int = 0
    notes: list[str] = field(default_factory=list)

    @property
    def completion(self) -> float:
        return 0.0 if self.starters == 0 else round(self.finishers / self.starters, 4)

    @property
    def mispunch_rate(self) -> float:
        mispunched = self.outcomes.get("mispunch", 0)
        return 0.0 if self.starters == 0 else round(mispunched / self.starters, 4)

    def to_dict(self) -> dict[str, object]:
        return {
            "event": self.event,
            "date": self.date,
            "entries": self.entries,
            "starters": self.starters,
            "finishers": self.finishers,
            "completion": self.completion,
            "mispunch_rate": self.mispunch_rate,
            "outcomes": dict(self.outcomes),
            "complaints": self.complaints,
            "upheld": self.upheld,
            "courses": [row.to_dict() for row in self.courses],
            "notes": list(self.notes),
        }


def build_report(event: Event, results: list[Result], *,
                 complaints: ComplaintBook | None = None,
                 notes: list[str] | None = None) -> EventReport:
    """Gather the report from the records."""
    tally = counts(results)
    starters = sum(count for outcome, count in tally.items() if outcome != "dns")
    book = complaints or ComplaintBook()

    return EventReport(
        event=event.name,
        date=event.date,
        entries=len(event.entries),
        starters=starters,
        finishers=tally.get("ok", 0),
        courses=event_statistics(results, event.class_courses),
        outcomes=tally,
        complaints=len(book),
        upheld=sum(1 for row in book.complaints if row.outcome == "upheld"),
        notes=list(notes or []),
    )


def render_report(report: EventReport) -> str:
    """The report as it goes into the email."""
    lines = [heading(f"{report.event} -- {report.date}", 66), ""]
    lines.append(f"{plural(report.entries, 'entry', 'entries')}, "
                 f"{report.starters} started, {report.finishers} finished "
                 f"({report.completion:.0%})")
    if report.mispunch_rate:
        lines.append(f"mispunch rate {report.mispunch_rate:.0%}")
    if report.complaints:
        lines.append(f"{plural(report.complaints, 'complaint')}, {report.upheld} upheld")
    lines.append("")

    lines.append(heading("courses", 40))
    lines.append(table([
        {"key": "course", "title": "course"},
        {"key": "finishers", "title": "in", "align": "right"},
        {"key": "winning", "title": "winner", "align": "right"},
        {"key": "target", "title": "target", "align": "right"},
        {"key": "verdict", "title": "verdict"},
    ], [row.to_dict() for row in report.courses]))
    lines.append("")

    for line in report_lines(report.courses):
        lines.append(f"  {line}")

    if report.notes:
        lines.append("")
        lines.append(heading("notes", 40))
        for note in report.notes:
            lines.append(f"  {require_str(note, 'note', max_len=300)}")
    return "\n".join(lines)
