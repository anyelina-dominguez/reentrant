"""Getting courses in and out.

Courses are drawn in a mapping package -- OCAD, Condes, Purple Pen -- and
arrive here as a file. The universal lowest common denominator, and the one
every package can write, is a plain text list:

    ; comment
    Blue: S1 101 102 103 F1
    Green: S1 101 103 F1
    Score,3600,10,10: 101 102 103 104

and a control file:

    101 SK 12345 67890 210 boulder
    102 SK 12800 67900 240 northern:knoll/foot

That is what this module reads and writes. It is not a course-planning format
and does not try to be: there is no map, no printing information and no course
overprint. It is enough to get the codes, the positions and the order across
between one person's laptop and another's, which is the actual problem.
"""

from __future__ import annotations

from ..errors import ValidationError
from ..geo.grid import parse as parse_grid
from ..util.order import sorted_by
from ..util.validate import require_str
from .control import Control, ControlSet
from .course import Course, CourseSet
from .descriptions import parse_description


def read_controls(text: str) -> tuple[ControlSet, list[dict[str, object]]]:
    """Read a control file. Returns the set and every line it could not use."""
    controls = ControlSet()
    rejected: list[dict[str, object]] = []

    for number, raw in enumerate(str(text).split("\n"), start=1):
        line = raw.split(";", 1)[0].strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            rejected.append({"line": number, "text": raw.strip(), "reason": "too few fields"})
            continue
        code, rest = parts[0], parts[1:]

        # The grid reference is however many fields it takes: letters plus two
        # numbers, or one bare pair. Anything after it is height then description.
        position = None
        used = 0
        for take in (3, 2, 1):
            if len(rest) >= take:
                try:
                    position = parse_grid(" ".join(rest[:take]))
                    used = take
                    break
                except ValidationError:
                    continue
        if position is None:
            rejected.append({"line": number, "text": raw.strip(), "reason": "no grid reference"})
            continue

        tail = rest[used:]
        height = None
        if tail:
            try:
                height = float(tail[0])
                tail = tail[1:]
            except ValueError:
                height = None

        described = None
        if tail:
            try:
                described = parse_description(" ".join(tail))
            except ValidationError as error:
                rejected.append({"line": number, "text": raw.strip(), "reason": error.message})
                continue

        try:
            controls.add(Control(code=code, position=position, description=described, height=height))
        except Exception as error:  # noqa: BLE001 - one bad line must not lose the file
            rejected.append({"line": number, "text": raw.strip(),
                             "reason": getattr(error, "message", str(error))})
    return controls, rejected


def write_controls(controls: ControlSet) -> str:
    """Write a control file that :func:`read_controls` reads back."""
    lines = ["; code  position  height  description"]
    for control in controls.all():
        parts = [control.code, str(control.position)]
        if control.height is not None:
            parts.append(f"{control.height:g}")
        if control.description is not None:
            described = control.description
            head = ":".join(filter(None, [described.which, described.appearance, described.feature]))
            parts.append(head + (f"/{described.location}" if described.location else ""))
        lines.append(" ".join(parts))
    return "\n".join(lines) + "\n"


def read_courses(text: str) -> tuple[CourseSet, list[dict[str, object]]]:
    """Read a course file."""
    courses = CourseSet()
    rejected: list[dict[str, object]] = []

    for number, raw in enumerate(str(text).split("\n"), start=1):
        line = raw.split(";", 1)[0].strip()
        if not line:
            continue
        if ":" not in line:
            rejected.append({"line": number, "text": raw.strip(), "reason": "no colon"})
            continue
        head, _, tail = line.partition(":")
        codes = tail.split()
        if not codes:
            rejected.append({"line": number, "text": raw.strip(), "reason": "no controls"})
            continue

        name, *scoring = [piece.strip() for piece in head.split(",")]
        try:
            if scoring:
                limit = int(scoring[0])
                points = int(scoring[1]) if len(scoring) > 1 else 10
                penalty = int(scoring[2]) if len(scoring) > 2 else 10
                course = Course(name=name, codes=codes, kind="score",
                                time_limit_seconds=limit, points_per_control=points,
                                penalty_per_minute=penalty)
            else:
                course = Course(name=name, codes=codes)
            courses.add(course)
        except Exception as error:  # noqa: BLE001
            rejected.append({"line": number, "text": raw.strip(),
                             "reason": getattr(error, "message", str(error))})
    return courses, rejected


def write_courses(courses: CourseSet) -> str:
    """Write a course file."""
    lines = ["; name[,limit,points,penalty]: codes"]
    for course in sorted_by(courses.all(), "name"):
        head = course.name
        if course.is_scored:
            head = ",".join([course.name, str(course.time_limit_seconds or 0),
                             str(course.points_per_control or 0),
                             str(course.penalty_per_minute or 0)])
        lines.append(f"{head}: {' '.join(course.codes)}")
    return "\n".join(lines) + "\n"


def read_pair(control_text: str, course_text: str) -> dict[str, object]:
    """Read both files and say what came of it."""
    controls, control_problems = read_controls(require_str(control_text, "controls", min_len=0))
    courses, course_problems = read_courses(require_str(course_text, "courses", min_len=0))
    missing = sorted({code for course in courses.all()
                      for code in course.missing_controls(controls)})
    return {
        "controls": controls,
        "courses": courses,
        "rejected": control_problems + course_problems,
        "missing": missing,
    }
