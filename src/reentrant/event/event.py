"""An event: everything on the day, in one object.

The piece that is easy to miss is ``class_courses``: the mapping from age class
to course. A competitor enters a **class**; they run a **course**; and which
course a class runs is a decision the organiser makes and changes, sometimes on
the morning, when it turns out only two people entered W80.

Holding that mapping here rather than on the entry means changing it changes
every affected entry at once, which is what an organiser expects when they
merge two classes at eight in the morning.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..courses.control import ControlSet
from ..courses.course import CourseSet
from ..entries.competitor import Entry, EntryList
from ..errors import NotFoundError, RuleError, ValidationError
from ..util.order import sorted_by
from ..util.times import parse_time_of_day
from ..util.validate import optional, require_int, require_mapping, require_str


@dataclass
class Event:
    """One fixture."""

    name: str
    date: str
    controls: ControlSet = field(default_factory=ControlSet)
    courses: CourseSet = field(default_factory=CourseSet)
    entries: EntryList = field(default_factory=EntryList)
    class_courses: dict[str, str] = field(default_factory=dict)
    venue: str = ""
    organiser: str = ""
    zero_seconds: int | None = None

    def __post_init__(self) -> None:
        self.name = require_str(self.name, "name", max_len=80)
        self.date = require_str(self.date, "date", max_len=10, pattern=r"\d{4}-\d{2}-\d{2}")
        self.venue = require_str(self.venue, "venue", min_len=0, max_len=80)
        self.organiser = require_str(self.organiser, "organiser", min_len=0, max_len=80)
        self.class_courses = {
            str(code).upper(): require_str(course, "course", max_len=40)
            for code, course in require_mapping(self.class_courses, "class_courses").items()
        }
        self.zero_seconds = optional(self.zero_seconds,
                                     lambda v: require_int(v, "zero_seconds", minimum=0, maximum=86_399))

    @property
    def year(self) -> int:
        return int(self.date[:4])

    # -- classes and courses -----------------------------------------------

    def course_for_class(self, class_code: str) -> str:
        """Which course a class runs."""
        wanted = str(class_code).upper()
        course = self.class_courses.get(wanted)
        if course is None:
            raise NotFoundError("that class is not running a course", class_code=wanted)
        return course

    def classes_on(self, course: str) -> list[str]:
        """Which classes run a course, which is what the results are grouped by."""
        return sorted(code for code, name in self.class_courses.items() if name == str(course))

    def set_class_course(self, class_code: str, course: str) -> None:
        wanted = str(class_code).upper()
        self.courses.require(course)
        self.class_courses[wanted] = course

    def merge_classes(self, into: str, *others: str) -> list[str]:
        """Point several classes at the course another one runs.

        The eight-in-the-morning operation: only two people entered W80, so run
        them on the W75 course and score them together.
        """
        target = self.course_for_class(into)
        moved = []
        for code in others:
            self.class_courses[str(code).upper()] = target
            moved.append(str(code).upper())
        return sorted(moved)

    # -- entries -----------------------------------------------------------

    def entry_course(self, entry: Entry) -> str:
        """The course an entry actually runs, from its class if it has no course."""
        if entry.course:
            return entry.course
        return self.course_for_class(entry.class_code)

    def check_ready(self) -> list[str]:
        """Everything that would stop the event running, as plain sentences."""
        problems: list[str] = []

        for note in self.controls.conflicts():
            problems.append(
                f"controls {note['codes'][0]} and {note['codes'][1]} are only {note['metres']} m apart")

        for course in self.courses.all():
            missing = course.missing_controls(self.controls)
            if missing:
                problems.append(f"course {course.name} uses controls that are not out: "
                                + ", ".join(missing))
            repeated = course.repeated_controls()
            if repeated:
                problems.append(f"course {course.name} visits {', '.join(repeated)} twice")

        for class_code, course in sorted(self.class_courses.items()):
            if self.courses.get(course) is None:
                problems.append(f"class {class_code} is set to run {course}, which does not exist")

        for entry in self.entries.all():
            if entry.class_code not in self.class_courses:
                problems.append(f"entry {entry.reference} is in {entry.class_code}, "
                                "which is not running a course")

        for entry in self.entries.ineligible(self.year):
            problems.append(f"entry {entry.reference} is in {entry.class_code}, "
                            "which that competitor may not run")

        return problems

    def require_ready(self) -> None:
        problems = self.check_ready()
        if problems:
            raise RuleError("the event is not ready", problems=problems)

    def start_seconds_for(self, entry: Entry) -> int | None:
        """The time an entry is due to start, if they have one."""
        return entry.start_seconds

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "date": self.date,
            "venue": self.venue,
            "organiser": self.organiser,
            "zero_seconds": self.zero_seconds,
            "class_courses": dict(sorted(self.class_courses.items())),
            "controls": self.controls.to_list(),
            "courses": self.courses.to_list(),
            "entries": self.entries.to_list(),
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "Event":
        data = require_mapping(raw, "event")
        return cls(
            name=str(data.get("name", "")),
            date=str(data.get("date", "")),
            venue=str(data.get("venue") or ""),
            organiser=str(data.get("organiser") or ""),
            zero_seconds=data.get("zero_seconds"),  # type: ignore[arg-type]
            class_courses=dict(data.get("class_courses") or {}),  # type: ignore[arg-type]
            controls=ControlSet.from_list(list(data.get("controls") or [])),  # type: ignore[arg-type]
            courses=CourseSet.from_list(list(data.get("courses") or [])),  # type: ignore[arg-type]
            entries=EntryList.from_list(list(data.get("entries") or [])),  # type: ignore[arg-type]
        )


def parse_zero(text: str) -> int:
    """The event's zero time, from which start times are counted."""
    return parse_time_of_day(text, "zero time")


def summary(event: Event) -> dict[str, object]:
    """The line at the top of every printout."""
    by_course: dict[str, int] = {}
    for entry in event.entries.all():
        # The course an entry *runs*, not the one it names: an entry to a class
        # has no course of its own, and counting those as blank made the
        # summary say every course was empty.
        try:
            course = event.entry_course(entry)
        except NotFoundError:
            course = entry.course
        by_course[course] = by_course.get(course, 0) + 1
    return {
        "name": event.name,
        "date": event.date,
        "venue": event.venue,
        "controls": len(event.controls),
        "courses": len(event.courses),
        "entries": len(event.entries),
        "classes": len(event.class_courses),
        "by_course": [{"course": name, "entries": by_course.get(name, 0)}
                      for name in sorted_by(event.courses.names(), lambda value: value)],
    }
