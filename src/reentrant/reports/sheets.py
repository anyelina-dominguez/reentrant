"""The printed sheets.

Seventy-two columns of fixed-width text, because these go onto a board in a
field, into an email, and through whatever printer was in the van. No colour,
no unicode beyond an ellipsis, nothing that depends on a font.

Four sheets:

* the **results**, by class, which is what goes on the board;
* the **splits**, by course, which is what the keen ones want;
* the **start list**, by time, which goes up the night before;
* the **download log**, which is what the organiser reads when a runner says
  their time is wrong.
"""

from __future__ import annotations

from ..event.event import Event
from ..results.analysis import LegAnalysis, leg_table
from ..results.classify import Result, by_class, by_course, counts
from ..util.text import heading, plural, table
from ..util.times import format_clock, format_time_of_day

WIDTH = 72


def _result_rows(rows: list[Result]) -> list[dict[str, object]]:
    return [{
        "place": "" if row.place is None else str(row.place),
        "name": row.name,
        "club": row.club,
        "time": row.time_text if row.placed else row.outcome,
        "behind": row.behind_text,
    } for row in rows]


RESULT_COLUMNS = [
    {"key": "place", "title": "", "align": "right", "width": 3},
    {"key": "name", "title": "name", "width": 26},
    {"key": "club", "title": "club", "width": 6},
    {"key": "time", "title": "time", "align": "right", "width": 8},
    {"key": "behind", "title": "", "align": "right", "width": 7},
]


def _length_of(event: Event, course_name: str) -> str:
    """``, 3.1 km`` for a course we know the length of, otherwise nothing."""
    course = event.courses.get(course_name)
    if course is None or course.is_scored:
        return ""
    try:
        metres = course.length_metres(event.controls)
    except Exception:  # noqa: BLE001 - a course with controls missing has no length
        return ""
    return f", {metres / 1000:.1f} km" if metres else ""


def results_sheet(event: Event, results: list[Result]) -> str:
    """The results, one block per class."""
    lines = [heading(f"{event.name} -- {event.date}", WIDTH)]
    if event.venue:
        lines.append(event.venue)
    lines.append("")

    blocks = by_class(results)
    for class_code in sorted(blocks):
        rows = blocks[class_code]
        course = event.class_courses.get(class_code, "")
        lines.append(heading(f"{class_code}  ({course}{_length_of(event, course)})"
                             if course else class_code, 40))
        lines.append(table(RESULT_COLUMNS, _result_rows(rows)))
        lines.append("")

    tally = counts(results)
    lines.append(" ".join(f"{outcome}: {count}" for outcome, count in tally.items()))
    return "\n".join(lines)


def course_results_sheet(event: Event, results: list[Result]) -> str:
    """The same runs grouped by course, which is what the planner reads."""
    lines = [heading(f"{event.name} -- by course", WIDTH), ""]
    blocks = by_course(results)
    for course_name in sorted(blocks):
        course = event.courses.get(course_name)
        length = ""
        if course is not None and not course.is_scored:
            metres = course.length_metres(event.controls)
            climb = course.climb_metres(event.controls)
            length = f"  {metres / 1000:.1f} km" + (f", {climb} m climb" if climb is not None else "")
        lines.append(heading(f"{course_name}{length}", 40))
        lines.append(table(RESULT_COLUMNS, _result_rows(blocks[course_name])))
        lines.append("")
    return "\n".join(lines)


def splits_sheet(legs: list[LegAnalysis], entries: dict[str, str], *, title: str = "splits") -> str:
    """One block per runner: their splits, their place on each leg.

    ``entries`` maps entry reference to the name to print.
    """
    lines = [heading(title, WIDTH), ""]
    for reference in sorted(entries, key=lambda key: entries[key]):
        rows = leg_table(legs, reference)
        if not any(row["place"] for row in rows):
            continue
        lines.append(entries[reference])
        lines.append(table([
            {"key": "number", "title": "#", "align": "right", "width": 3},
            {"key": "code", "title": "code", "width": 5},
            {"key": "time", "title": "leg", "align": "right", "width": 8},
            {"key": "place", "title": "pl", "align": "right", "width": 3},
            {"key": "fastest", "title": "best", "align": "right", "width": 8},
            {"key": "behind", "title": "lost", "align": "right", "width": 8},
        ], [{**row, "place": "" if row["place"] is None else row["place"]} for row in rows]))
        lines.append("")
    return "\n".join(lines)


def start_list_sheet(event: Event, rows: list[dict[str, object]]) -> str:
    """The start list, in time order."""
    lines = [heading(f"{event.name} -- start list", WIDTH), ""]
    lines.append(table([
        {"key": "time", "title": "time", "width": 8},
        {"key": "course", "title": "course", "width": 8},
        {"key": "name", "title": "name", "width": 26},
        {"key": "club", "title": "club", "width": 6},
    ], [{"time": row["time"], "course": row["course"],
         "name": row["name"], "club": row["club"]} for row in rows]))
    lines.append("")
    lines.append(plural(len(rows), "starter"))
    return "\n".join(lines)


def download_log_sheet(downloads: list) -> str:
    """Every card read, in the order it was read."""
    lines = [heading("download log", WIDTH), ""]
    rows = []
    for download in downloads:
        rows.append({
            "card": download.card,
            "name": download.name or "-",
            "course": download.course or "-",
            "start": "" if download.start_seconds is None else format_time_of_day(download.start_seconds),
            "time": format_clock(download.seconds),
            "note": "" if download.ok else (download.problem or "not classified"),
        })
    lines.append(table([
        {"key": "card", "title": "card", "align": "right", "width": 7},
        {"key": "name", "title": "name", "width": 22},
        {"key": "course", "title": "course", "width": 7},
        {"key": "start", "title": "start", "width": 8},
        {"key": "time", "title": "time", "align": "right", "width": 8},
        {"key": "note", "title": "note", "width": 16},
    ], rows))
    lines.append("")
    lines.append(plural(len(downloads), "card") + " read")
    return "\n".join(lines)
