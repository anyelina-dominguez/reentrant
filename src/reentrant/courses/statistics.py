"""Was the course the right length?

Every class has a **target winning time** -- thirty-five minutes for most
adult classes at a club event, less for the youngest and the oldest -- and the
planner works backwards from it to a course length. Afterwards, the controller
checks whether it came out right, and that check is the one piece of feedback a
planner ever gets.

The arithmetic is deliberately blunt:

* the **winning time** against the target, as a ratio;
* the **spread** of the field, because a course where the winner takes half the
  time of the median is a course that punished one mistake too hard;
* the **completion rate**, because a course where a third of the field
  mispunched was too hard for the people on it, whatever the times say.

None of these three is a verdict on its own. Together they are what a
controller writes two sentences about in the event report.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..results.classify import Result, classify
from ..util.num_stats import median_of, percentile_of
from ..util.order import sorted_by
from ..util.times import format_clock
from ..util.validate import require_int, require_number

#: Target winning times in minutes, by class age. The middle of the range a
#: club event aims at; a badge event aims longer and a score event at nothing.
TARGET_MINUTES = {
    10: 20, 12: 25, 14: 30, 16: 35, 18: 40, 20: 40, 21: 35,
    35: 35, 40: 35, 45: 35, 50: 35, 55: 33, 60: 32, 65: 30,
    70: 28, 75: 26, 80: 24, 85: 22, 90: 20, 95: 20,
}

#: A winning time this far either side of target is close enough.
TOLERANCE = 0.20


def target_seconds(class_age: int) -> int:
    """The target winning time for a class, in seconds."""
    require_int(class_age, "class_age", minimum=1, maximum=99)
    if class_age in TARGET_MINUTES:
        return TARGET_MINUTES[class_age] * 60
    nearest = min(TARGET_MINUTES, key=lambda age: abs(age - class_age))
    return TARGET_MINUTES[nearest] * 60


@dataclass
class CourseStatistics:
    """How one course went."""

    course: str
    starters: int
    finishers: int
    winning_seconds: int | None
    median_seconds: int | None
    slowest_seconds: int | None
    target_seconds: int | None = None

    @property
    def completion(self) -> float:
        return 0.0 if self.starters == 0 else round(self.finishers / self.starters, 4)

    @property
    def against_target(self) -> float | None:
        """Winning time over target: 1.0 is exactly right, 1.3 is too long."""
        if self.winning_seconds is None or not self.target_seconds:
            return None
        return round(self.winning_seconds / self.target_seconds, 3)

    @property
    def verdict(self) -> str:
        """One word for the event report."""
        ratio = self.against_target
        if ratio is None:
            return "unknown"
        if ratio > 1 + TOLERANCE:
            return "too long"
        if ratio < 1 - TOLERANCE:
            return "too short"
        return "about right"

    @property
    def spread(self) -> float | None:
        """Median over winning time. Two is ordinary; four is a hard course."""
        if not self.winning_seconds or self.median_seconds is None:
            return None
        return round(self.median_seconds / self.winning_seconds, 3)

    def to_dict(self) -> dict[str, object]:
        return {
            "course": self.course,
            "starters": self.starters,
            "finishers": self.finishers,
            "completion": self.completion,
            "winning": format_clock(self.winning_seconds),
            "winning_seconds": self.winning_seconds,
            "median": format_clock(self.median_seconds),
            "slowest": format_clock(self.slowest_seconds),
            "target": format_clock(self.target_seconds),
            "against_target": self.against_target,
            "spread": self.spread,
            "verdict": self.verdict,
        }


def course_statistics(results: list[Result], *, target: int | None = None) -> CourseStatistics:
    """How one course went, from its results."""
    placed = [row for row in classify(results) if row.placed]
    times = sorted(int(row.seconds) for row in placed if row.seconds is not None)
    starters = sum(1 for row in results if row.outcome != "dns")
    course = results[0].course if results else ""

    return CourseStatistics(
        course=course,
        starters=starters,
        finishers=len(times),
        winning_seconds=times[0] if times else None,
        median_seconds=median_of(times),
        slowest_seconds=times[-1] if times else None,
        target_seconds=target,
    )


def event_statistics(results: list[Result], class_courses: dict[str, str],
                     *, targets: dict[str, int] | None = None) -> list[CourseStatistics]:
    """Every course, with the target taken from the classes running it."""
    from ..util.order import group_by

    by_course = group_by(sorted_by(results, "course"), lambda row: row.course)
    rows = []
    for course, block in by_course.items():
        target = None
        if targets and course in targets:
            target = targets[course]
        else:
            ages = [int(code[1:]) for code, name in class_courses.items()
                    if name == course and code[1:].isdigit()]
            if ages:
                target = round(sum(target_seconds(age) for age in ages) / len(ages))
        rows.append(course_statistics(block, target=target))
    return sorted_by(rows, "course")


def length_for(target: int, pace_seconds_per_km: float) -> int:
    """The course length a target winning time implies, in metres.

    The pace is the winner's expected pace on the terrain, which is the number
    a planner argues about with the controller: five minutes a kilometre on
    open moor, nine in a green forest, and there is no way to compute it.
    """
    require_int(target, "target", minimum=60, maximum=36_000)
    require_number(pace_seconds_per_km, "pace_seconds_per_km", minimum=120, maximum=1800)
    return int(round(target / pace_seconds_per_km * 1000 / 10) * 10)


def implied_pace(metres: int, winning_seconds: int) -> float | None:
    """The pace the winner actually ran, for next time."""
    require_int(metres, "metres", minimum=0)
    if metres <= 0:
        return None
    return round(winning_seconds * 1000 / metres, 1)


def report_lines(rows: list[CourseStatistics]) -> list[str]:
    """The two sentences a controller writes, one course at a time."""
    lines = []
    for row in rows:
        told = row.to_dict()
        lines.append(
            f"{row.course}: won in {told['winning']} against a target of {told['target']} "
            f"({row.verdict}); {row.finishers} of {row.starters} finished"
        )
    return lines
