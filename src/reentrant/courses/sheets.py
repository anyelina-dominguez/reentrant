"""Control description sheets.

The slip a runner straps to their arm. It is a grid, one row per control, and
the columns are the ones :mod:`reentrant.courses.descriptions` describes. The
pictogram version needs a font nobody has; this is the text version, which is
what a club event prints and what goes on the back of the map.

The header is part of the standard and people rely on it: course name, length
in kilometres, climb in metres. A runner who cannot see the length on the slip
will ask, and the answer had better match the results.
"""

from __future__ import annotations

from ..courses.control import ControlSet
from ..courses.course import Course, CourseSet
from ..util.text import heading, pad_left, pad_right
from ..util.validate import require_int

#: The width of the description column on the printed slip.
DESCRIPTION_WIDTH = 46


def _header(course: Course, controls: ControlSet) -> list[str]:
    if course.is_scored:
        limit = (course.time_limit_seconds or 0) // 60
        return [f"{course.name}   score, {limit} minutes"]
    metres = course.length_metres(controls)
    climb = course.climb_metres(controls)
    tail = f"{metres / 1000:.1f} km"
    if climb is not None:
        tail += f", {climb} m climb"
    return [f"{course.name}   {tail}   {course.size} controls"]


def description_sheet(course: Course, controls: ControlSet) -> str:
    """One course's slip."""
    lines = _header(course, controls)
    lines.append("-" * (DESCRIPTION_WIDTH + 8))

    if course.is_scored:
        for code in course.control_codes:
            control = controls.require(code)
            described = "" if control.description is None else control.description.text()
            lines.append(f"{pad_left(code, 5)}  {pad_right(described, DESCRIPTION_WIDTH)}".rstrip())
        return "\n".join(lines)

    numbering = course.numbering()
    for code in course.codes:
        control = controls.require(code)
        if control.is_start:
            lines.append("    S  start")
            continue
        if control.is_finish:
            lines.append("    F  finish, follow the tapes")
            continue
        described = "" if control.description is None else control.description.text()
        lines.append(f"{pad_left(numbering[code], 3)}  {pad_left(code, 4)}  "
                     f"{pad_right(described, DESCRIPTION_WIDTH)}".rstrip())
    return "\n".join(lines)


def all_sheets(courses: CourseSet, controls: ControlSet) -> str:
    """Every course's slip, one after another, for printing in one go."""
    blocks = []
    for course in courses.all():
        blocks.append(description_sheet(course, controls))
    return "\n\n".join(blocks)


def control_card(controls: ControlSet, *, per_row: int = 6) -> str:
    """The list of every control and its description, for the collectors.

    Nothing to do with the runners: this is what the people picking the kites up
    at the end of the day carry, so it is by code rather than by course.
    """
    require_int(per_row, "per_row", minimum=1, maximum=12)
    lines = [heading("controls out", 66)]
    for control in controls.all():
        if control.is_start or control.is_finish:
            continue
        described = "" if control.description is None else control.description.text()
        lines.append(f"{pad_left(control.code, 5)}  {pad_right(str(control.position), 18)}  {described}".rstrip())
    return "\n".join(lines)


def collection_list(courses: CourseSet, controls: ControlSet) -> list[dict[str, object]]:
    """Every control with the courses that used it, for the sweep.

    A control used by no course is still out there and still has to be
    collected, which is why it appears with an empty list rather than being
    left off.
    """
    rows = []
    for control in controls.all():
        if control.is_start or control.is_finish:
            continue
        rows.append({
            "code": control.code,
            "position": str(control.position),
            "courses": courses.using(control.code),
        })
    return rows
