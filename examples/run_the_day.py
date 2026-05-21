#!/usr/bin/env python3
"""A whole event, from the entry list to the results.

    python3 examples/run_the_day.py

Nothing is read from disc and nothing is written: the event is built in memory,
five runners are put round two courses, and the sheets are printed. It is the
shortest thing that shows how the pieces fit together.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from reentrant.courses.control import Control, ControlSet  # noqa: E402
from reentrant.courses.course import Course, CourseSet  # noqa: E402
from reentrant.entries.importer import parse_entries  # noqa: E402
from reentrant.event.download import process, results_from  # noqa: E402
from reentrant.event.event import Event  # noqa: E402
from reentrant.event.report import build_report, render_report  # noqa: E402
from reentrant.geo.grid import parse as grid  # noqa: E402
from reentrant.reports.sheets import results_sheet, start_list_sheet  # noqa: E402
from reentrant.starts.draw import apply_draw, draw_course, start_list  # noqa: E402
from reentrant.timing.punch import read_from_pairs  # noqa: E402
from reentrant.util.times import parse_time_of_day  # noqa: E402

ENTRIES = """surname,first name,club,class,si card,yob,gender
Okonkwo,Ada,DPO,W45,205431,1981,W
Bergstrom,Nils,SYO,M21,205999,1990,M
Cai,Jo,HALO,M21,300111,2000,M
Dunn,Kim,DPO,M21,300222,1995,M
Eze,Lin,SYO,W45,300333,1978,W
"""

CARDS = [
    (205431, "10:00:00", "10:31:12", [("101", "10:04:11"), ("102", "10:18:44")]),
    (300333, "10:02:00", "10:36:40", [("101", "10:07:00"), ("102", "10:24:00")]),
    (205999, "10:04:00", "10:33:10", [("101", "10:08:30"), ("103", "10:21:00")]),
    (300111, "10:06:00", "10:41:00", [("101", "10:12:00")]),          # missed 103
    (300222, "10:08:00", "10:38:20", [("101", "10:13:00"), ("103", "10:26:00")]),
]

controls = ControlSet()
for code, east, north in [("S1", 12000, 67000), ("101", 12300, 67400),
                          ("102", 12900, 67800), ("103", 13400, 67200),
                          ("F1", 12100, 67050)]:
    controls.add(Control(code, grid(f"SK {east} {north}"), height=200.0))

courses = CourseSet()
courses.add(Course("Blue", ["S1", "101", "102", "F1"]))
courses.add(Course("Green", ["S1", "101", "103", "F1"]))

event = Event(name="Longshaw club fixture", date="2026-05-09", controls=controls,
              courses=courses, class_courses={"W45": "Blue", "M21": "Green"},
              venue="Longshaw")

imported = parse_entries(ENTRIES, entries=event.entries)
print(f"{len(imported.added)} entries read, {len(imported.rejected)} rejected")
print()

draws = []
for course in event.courses.all():
    runners = [entry for entry in event.entries.all()
               if event.entry_course(entry) == course.name]
    drawn = draw_course(course.name, runners,
                        first_seconds=parse_time_of_day("10:00:00"),
                        interval_seconds=120, seed=event.name)
    for entry in apply_draw(runners, drawn):
        event.entries.update(entry)
    draws.append(drawn)

print(start_list_sheet(event, start_list(draws)))
print()

downloads = []
for card, start, finish, punches in CARDS:
    read = read_from_pairs(card, punches, start=start, finish=finish)
    download = process(event, read)
    downloads.append(download)
    print(f"{download.card}  {download.name or '-':<20} "
          f"{'clear' if download.ok else download.problem}")
print()

results = results_from(event, downloads)
print(results_sheet(event, results))
print()
print(render_report(build_report(event, results)))
