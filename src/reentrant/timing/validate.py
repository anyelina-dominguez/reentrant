"""Whether a run counts.

This is the module the whole system exists for, and the rule it implements is
one sentence long:

    the punches must contain the course's controls, in order, as a subsequence.

Everything else follows from that sentence and is worth spelling out, because
every one of these has been argued about in a car park:

* **Extra punches do not matter.** A runner who punches somebody else's control
  on the way past has an extra punch. It is ignored. There is no penalty for it
  and never has been.
* **The order matters, the times do not.** A punch list of 101, 103, 102, 103
  contains 101, 102, 103 in order, so it is a valid run of that course -- the
  runner overshot to 103, came back to 102, and went on to 103 again. The
  second 103 is the one that counts.
* **The first punch that fits is the one that counts.** Which is what makes the
  paragraph above work, and what makes the split times come out right.
* **A missing finish is not a mispunch.** It is a run that cannot be timed,
  which is a different thing and is reported differently, because the fix is
  different: a mispunch is final, a missing finish is usually a download
  problem that the organiser can resolve.

A score course is scored rather than checked: any punch at a listed control
counts once, whatever the order, and the only failure is coming back late.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..courses.course import Course
from ..util.order import sorted_by
from ..util.validate import require_int
from .punch import CardRead, Punch

#: What became of a run.
OUTCOMES = ["ok", "mispunch", "no-finish", "no-start", "over-time"]


@dataclass
class RunCheck:
    """The verdict on one card against one course."""

    outcome: str
    matched: list[Punch] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)
    extras: list[Punch] = field(default_factory=list)
    points: int | None = None
    penalty: int | None = None

    @property
    def ok(self) -> bool:
        return self.outcome == "ok"

    @property
    def counts(self) -> bool:
        """Whether the run goes in the results as a placed run."""
        return self.outcome == "ok"

    def to_dict(self) -> dict[str, object]:
        return {
            "outcome": self.outcome,
            "matched": [punch.code for punch in self.matched],
            "missing": list(self.missing),
            "extras": [punch.code for punch in self.extras],
            "points": self.points,
            "penalty": self.penalty,
        }


def check_order(required: list[str], punches: list[Punch]) -> tuple[list[Punch], list[str], list[Punch]]:
    """Match a course's controls against a punch list, in order.

    Returns ``(matched, missing, extras)``. ``matched`` holds one punch per
    control that was found, in course order; ``missing`` the codes that were
    not; ``extras`` every punch the course did not ask for.

    The walk is greedy and single-pass, which is both the standard rule and the
    only one that gives a stable answer: taking the *first* punch that fits at
    each step means the same card always produces the same splits.
    """
    matched: list[Punch] = []
    missing: list[str] = []
    used: set[int] = set()

    position = 0
    for code in required:
        found = None
        for index in range(position, len(punches)):
            if punches[index].code == code:
                found = index
                break
        if found is None:
            missing.append(code)
            continue
        matched.append(punches[found])
        used.add(found)
        position = found + 1

    extras = [punch for index, punch in enumerate(punches) if index not in used]
    return matched, missing, extras


def check_run(course: Course, read: CardRead, *,
              start_seconds: int | None = None,
              finish_seconds: int | None = None) -> RunCheck:
    """Check one card against one course."""
    if course.is_scored:
        return _check_score(course, read, start_seconds=start_seconds, finish_seconds=finish_seconds)

    opened = start_seconds if start_seconds is not None else read.start_seconds
    closed = finish_seconds if finish_seconds is not None else read.finish_seconds
    punches = read.since_start(opened)

    matched, missing, extras = check_order(course.control_codes, punches)
    if missing:
        return RunCheck("mispunch", matched=matched, missing=missing, extras=extras)
    if opened is None:
        return RunCheck("no-start", matched=matched, extras=extras)
    if closed is None:
        return RunCheck("no-finish", matched=matched, extras=extras)
    return RunCheck("ok", matched=matched, extras=extras)


def _check_score(course: Course, read: CardRead, *,
                 start_seconds: int | None = None,
                 finish_seconds: int | None = None) -> RunCheck:
    """Score a score course: points for controls, penalty for coming back late."""
    opened = start_seconds if start_seconds is not None else read.start_seconds
    closed = finish_seconds if finish_seconds is not None else read.finish_seconds
    punches = read.since_start(opened)

    wanted = set(course.control_codes)
    matched: list[Punch] = []
    seen: set[str] = set()
    extras: list[Punch] = []
    for punch in punches:
        if punch.code in wanted and punch.code not in seen:
            matched.append(punch)
            seen.add(punch.code)
        else:
            extras.append(punch)

    per_control = course.points_per_control or 0
    points = len(matched) * per_control

    if opened is None:
        return RunCheck("no-start", matched=matched, extras=extras, points=points)
    if closed is None:
        return RunCheck("no-finish", matched=matched, extras=extras, points=points)

    from ..util.times import difference

    elapsed = difference(opened, closed)
    limit = course.time_limit_seconds or 0
    over = max(0, elapsed - limit)
    # Penalties are per minute or part of a minute, which is the usual wording
    # and is harsher than it looks: one second late costs a whole minute.
    minutes_late = (over + 59) // 60
    penalty = minutes_late * (course.penalty_per_minute or 0)

    return RunCheck(
        "over-time" if over > 0 else "ok",
        matched=matched,
        extras=extras,
        points=points - penalty,
        penalty=penalty,
    )


def splits(matched: list[Punch], start_seconds: int,
           finish_seconds: int | None = None) -> list[dict[str, object]]:
    """Leg times from the matched punches.

    One row per control, plus a last row for the run in to the finish when a
    finish time is given. Each row carries the time at the control and the leg
    time from the one before.
    """
    require_int(start_seconds, "start_seconds", minimum=0, maximum=86_399)
    rows: list[dict[str, object]] = []
    previous = start_seconds
    for number, punch in enumerate(matched, start=1):
        from ..util.times import difference

        leg = difference(previous, punch.at_seconds)
        rows.append({
            "number": number,
            "code": punch.code,
            "at_seconds": punch.at_seconds,
            "elapsed_seconds": difference(start_seconds, punch.at_seconds),
            "leg_seconds": leg,
        })
        previous = punch.at_seconds
    if finish_seconds is not None:
        from ..util.times import difference

        rows.append({
            "number": len(matched) + 1,
            "code": "F1",
            "at_seconds": finish_seconds,
            "elapsed_seconds": difference(start_seconds, finish_seconds),
            "leg_seconds": difference(previous, finish_seconds),
        })
    return rows


def missing_report(check: RunCheck, course: Course) -> str:
    """The line the download tent reads out to the runner."""
    if check.ok:
        return "clear"
    if check.outcome == "mispunch":
        numbering = course.numbering()
        parts = [f"{numbering.get(code, 0)} ({code})" for code in check.missing]
        return "missing control " + ", ".join(parts)
    if check.outcome == "no-finish":
        return "no finish punch"
    if check.outcome == "no-start":
        return "no start time"
    return "over time"


def order_of_visit(read: CardRead, start_seconds: int | None = None) -> list[str]:
    """The codes in the order they were punched, for the download printout."""
    return [punch.code for punch in sorted_by(read.since_start(start_seconds), "at_seconds", "code")]
