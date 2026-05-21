#!/usr/bin/env python3
"""Walk a planner's courses the way a controller would.

    python3 examples/plan_check.py

Builds a small event in memory and prints everything a controller would say
about it: the controls that are too close together, the dog-legs, the legs that
are too short, and the courses that start to the same control.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from reentrant.courses.control import Control, ControlSet  # noqa: E402
from reentrant.courses.course import Course, CourseSet  # noqa: E402
from reentrant.courses.descriptions import parse_description  # noqa: E402
from reentrant.courses.planning import check_event, summary  # noqa: E402
from reentrant.courses.sheets import description_sheet  # noqa: E402
from reentrant.geo.grid import parse as grid  # noqa: E402
from reentrant.util.text import heading  # noqa: E402

PLACES = [
    ("S1", "SK 12000 67000", 200.0, None),
    ("101", "SK 12000 67500", 215.0, "knoll"),
    ("102", "SK 12000 67100", 205.0, "boulder"),      # straight back: a dog-leg
    ("103", "SK 12040 67100", 205.0, "boulder"),      # forty metres from 102
    ("104", "SK 12800 67900", 250.0, "northern:re-entrant/foot"),
    ("F1", "SK 12100 67050", 202.0, None),
]

controls = ControlSet()
for code, position, height, described in PLACES:
    controls.add(Control(
        code=code,
        position=grid(position),
        description=None if described is None else parse_description(described),
        height=height,
    ))

courses = CourseSet()
courses.add(Course("Blue", ["S1", "101", "102", "104", "F1"]))
courses.add(Course("Green", ["S1", "101", "103", "F1"]))

print(heading("controls", 66))
for problem in controls.conflicts():
    print(f"  {problem['codes'][0]} and {problem['codes'][1]}: "
          f"{problem['metres']} m apart -- {problem['reason']}")
if not controls.conflicts():
    print("  nothing too close")
print()

notes = check_event(courses, controls)
print(heading("courses", 66))
for note in notes:
    print(f"  [{note.kind}] {note.course}: {note.message}")
print()
print("  " + ", ".join(f"{kind}: {count}" for kind, count in summary(notes).items()))
print()

for course in courses.all():
    print(description_sheet(course, controls))
    print()
