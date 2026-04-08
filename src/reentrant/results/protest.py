"""Complaints, protests and the jury.

The formal route when somebody thinks a result is wrong, and it has three
stages because the sport says so:

1. a **complaint** to the organiser, which most of them end at;
2. if the complainant is not satisfied, a **protest** to the jury;
3. the jury's **decision**, which is final.

Time limits are the point of the whole structure. A complaint has to be in
within ``COMPLAINT_MINUTES`` of the results going up, and a protest within
``PROTEST_MINUTES`` of the organiser's answer. Somebody who reads the results
in the car on Wednesday has no case, however right they are, and recording the
clock times is what lets the organiser say so kindly.

Nothing here changes a result. A jury that upholds a protest produces a
:class:`~reentrant.timing.repair.Correction`, which is a separate, recorded
decision -- so the results can always be rebuilt from the download plus the
decisions, and the reasoning survives.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..errors import ConflictError, RuleError, ValidationError
from ..timing.repair import Correction
from ..util.order import sorted_by
from ..util.times import difference, format_time_of_day
from ..util.validate import optional, require_int, require_one_of, require_str

#: How long after the results go up a complaint may be made.
COMPLAINT_MINUTES = 15

#: And how long after the organiser's answer a protest may be lodged.
PROTEST_MINUTES = 15

STAGES = ["complaint", "protest", "decided"]
OUTCOMES = ["upheld", "rejected", "withdrawn"]


@dataclass
class Complaint:
    """Somebody says a result is wrong."""

    reference: str
    entry: str
    about: str
    made_seconds: int
    results_seconds: int
    stage: str = "complaint"
    answer: str = ""
    answered_seconds: int | None = None
    protest_seconds: int | None = None
    outcome: str | None = None
    reasoning: str = ""
    jury: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.reference = require_str(self.reference, "reference", max_len=16)
        self.entry = require_str(self.entry, "entry", max_len=16)
        self.about = require_str(self.about, "about", max_len=400)
        self.made_seconds = require_int(self.made_seconds, "made_seconds", minimum=0, maximum=86_399)
        self.results_seconds = require_int(self.results_seconds, "results_seconds",
                                           minimum=0, maximum=86_399)
        self.stage = require_one_of(self.stage, "stage", STAGES)
        self.answered_seconds = optional(self.answered_seconds,
                                         lambda v: require_int(v, "answered_seconds", minimum=0, maximum=86_399))
        self.protest_seconds = optional(self.protest_seconds,
                                        lambda v: require_int(v, "protest_seconds", minimum=0, maximum=86_399))
        self.outcome = optional(self.outcome, lambda v: require_one_of(v, "outcome", OUTCOMES))
        self.jury = [require_str(name, "juror", max_len=60) for name in self.jury]

    @property
    def late_by(self) -> int:
        """Seconds past the complaint window, or nought if it was in time."""
        return max(0, difference(self.results_seconds, self.made_seconds) - COMPLAINT_MINUTES * 60)

    @property
    def in_time(self) -> bool:
        return self.late_by == 0

    def answer_it(self, answer: str, at_seconds: int) -> "Complaint":
        """The organiser answers."""
        if self.stage != "complaint":
            raise ConflictError("that complaint has already moved on",
                                reference=self.reference, stage=self.stage)
        self.answer = require_str(answer, "answer", max_len=400)
        self.answered_seconds = require_int(at_seconds, "at_seconds", minimum=0, maximum=86_399)
        return self

    def escalate(self, at_seconds: int) -> "Complaint":
        """The complainant is not satisfied and takes it to the jury."""
        if self.answered_seconds is None:
            raise ConflictError("the organiser has not answered yet", reference=self.reference)
        if self.stage != "complaint":
            raise ConflictError("that is already with the jury", reference=self.reference)
        late = difference(self.answered_seconds, at_seconds) - PROTEST_MINUTES * 60
        if late > 0:
            raise RuleError("that protest is out of time",
                            reference=self.reference, late_by=late)
        self.stage = "protest"
        self.protest_seconds = require_int(at_seconds, "at_seconds", minimum=0, maximum=86_399)
        return self

    def decide(self, outcome: str, reasoning: str, jury: list[str]) -> "Complaint":
        """The jury decides. This is final."""
        if self.stage != "protest":
            raise ConflictError("there is no protest to decide", reference=self.reference)
        if len(jury) < 3:
            raise ValidationError("a jury is three people", reference=self.reference, jury=jury)
        self.outcome = require_one_of(outcome, "outcome", OUTCOMES)
        self.reasoning = require_str(reasoning, "reasoning", max_len=800)
        self.jury = [require_str(name, "juror", max_len=60) for name in jury]
        self.stage = "decided"
        return self

    def correction(self, decision: str, reason: str = "") -> Correction:
        """The correction an upheld protest produces."""
        if self.outcome != "upheld":
            raise ConflictError("only an upheld protest changes a result",
                                reference=self.reference, outcome=self.outcome)
        return Correction(entry=self.entry, decision=decision,
                          reason=reason or self.reasoning or "upheld on protest",
                          by="jury")

    def to_dict(self) -> dict[str, object]:
        return {
            "reference": self.reference,
            "entry": self.entry,
            "about": self.about,
            "made": format_time_of_day(self.made_seconds),
            "in_time": self.in_time,
            "late_by": self.late_by,
            "stage": self.stage,
            "answer": self.answer,
            "answered": None if self.answered_seconds is None else format_time_of_day(self.answered_seconds),
            "outcome": self.outcome,
            "reasoning": self.reasoning,
            "jury": list(self.jury),
        }


@dataclass
class ComplaintBook:
    """Every complaint made at an event."""

    complaints: list[Complaint] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.complaints)

    def add(self, complaint: Complaint) -> Complaint:
        if any(held.reference == complaint.reference for held in self.complaints):
            raise ConflictError("that complaint reference is taken",
                                reference=complaint.reference)
        self.complaints.append(complaint)
        return complaint

    def about(self, entry: str) -> list[Complaint]:
        return [row for row in self.complaints if row.entry == str(entry)]

    def open(self) -> list[Complaint]:
        """Everything not yet finished with."""
        return sorted_by([row for row in self.complaints if row.stage != "decided"],
                         "made_seconds", "reference")

    def corrections(self) -> list[Correction]:
        """The corrections every upheld protest produced, for the results run."""
        out = []
        for complaint in self.complaints:
            if complaint.outcome == "upheld":
                out.append(complaint.correction("reinstate"))
        return out

    def to_list(self) -> list[dict[str, object]]:
        return [row.to_dict() for row in sorted_by(self.complaints, "made_seconds", "reference")]
