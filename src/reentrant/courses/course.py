"""Courses: an ordered list of controls, and what that adds up to.

Three kinds, because they are scored differently and the difference reaches all
the way to the results:

``point-to-point``
    the ordinary kind. Visit the controls in the given order. Miss one, or take
    them out of order, and the run does not count.

``score``
    visit what you like in the time allowed, each control worth points, with a
    penalty per minute late back. Order does not matter and neither does
    missing one.

``line``
    a point-to-point course where the route between controls is also fixed --
    used for a string course or a training exercise. Scored as point-to-point
    here; the distinction exists so the map can be printed differently.

The length of a course is the sum of its straight legs. That is not how far
anybody runs, and everybody knows it -- the figure on the results sheet is the
straight-line distance because it is the only one two clubs will agree on.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..errors import RuleError, ValidationError
from ..geo import distance as geo
from ..util.ids import FINISH_CODE, START_CODE
from ..util.order import sorted_by
from ..util.validate import (
    optional, require_int, require_list, require_mapping, require_one_of, require_str,
)
from .control import Control, ControlSet

COURSE_KINDS = ["point-to-point", "score", "line"]


@dataclass(frozen=True)
class Leg:
    """One control to the next."""

    number: int
    start: Control
    finish: Control
    metres: float
    bearing: float

    @property
    def label(self) -> str:
        return f"{self.start.code}-{self.finish.code}"


@dataclass
class Course:
    """A course as the planner drew it."""

    name: str
    codes: list[str]
    kind: str = "point-to-point"
    time_limit_seconds: int | None = None
    points_per_control: int | None = None
    penalty_per_minute: int | None = None

    def __post_init__(self) -> None:
        self.name = require_str(self.name, "name", max_len=40)
        self.kind = require_one_of(self.kind, "kind", COURSE_KINDS)
        self.codes = [str(code).strip() for code in require_list(self.codes, "codes", min_len=1, max_len=200)]
        self.time_limit_seconds = optional(
            self.time_limit_seconds, lambda v: require_int(v, "time_limit_seconds", minimum=60, maximum=86_400))
        self.points_per_control = optional(
            self.points_per_control, lambda v: require_int(v, "points_per_control", minimum=1, maximum=1000))
        self.penalty_per_minute = optional(
            self.penalty_per_minute, lambda v: require_int(v, "penalty_per_minute", minimum=0, maximum=1000))

        if self.kind == "score" and self.time_limit_seconds is None:
            raise ValidationError("a score course needs a time limit", name=self.name)
        if self.kind != "score" and self.points_per_control is not None:
            raise ValidationError("only a score course carries points", name=self.name)

    # -- the shape of the course -------------------------------------------

    @property
    def control_codes(self) -> list[str]:
        """The codes that are actual controls, without the start and finish."""
        return [code for code in self.codes if code not in (START_CODE, FINISH_CODE)]

    @property
    def size(self) -> int:
        return len(self.control_codes)

    @property
    def is_scored(self) -> bool:
        return self.kind == "score"

    def numbering(self) -> dict[str, int]:
        """Control code to its number on the map, for a point-to-point course.

        A score course has no numbering, because there is no order; the map
        prints the codes and the points instead.
        """
        if self.is_scored:
            return {}
        return {code: index for index, code in enumerate(self.control_codes, start=1)}

    def legs(self, controls: ControlSet) -> list[Leg]:
        """Every leg in order, with its length and bearing."""
        if self.is_scored:
            return []
        found = [controls.require(code) for code in self.codes]
        legs = []
        for number, (start, finish) in enumerate(zip(found, found[1:]), start=1):
            legs.append(Leg(
                number=number,
                start=start,
                finish=finish,
                metres=geo.between(start.position, finish.position).metres,
                bearing=geo.bearing(start.position, finish.position),
            ))
        return legs

    def length_metres(self, controls: ControlSet) -> int:
        """Straight-line length, rounded to the ten metres a map can support."""
        if self.is_scored:
            return 0
        points = [controls.require(code).position for code in self.codes]
        return geo.path_length(points).rounded(10)

    def climb_metres(self, controls: ControlSet) -> int | None:
        """Total ascent, to the nearest five metres.

        ``None`` when any control on the course has no height recorded --
        which is the usual state of the start. Printing nought there would be a
        lie, and a course with unknown climb should say so.
        """
        heights = [controls.require(code).height for code in self.codes]
        if any(height is None for height in heights):
            return None
        return int(round(geo.climb([float(height) for height in heights]) / 5) * 5)

    def describe(self, controls: ControlSet) -> list[str]:
        """The description sheet: one line per control, numbered."""
        lines = []
        numbering = self.numbering()
        for code in self.codes:
            control = controls.require(code)
            if control.is_start:
                lines.append("  S  start")
            elif control.is_finish:
                lines.append("  F  finish")
            else:
                lines.append(f"{numbering.get(code, 0):3d} {control.describe()}")
        return lines

    # -- checking ----------------------------------------------------------

    def missing_controls(self, controls: ControlSet) -> list[str]:
        return [code for code in self.codes if code not in controls]

    def repeated_controls(self) -> list[str]:
        """Codes appearing more than once, which no course may do.

        A control visited twice cannot be scored: the punch record has two
        punches at the same code and no way to say which visit was which.
        """
        seen: dict[str, int] = {}
        for code in self.control_codes:
            seen[code] = seen.get(code, 0) + 1
        return sorted(code for code, count in seen.items() if count > 1)

    def check(self, controls: ControlSet) -> None:
        missing = self.missing_controls(controls)
        if missing:
            raise RuleError("that course uses controls that are not out",
                            course=self.name, missing=missing)
        repeated = self.repeated_controls()
        if repeated:
            raise RuleError("that course visits a control twice",
                            course=self.name, repeated=repeated)
        if not self.is_scored:
            if self.codes[0] != START_CODE:
                raise RuleError("a course starts at the start", course=self.name)
            if self.codes[-1] != FINISH_CODE:
                raise RuleError("a course ends at the finish", course=self.name)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "codes": list(self.codes),
            "kind": self.kind,
            "time_limit_seconds": self.time_limit_seconds,
            "points_per_control": self.points_per_control,
            "penalty_per_minute": self.penalty_per_minute,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "Course":
        data = require_mapping(raw, "course")
        return cls(
            name=str(data.get("name", "")),
            codes=list(data.get("codes", [])),  # type: ignore[arg-type]
            kind=str(data.get("kind", "point-to-point")),
            time_limit_seconds=data.get("time_limit_seconds"),  # type: ignore[arg-type]
            points_per_control=data.get("points_per_control"),  # type: ignore[arg-type]
            penalty_per_minute=data.get("penalty_per_minute"),  # type: ignore[arg-type]
        )


@dataclass
class CourseSet:
    """Every course at an event."""

    courses: dict[str, Course] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.courses)

    def add(self, course: Course) -> Course:
        if course.name in self.courses:
            raise ValidationError("there is already a course of that name", name=course.name)
        self.courses[course.name] = course
        return course

    def put(self, course: Course) -> Course:
        self.courses[course.name] = course
        return course

    def require(self, name: str) -> Course:
        course = self.courses.get(require_str(name, "course"))
        if course is None:
            from ..errors import NotFoundError
            raise NotFoundError("no such course", course=name)
        return course

    def get(self, name: str) -> Course | None:
        return self.courses.get(str(name))

    def all(self) -> list[Course]:
        return sorted_by(self.courses.values(), "name")

    def names(self) -> list[str]:
        return [course.name for course in self.all()]

    def using(self, code: str) -> list[str]:
        """Which courses use a control, which is what a planner asks before moving it."""
        return [course.name for course in self.all() if str(code) in course.codes]

    def to_list(self) -> list[dict[str, object]]:
        return [course.to_dict() for course in self.all()]

    @classmethod
    def from_list(cls, rows: list[dict[str, object]]) -> "CourseSet":
        courses = cls()
        for row in rows:
            courses.put(Course.from_dict(row))
        return courses
