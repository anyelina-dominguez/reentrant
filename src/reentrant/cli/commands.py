"""One function per command.

Every command takes ``(arguments, held, path)`` and returns
``Outcome(status, lines, save)``. Nothing here prints: ``main`` does that, at
the very bottom, which is what makes the commands testable by reading the lines
they would have printed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..api.app import build_router, paths
from ..api.context import Context
from ..api.http import serve
from ..courses.planning import check_event, summary as planning_summary
from ..courses.sheets import all_sheets, collection_list, description_sheet
from ..reports.board import board
from ..entries.competitor import Competitor, Entry
from ..entries.hire import HireBox
from ..errors import ValidationError
from ..event.download import outstanding, process, results_from
from ..event.event import Event, summary
from ..event.report import build_report, render_report
from ..reports.exports import entries_csv, results_csv, splits_csv
from ..reports.sheets import (
    course_results_sheet, download_log_sheet, results_sheet, splits_sheet, start_list_sheet,
)
from ..results.analysis import analyse_legs
from ..results.classify import classify
from ..starts.callup import call_up
from ..starts.draw import apply_draw, draw_course, start_list
from ..store.jsonstore import EventFile
from ..timing.punch import CardRead
from ..util.csv_io import map_columns, read_rows
from ..util.text import heading, plural, table
from ..util.times import format_time_of_day, parse_time_of_day


@dataclass
class Outcome:
    """What a command did.

    ``event`` is only set by ``new``, which is the one command that makes an
    event rather than working on one.
    """

    status: int = 0
    lines: list[str] = field(default_factory=list)
    save: bool = False
    event: Event | None = None


def new_event(arguments, held: EventFile | None, path: Path) -> Outcome:
    """``reentrant new "Club fixture" 2026-05-09``"""
    if len(arguments.positional) < 2:
        return Outcome(1, ["usage: reentrant new <name> <date>"])
    if held is not None:
        return Outcome(1, [f"there is already an event in {path}"])
    name, date = arguments.positional[0], arguments.positional[1]
    event = Event(name=name, date=date, venue=arguments.value("venue", "") or "")
    return Outcome(0, [f"created {name} on {date} in {path}"], save=True, event=event)


def show(arguments, held: EventFile, path: Path) -> Outcome:
    """``reentrant show`` -- what is in the file."""
    told = summary(held.event)
    lines = [heading(f"{told['name']} -- {told['date']}", 66)]
    if told["venue"]:
        lines.append(str(told["venue"]))
    lines.append(f"{told['controls']} controls, {told['courses']} courses, "
                 f"{told['classes']} classes, {told['entries']} entries")
    lines.append("")
    lines.append(table([{"key": "course", "title": "course"},
                        {"key": "entries", "title": "entries", "align": "right"}],
                       list(told["by_course"])))  # type: ignore[arg-type]
    return Outcome(0, lines)


def check(arguments, held: EventFile, path: Path) -> Outcome:
    """``reentrant check`` -- everything that would stop the event running."""
    problems = held.event.check_ready()
    notes = check_event(held.event.courses, held.event.controls)

    lines = [heading("check", 66)]
    if problems:
        lines.append("problems:")
        lines.extend(f"  {line}" for line in problems)
    else:
        lines.append("nothing wrong")
    if notes:
        lines.append("")
        lines.append("notes for the controller:")
        for note in notes:
            lines.append(f"  [{note.kind}] {note.course}: {note.message}")
        lines.append("")
        lines.append(", ".join(f"{kind}: {count}"
                               for kind, count in planning_summary(notes).items()))
    return Outcome(1 if problems else 0, lines)


def import_entries(arguments, held: EventFile, path: Path) -> Outcome:
    """``reentrant import --file entries.csv``"""
    source = Path(arguments.require("file"))
    rows = read_rows(source.read_text(encoding="utf-8"))
    if not rows:
        return Outcome(1, [f"{source} has no rows"])

    mapping = map_columns(rows[0].keys(), {
        "surname": ["surname", "last name", "family name"],
        "forename": ["forename", "first name", "given name"],
        "club": ["club", "team"],
        "class": ["class", "age class", "category"],
        "course": ["course"],
        "card": ["card", "si", "si card", "chip"],
        "birth_year": ["birth year", "yob", "year of birth"],
        "sex": ["sex", "gender"],
    }, required=["surname", "forename", "class"])

    added, rejected = [], []
    for number, row in enumerate(rows, start=2):
        try:
            entry = Entry(
                reference=held.event.entries.next_reference(),
                competitor=Competitor(
                    surname=row[mapping["surname"]],
                    forename=row[mapping["forename"]],
                    club=row.get(mapping.get("club", ""), ""),
                    birth_year=int(row[mapping["birth_year"]]) if mapping.get("birth_year") and row.get(mapping["birth_year"]) else None,
                    sex=row.get(mapping.get("sex", "")) or None,
                ),
                course=row.get(mapping.get("course", ""), ""),
                class_code=row[mapping["class"]],
                card=int(row[mapping["card"]]) if mapping.get("card") and row.get(mapping["card"]) else None,
            )
            held.event.entries.add(entry)
            added.append(entry)
        except Exception as error:  # noqa: BLE001 - one bad row must not lose the file
            rejected.append((number, getattr(error, "message", str(error))))

    lines = [f"read {plural(len(rows), 'row')} from {source}",
             f"added {len(added)}, rejected {len(rejected)}"]
    lines.extend(f"  line {number}: {reason}" for number, reason in rejected)
    return Outcome(1 if rejected else 0, lines, save=bool(added))


def draw(arguments, held: EventFile, path: Path) -> Outcome:
    """``reentrant draw --first 10:00:00 --interval 60``"""
    event = held.event
    first = parse_time_of_day(arguments.value("first", "10:00:00") or "10:00:00", "first")
    interval = arguments.number("interval", 60) or 60
    seed = arguments.value("seed", event.name) or event.name

    draws = []
    for course in event.courses.all():
        runners = [entry for entry in event.entries.all()
                   if event.entry_course(entry) == course.name]
        if not runners:
            continue
        drawn = draw_course(course.name, runners, first_seconds=first,
                            interval_seconds=interval, seed=seed)
        for entry in apply_draw(runners, drawn):
            event.entries.update(entry)
        draws.append(drawn)

    if not draws:
        return Outcome(1, ["there is nobody to draw"])

    lines = [heading("start draw", 66)]
    for drawn in draws:
        note = "" if not drawn.unresolved else f"  ({plural(len(drawn.unresolved), 'clash')})"
        lines.append(f"  {drawn.course}: {plural(len(drawn.slots), 'starter')}{note}")
    lines.append("")
    lines.append(start_list_sheet(event, start_list(draws)))
    return Outcome(0, lines, save=True)


def starts(arguments, held: EventFile, path: Path) -> Outcome:
    """``reentrant starts`` -- the list as it stands."""
    event = held.event
    rows = []
    for entry in event.entries.all():
        if entry.start_seconds is None:
            continue
        rows.append({"time": format_time_of_day(entry.start_seconds),
                     "seconds": entry.start_seconds,
                     "course": event.entry_course(entry),
                     "name": entry.competitor.listed_name,
                     "club": entry.competitor.club})
    rows.sort(key=lambda row: (row["seconds"], row["course"], row["name"]))
    if not rows:
        return Outcome(1, ["nobody has a start time yet"])
    return Outcome(0, [start_list_sheet(event, rows)])


def download(arguments, held: EventFile, path: Path) -> Outcome:
    """``reentrant download --file cards.json`` -- put a log of cards through."""
    source = Path(arguments.require("file"))
    import json

    raw = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValidationError("a download log is a list of card reads")

    processed = []
    for row in raw:
        read = CardRead.from_dict(row)
        held.downloads.append(read)
        processed.append(process(held.event, read))

    held.results = results_from(held.event, processed)
    lines = [download_log_sheet(processed)]
    still_out = outstanding(held.event, processed)
    if still_out:
        lines.append("")
        lines.append(f"still out: " + ", ".join(entry.competitor.listed_name for entry in still_out))
    return Outcome(0, lines, save=True)


def results(arguments, held: EventFile, path: Path) -> Outcome:
    """``reentrant results [--by course] [--csv]``"""
    rows = held.results
    if not rows:
        return Outcome(1, ["nothing has been downloaded yet"])
    if arguments.flag("csv"):
        return Outcome(0, results_csv(rows).rstrip("\n").split("\n"))
    if arguments.value("by") == "course":
        return Outcome(0, [course_results_sheet(held.event, rows)])
    return Outcome(0, [results_sheet(held.event, rows)])


def splits(arguments, held: EventFile, path: Path) -> Outcome:
    """``reentrant splits --course Blue [--csv]``"""
    course = arguments.require("course")
    held.event.courses.require(course)

    by_entry: dict[str, list[dict[str, Any]]] = {}
    names: dict[str, str] = {}
    for read in held.downloads:
        result = process(held.event, read)
        if result.entry is None or result.course != course or not result.ok:
            continue
        by_entry[result.entry.reference] = result.splits
        names[result.entry.reference] = result.entry.competitor.listed_name

    if not by_entry:
        return Outcome(1, [f"nobody has completed {course} yet"])
    if arguments.flag("csv"):
        return Outcome(0, splits_csv(by_entry, names).rstrip("\n").split("\n"))
    legs = analyse_legs(by_entry)
    return Outcome(0, [splits_sheet(legs, names, title=f"splits -- {course}")])


def export_entries(arguments, held: EventFile, path: Path) -> Outcome:
    """``reentrant export-entries`` -- the entry list back out as CSV."""
    rows = held.event.entries.all()
    if not rows:
        return Outcome(1, ["there are no entries"])
    return Outcome(0, entries_csv(rows).rstrip("\n").split("\n"))


def show_board(arguments, held: EventFile, path: Path) -> Outcome:
    """``reentrant board [--at 13:30:00] [--shown 5]`` -- the sheet for the board."""
    if not held.results:
        return Outcome(1, ["nothing has been downloaded yet"])
    at_seconds = parse_time_of_day(arguments.value("at", "12:00:00") or "12:00:00", "at")
    shown = arguments.number("shown", 5) or 5
    return Outcome(0, [board(held.event, held.results, at_seconds, shown=shown)])


def describe(arguments, held: EventFile, path: Path) -> Outcome:
    """``reentrant describe [--course Blue]`` -- the control description sheets."""
    wanted = arguments.value("course")
    if wanted:
        course = held.event.courses.require(wanted)
        return Outcome(0, description_sheet(course, held.event.controls).split("\n"))
    if not len(held.event.courses):
        return Outcome(1, ["there are no courses yet"])
    return Outcome(0, all_sheets(held.event.courses, held.event.controls).split("\n"))


def collect(arguments, held: EventFile, path: Path) -> Outcome:
    """``reentrant collect`` -- the list for whoever picks the controls up."""
    rows = collection_list(held.event.courses, held.event.controls)
    if not rows:
        return Outcome(1, ["there are no controls out"])
    lines = [heading("controls to collect", 66)]
    lines.append(table([
        {"key": "code", "title": "code", "align": "right"},
        {"key": "position", "title": "position"},
        {"key": "used", "title": "used by"},
    ], [{"code": row["code"], "position": row["position"],
         "used": ", ".join(row["courses"]) or "no course"} for row in rows]))
    lines.append("")
    lines.append(plural(len(rows), "control") + " to collect")
    return Outcome(0, lines)


def serve_http(arguments, held: EventFile, path: Path) -> Outcome:
    """``reentrant serve --port 8080`` -- answer http until stopped."""
    port = arguments.number("port", 0) or 0
    context = Context.from_file(held, path)
    server = serve(build_router(), context, port=port)
    host, bound = server.server_address[0], server.server_address[1]
    outcome = Outcome(0, [f"listening on http://{host}:{bound}",
                          f"{len(paths())} routes; stop with control-c"])
    outcome.server = server  # type: ignore[attr-defined]
    return outcome


def write_up(arguments, held: EventFile, path: Path) -> Outcome:
    """``reentrant report [--note "..."]`` -- the organiser's write-up."""
    if not held.results:
        return Outcome(1, ["nothing has been downloaded yet"])
    notes = [value for value in [arguments.value("note")] if value]
    report = build_report(held.event, held.results, notes=notes)
    return Outcome(0, render_report(report).split("\n"))


