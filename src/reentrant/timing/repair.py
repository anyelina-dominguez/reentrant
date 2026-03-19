"""Corrections made at the desk.

Some runs cannot be settled by the card alone, and somebody has to decide.
A control that was found lying in the bracken; a card that failed to record a
punch everybody watched happen; a runner who cut the course and admitted it.
Every one of those is a **decision**, not a calculation, and this module exists
so that decisions are recorded rather than typed over the top of the data.

The rule: **the punches are never edited**. A correction is a separate record
saying who decided what and why. Re-running the results over the same download
with the same corrections gives the same answer, and the original card read is
still there to be argued with.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..errors import ConflictError, ValidationError
from ..results.classify import Result
from ..util.order import sorted_by
from ..util.times import format_clock, parse_clock
from ..util.validate import optional, require_int, require_one_of, require_str

#: What can be decided about a run.
DECISIONS = ["reinstate", "disqualify", "retire", "set-time", "void-control"]


@dataclass(frozen=True)
class Correction:
    """One decision about one run."""

    entry: str
    decision: str
    reason: str
    by: str = ""
    seconds: int | None = None
    code: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "entry", require_str(self.entry, "entry", max_len=16))
        object.__setattr__(self, "decision", require_one_of(self.decision, "decision", DECISIONS))
        object.__setattr__(self, "reason", require_str(self.reason, "reason", max_len=200))
        object.__setattr__(self, "by", require_str(self.by, "by", min_len=0, max_len=60))
        if self.seconds is not None:
            object.__setattr__(self, "seconds", require_int(self.seconds, "seconds", minimum=0))
        if self.decision == "set-time" and self.seconds is None:
            raise ValidationError("setting a time needs a time", entry=self.entry)
        if self.decision == "void-control" and not self.code:
            raise ValidationError("voiding a control needs the control", entry=self.entry)

    def to_dict(self) -> dict[str, object]:
        return {
            "entry": self.entry,
            "decision": self.decision,
            "reason": self.reason,
            "by": self.by,
            "seconds": self.seconds,
            "time": None if self.seconds is None else format_clock(self.seconds),
            "code": self.code,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "Correction":
        seconds = raw.get("seconds")
        if seconds is None and raw.get("time"):
            seconds = parse_clock(str(raw["time"]), "time")
        return cls(
            entry=str(raw.get("entry", "")),
            decision=str(raw.get("decision", "")),
            reason=str(raw.get("reason", "")),
            by=str(raw.get("by") or ""),
            seconds=optional(seconds, lambda v: require_int(v, "seconds")),
            code=optional(raw.get("code"), lambda v: require_str(v, "code", max_len=4)),
        )


@dataclass
class CorrectionLog:
    """Every decision made, in the order they were made."""

    corrections: list[Correction] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.corrections)

    def add(self, correction: Correction) -> Correction:
        for held in self.corrections:
            if held.entry == correction.entry and held.decision == correction.decision:
                raise ConflictError("that decision has already been made",
                                    entry=correction.entry, decision=correction.decision)
        self.corrections.append(correction)
        return correction

    def about(self, entry: str) -> list[Correction]:
        return [row for row in self.corrections if row.entry == str(entry)]

    def voided(self) -> list[str]:
        """Controls voided for everybody, which is the usual case."""
        return sorted({row.code for row in self.corrections
                       if row.decision == "void-control" and row.code})

    def to_list(self) -> list[dict[str, object]]:
        return [row.to_dict() for row in sorted_by(self.corrections, "entry", "decision")]

    @classmethod
    def from_list(cls, rows: list[dict[str, object]]) -> "CorrectionLog":
        return cls([Correction.from_dict(row) for row in rows])


def apply_corrections(results: list[Result], log: CorrectionLog) -> list[Result]:
    """Rewrite a results list according to the decisions taken.

    The decisions are applied in a fixed order -- disqualify last -- so that a
    run which was reinstated and then disqualified ends up disqualified
    whichever order the two were typed in.
    """
    order = {"void-control": 0, "reinstate": 1, "set-time": 2, "retire": 3, "disqualify": 4}
    by_entry: dict[str, Result] = {row.entry: row for row in results}

    for correction in sorted(log.corrections, key=lambda row: order.get(row.decision, 9)):
        held = by_entry.get(correction.entry)
        if held is None:
            continue
        if correction.decision == "reinstate":
            by_entry[correction.entry] = _with(held, outcome="ok",
                                               seconds=correction.seconds or held.seconds)
        elif correction.decision == "set-time":
            by_entry[correction.entry] = _with(held, outcome="ok", seconds=correction.seconds)
        elif correction.decision == "retire":
            by_entry[correction.entry] = _with(held, outcome="dnf", seconds=None)
        elif correction.decision == "disqualify":
            by_entry[correction.entry] = _with(held, outcome="disqualified", seconds=None)

    return [by_entry[row.entry] for row in results]


def _with(row: Result, *, outcome: str, seconds: int | None) -> Result:
    return Result(entry=row.entry, name=row.name, club=row.club, class_code=row.class_code,
                  course=row.course, seconds=seconds, outcome=outcome)


def voided_course_codes(codes: list[str], log: CorrectionLog) -> list[str]:
    """A course's controls with the voided ones taken out.

    When a control is found knocked over, the fair thing is to void it for
    everybody and score the course without it. That is a change to the course,
    not to anybody's punches, which is why it happens here and not in the
    validator.
    """
    voided = set(log.voided())
    return [code for code in codes if code not in voided]
