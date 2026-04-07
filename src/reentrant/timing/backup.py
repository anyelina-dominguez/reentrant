"""Backup punching.

Every control carries a pin punch as well as the electronic box, and the map
has a grid of little squares for them. When a box fails -- flat battery, water
inside, knocked into a stream -- the pin marks are what proves the runner was
there.

Reading them is a human job: somebody looks at the map and types in which
squares have holes. What this module does is put that reading together with the
electronic one, and it takes the **union**: a control counts as visited if the
box recorded it *or* there is a pin mark in the right square.

The rule that makes this safe is that backup evidence is per control and is
recorded as a decision with a name against it, exactly like the corrections in
:mod:`reentrant.timing.repair`. A runner does not get to tell the desk which
squares are punched; the desk looks.

What backup cannot supply is a **time**. A pin mark says "here", never "at
twenty past". So a run rescued by backup punching has no splits for the
rescued controls, and the module says so rather than inventing them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..courses.course import Course
from ..errors import ConflictError, ValidationError
from ..util.order import sorted_by
from ..util.validate import require_list, require_str
from .punch import CardRead, Punch
from .validate import RunCheck, check_order


@dataclass(frozen=True)
class BackupMark:
    """A pin mark somebody has read off a map."""

    entry: str
    code: str
    box: int
    read_by: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry", require_str(self.entry, "entry", max_len=16))
        object.__setattr__(self, "code", require_str(self.code, "code", max_len=4))
        if not isinstance(self.box, int) or isinstance(self.box, bool) or not 1 <= self.box <= 40:
            raise ValidationError("a backup box is numbered one to forty", box=self.box)
        object.__setattr__(self, "read_by", require_str(self.read_by, "read_by",
                                                        min_len=0, max_len=60))

    def to_dict(self) -> dict[str, object]:
        return {"entry": self.entry, "code": self.code, "box": self.box, "read_by": self.read_by}


@dataclass
class BackupLog:
    """Every pin mark read, for every runner."""

    marks: list[BackupMark] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.marks)

    def add(self, mark: BackupMark) -> BackupMark:
        for held in self.marks:
            if held.entry == mark.entry and held.box == mark.box and held.code != mark.code:
                raise ConflictError("that box already holds a different control",
                                    entry=mark.entry, box=mark.box, held=held.code)
        self.marks.append(mark)
        return mark

    def codes_for(self, entry: str) -> list[str]:
        """Which controls a runner has pin marks for, in box order."""
        mine = [mark for mark in self.marks if mark.entry == str(entry)]
        return [mark.code for mark in sorted_by(mine, "box", "code")]

    def to_list(self) -> list[dict[str, object]]:
        return [mark.to_dict() for mark in sorted_by(self.marks, "entry", "box")]

    @classmethod
    def from_list(cls, rows: list[dict[str, object]]) -> "BackupLog":
        log = cls()
        for row in require_list(rows, "marks"):
            log.add(BackupMark(entry=str(row.get("entry", "")), code=str(row.get("code", "")),
                               box=int(row.get("box", 0)), read_by=str(row.get("read_by") or "")))
        return log


def rescue(course: Course, read: CardRead, backup: list[str], *,
           start_seconds: int | None = None) -> RunCheck:
    """Re-check a run with the pin marks added to the electronic punches.

    The backup marks are inserted into the punch list **in course order** at the
    position the missing control should occupy, because a pin mark carries no
    time and the order is the only thing it can contribute. The result is a
    :class:`RunCheck` whose ``matched`` list holds the real punches only -- the
    rescued controls are in ``missing`` no longer, but they have no punch and so
    no split.
    """
    if course.is_scored:
        raise ValidationError("backup punching does not apply to a score course",
                              course=course.name)

    opened = start_seconds if start_seconds is not None else read.start_seconds
    punches = read.since_start(opened)
    available = set(str(code) for code in backup)

    matched: list[Punch] = []
    missing: list[str] = []
    rescued: list[str] = []
    position = 0

    for code in course.control_codes:
        found = None
        for index in range(position, len(punches)):
            if punches[index].code == code:
                found = index
                break
        if found is not None:
            matched.append(punches[found])
            position = found + 1
        elif code in available:
            rescued.append(code)
        else:
            missing.append(code)

    used = {punch for punch in matched}
    extras = [punch for punch in punches if punch not in used]

    if missing:
        return RunCheck("mispunch", matched=matched, missing=missing, extras=extras)
    if opened is None:
        return RunCheck("no-start", matched=matched, extras=extras)
    if read.finish_seconds is None:
        return RunCheck("no-finish", matched=matched, extras=extras)
    check = RunCheck("ok", matched=matched, extras=extras)
    check.rescued = rescued  # type: ignore[attr-defined]
    return check


def rescued_controls(check: RunCheck) -> list[str]:
    """Which controls a run was rescued on, if any."""
    return list(getattr(check, "rescued", []))


def would_rescue(course: Course, read: CardRead, backup: list[str]) -> bool:
    """Whether the pin marks are enough to turn a mispunch into a run."""
    before = check_order(course.control_codes, read.since_start())
    if not before[1]:
        return False
    return rescue(course, read, backup).ok