def callup(arguments, held: EventFile, path: Path) -> Outcome:
    """``reentrant callup --at 10:03:00`` -- who should be in which box now."""
    now = parse_time_of_day(arguments.value("at", "10:00:00") or "10:00:00", "at")
    rows = call_up(held.event.entries.all(), now,
                   course_of=held.event.entry_course)
    if not rows:
        return Outcome(0, [f"nobody is due in the next few minutes at "
                           f"{format_time_of_day(now)}"])
    lines = [heading(f"call up at {format_time_of_day(now)}", 66)]
    lines.append(table([
        {"key": "stage", "title": "box"},
        {"key": "away", "title": "min", "align": "right"},
        {"key": "start", "title": "start"},
        {"key": "name", "title": "name"},
        {"key": "course", "title": "course"},
    ], [{"stage": row.stage, "away": row.minutes_away,
         "start": format_time_of_day(row.start_seconds),
         "name": row.name, "course": row.course} for row in rows]))
    return Outcome(0, lines)


def hire(arguments, held: EventFile, path: Path) -> Outcome:
    """``reentrant hire [--lend 300111 --to ENT-0042] [--back 300111]``

    Without arguments it prints the box: what is in it, what is out, and who
    has it. The box itself is not kept in the event file -- it belongs to the
    club rather than to one fixture -- so this reads and writes the list on the
    command line and prints the state it leaves behind.
    """
    box = HireBox(owned=[int(card) for card in (arguments.value("owned", "") or "").split(",")
                         if card.strip().isdigit()])
    at_seconds = parse_time_of_day(arguments.value("at", "10:00:00") or "10:00:00", "at")

    lend = arguments.value("lend")
    if lend:
        entry = held.event.entries.require(arguments.require("to"))
        if int(lend) not in box.owned:
            box.owned = sorted(set(box.owned) | {int(lend)})
        box.lend(int(lend), entry.reference, entry.competitor.listed_name, at_seconds)

    back = arguments.value("back")
    if back:
        if box.out_on(int(back)) is None:
            return Outcome(1, [f"card {back} is not out"])
        box.take_back(int(back), at_seconds)

    told = box.summary()
    lines = [heading("hire cards", 66),
             f"{told['owned']} owned, {told['out']} out, {told['available']} in the box"]
    if box.still_out():
        lines.append("")
        lines.append(table([
            {"key": "card", "title": "card", "align": "right"},
            {"key": "name", "title": "name"},
            {"key": "out", "title": "out"},
        ], [hire.to_dict() for hire in box.still_out()]))
    return Outcome(0, lines)
