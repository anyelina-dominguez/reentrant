"""Checking a course before it is printed.

None of this is a rule of the sport. It is the list of things a controller
looks for when they walk a planner's course, written down so the planner can
find them first. Every check returns a note rather than raising, because a
planner wants the whole list, and because half of these are judgement calls
that a good course sometimes breaks on purpose.

The checks:

**dog-legs** -- leaving a control on nearly the bearing you arrived on. It
sends runners back past the people coming in, who then follow them. This is the
one controllers care about most.

**short legs** -- under ``SHORT_LEG_METRES``, which on most terrain is not a
navigational problem so much as a queue.

**long legs on a short course** -- a leg that is a large fraction of the whole
course is usually a planning accident on a junior course.

**shared control, different numbers** -- fine, and normal. But a control that
is number 3 on one course and number 3 on another, approached from different
directions, is where mispunches come from, so it is worth a look.

**bunching** -- the first control being the same on several courses puts
everybody in the same place at once.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..util.order import group_by, sorted_by
from .control import ControlSet
from .course import Course, CourseSet

#: A leg shorter than this is worth a second look.
SHORT_LEG_METRES = 100.0

#: Turning less than this at a control is a dog-leg.
DOG_LEG_DEGREES = 30.0

#: A leg longer than this share of the course, on a course under
#: :data:`SHORT_COURSE_METRES`, is probably an accident.
LONG_LEG_SHARE = 0.35
SHORT_COURSE_METRES = 3000.0


@dataclass(frozen=True)
class Note:
    """Something a controller would mention."""

    course: str
    kind: str
    message: str
    where: str = ""

    def to_dict(self) -> dict[str, str]:
        return {"course": self.course, "kind": self.kind, "message": self.message, "where": self.where}


def _turn(incoming: float, outgoing: float) -> float:
    """How far the runner turns at a control, in degrees, 0 to 180.

    Zero means straight back the way they came, 180 means straight on.
    """
    difference = abs((outgoing - incoming + 180) % 360 - 180)
    return 180 - difference


def dog_legs(course: Course, controls: ControlSet) -> list[Note]:
    """Controls where the runner leaves on nearly the bearing they arrived on."""
    legs = course.legs(controls)
    notes = []
    for incoming, outgoing in zip(legs, legs[1:]):
        turn = _turn(incoming.bearing, outgoing.bearing)
        if turn < DOG_LEG_DEGREES:
            notes.append(Note(
                course=course.name,
                kind="dog-leg",
                message=f"leaves control {incoming.finish.code} within {turn:.0f} degrees of the way in",
                where=incoming.finish.code,
            ))
    return notes


def short_legs(course: Course, controls: ControlSet) -> list[Note]:
    return [
        Note(course.name, "short-leg",
             f"leg {leg.number} ({leg.label}) is only {leg.metres:.0f} m", leg.label)
        for leg in course.legs(controls)
        if leg.metres < SHORT_LEG_METRES
    ]


def unbalanced_legs(course: Course, controls: ControlSet) -> list[Note]:
    """Legs that are a large share of a short course."""
    legs = course.legs(controls)
    total = sum(leg.metres for leg in legs)
    if total == 0 or total > SHORT_COURSE_METRES:
        return []
    return [
        Note(course.name, "long-leg",
             f"leg {leg.number} ({leg.label}) is {leg.metres / total:.0%} of the course", leg.label)
        for leg in legs
        if leg.metres / total > LONG_LEG_SHARE
    ]


def check_course(course: Course, controls: ControlSet) -> list[Note]:
    """Every note for one course, worst kind first."""
    notes = dog_legs(course, controls) + short_legs(course, controls) + unbalanced_legs(course, controls)
    order = {"dog-leg": 0, "short-leg": 1, "long-leg": 2}
    return sorted_by(notes, lambda note: (order.get(note.kind, 9), note.where))


def shared_numbers(courses: CourseSet) -> list[Note]:
    """Controls carrying the same number on more than one course.

    Not wrong, but it is where a runner reading the wrong description sheet
    ends up, so a controller looks at each one.
    """
    numbered: dict[tuple[str, int], list[str]] = {}
    for course in courses.all():
        for code, number in course.numbering().items():
            numbered.setdefault((code, number), []).append(course.name)
    notes = []
    for (code, number), names in numbered.items():
        if len(names) > 1:
            notes.append(Note(
                course=", ".join(sorted(names)),
                kind="shared-number",
                message=f"control {code} is number {number} on {len(names)} courses",
                where=code,
            ))
    return sorted_by(notes, "where")


def bunching(courses: CourseSet) -> list[Note]:
    """Courses whose first control is the same, which crowds the start."""
    firsts = group_by(
        [course for course in courses.all() if not course.is_scored and course.control_codes],
        lambda course: course.control_codes[0],
    )
    return sorted_by([
        Note(course=", ".join(sorted(course.name for course in sharing)),
             kind="bunching",
             message=f"{len(sharing)} courses start to control {code}",
             where=code)
        for code, sharing in firsts.items() if len(sharing) > 1
    ], "where")


def check_event(courses: CourseSet, controls: ControlSet) -> list[Note]:
    """Every note for every course, plus the ones about the set as a whole."""
    notes: list[Note] = []
    for course in courses.all():
        notes.extend(check_course(course, controls))
    notes.extend(shared_numbers(courses))
    notes.extend(bunching(courses))
    return notes


def summary(notes: list[Note]) -> dict[str, int]:
    """How many of each kind, for the line at the top of the report."""
    counts: dict[str, int] = {}
    for note in notes:
        counts[note.kind] = counts.get(note.kind, 0) + 1
    return dict(sorted(counts.items()))
