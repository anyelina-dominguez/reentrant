"""Punches and card reads.

A card comes back from the forest with a list of punches on it: a control code
and the time it was punched, in the order the card recorded them. Plus, usually,
a start punch and a finish punch.

Two things about the list that the rest of the system has to live with:

**It is in card order, not course order.** The runner visited them in whatever
order they managed. Putting them in course order is exactly the question
:mod:`reentrant.timing.validate` answers.

**It may hold punches from another course.** A runner who wanders into somebody
else's control and punches it out of habit has an extra punch on the card, and
that is not an error. Extra punches are ignored, never penalised.

A card may also hold punches from *last week*, if the memory was not cleared.
Those are filtered by time: anything before the start punch is not part of this
run.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import ValidationError
from ..util.ids import FINISH_CODE, START_CODE, require_control_code

#: The two boxes a runner passes before the start. Neither is a control, and
#: neither counts towards anything -- but a card that was never cleared holds
#: last week's punches, and the check box is where that gets caught.
CLEAR_CODE = "C1"
CHECK_CODE = "K1"
from ..util.order import sorted_by
from ..util.times import difference, format_time_of_day
from ..util.validate import optional, require_int, require_list, require_mapping


@dataclass(frozen=True)
class Punch:
    """One control, one moment. The time is seconds since midnight."""

    code: str
    at_seconds: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", require_control_code(self.code))
        object.__setattr__(self, "at_seconds",
                           require_int(self.at_seconds, "at_seconds", minimum=0, maximum=86_399))

    @property
    def is_start(self) -> bool:
        return self.code == START_CODE

    @property
    def is_finish(self) -> bool:
        return self.code == FINISH_CODE

    @property
    def is_admin(self) -> bool:
        """Clear and check: on the card, never on a course."""
        return self.code in (CLEAR_CODE, CHECK_CODE)

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "at": format_time_of_day(self.at_seconds)}

    def __str__(self) -> str:
        return f"{self.code}@{format_time_of_day(self.at_seconds)}"


@dataclass
class CardRead:
    """One card, downloaded.

    ``start_seconds`` and ``finish_seconds`` are what the card itself recorded.
    Where the event uses timed starts rather than a start punch, the card has no
    start and the entry's allotted time is used instead -- which is why
    :meth:`elapsed` takes an override.
    """

    card: int
    punches: list[Punch]
    start_seconds: int | None = None
    finish_seconds: int | None = None
    read_at: str = ""

    def __post_init__(self) -> None:
        self.card = require_int(self.card, "card", minimum=1, maximum=9_999_999)
        self.punches = [punch if isinstance(punch, Punch) else Punch(**punch)
                        for punch in require_list(self.punches, "punches", max_len=1000)]
        self.start_seconds = optional(self.start_seconds,
                                      lambda v: require_int(v, "start_seconds", minimum=0, maximum=86_399))
        self.finish_seconds = optional(self.finish_seconds,
                                       lambda v: require_int(v, "finish_seconds", minimum=0, maximum=86_399))
        self.read_at = (self.read_at or "").strip()

    # -- the punches that belong to this run -------------------------------

    @property
    def control_punches(self) -> list[Punch]:
        """Punches at actual controls, in the order the card recorded them."""
        return [punch for punch in self.punches
                if not (punch.is_start or punch.is_finish or punch.is_admin)]

    @property
    def cleared(self) -> bool:
        """Whether the card was cleared before the run."""
        return any(punch.code == CLEAR_CODE for punch in self.punches)

    @property
    def checked(self) -> bool:
        return any(punch.code == CHECK_CODE for punch in self.punches)

    def since_start(self, start_seconds: int | None = None) -> list[Punch]:
        """Control punches from this run, dropping anything left over from before.

        A card that was not cleared holds last week's punches. They are always
        *earlier* in the day than this run's start, so the start time is enough
        to tell them apart -- except across midnight, which no orienteering
        event has ever needed and which this deliberately does not handle.
        """
        opened = start_seconds if start_seconds is not None else self.start_seconds
        if opened is None:
            return self.control_punches
        return [punch for punch in self.control_punches if punch.at_seconds >= opened]

    def codes(self, start_seconds: int | None = None) -> list[str]:
        return [punch.code for punch in self.since_start(start_seconds)]

    def elapsed(self, start_seconds: int | None = None,
                finish_seconds: int | None = None) -> int | None:
        """The run time in whole seconds, or ``None`` if we cannot say."""
        opened = start_seconds if start_seconds is not None else self.start_seconds
        closed = finish_seconds if finish_seconds is not None else self.finish_seconds
        if opened is None or closed is None:
            return None
        return difference(opened, closed)

    def punch_at(self, code: str) -> Punch | None:
        """The first punch at a code, which is the one that counts."""
        wanted = require_control_code(code)
        for punch in self.punches:
            if punch.code == wanted:
                return punch
        return None

    def ordered(self) -> list[Punch]:
        """Every punch sorted by time, for a download listing."""
        return sorted_by(self.punches, "at_seconds", "code")

    def to_dict(self) -> dict[str, object]:
        return {
            "card": self.card,
            "punches": [punch.to_dict() for punch in self.punches],
            "start": None if self.start_seconds is None else format_time_of_day(self.start_seconds),
            "finish": None if self.finish_seconds is None else format_time_of_day(self.finish_seconds),
            "read_at": self.read_at,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "CardRead":
        from ..util.times import parse_time_of_day

        data = require_mapping(raw, "card read")
        punches = []
        for row in require_list(data.get("punches", []), "punches"):
            entry = require_mapping(row, "punch")
            punches.append(Punch(str(entry.get("code", "")),
                                 parse_time_of_day(str(entry.get("at", "")), "punch time")))
        return cls(
            card=int(data.get("card", 0)),
            punches=punches,
            start_seconds=optional(data.get("start"), lambda v: parse_time_of_day(str(v), "start")),
            finish_seconds=optional(data.get("finish"), lambda v: parse_time_of_day(str(v), "finish")),
            read_at=str(data.get("read_at") or ""),
        )


def read_from_pairs(card: int, pairs: list[tuple[str, str]], *,
                    start: str | None = None, finish: str | None = None) -> CardRead:
    """Build a read from ``[(code, "10:04:11"), ...]``, which is how tests and
    the download log both express one."""
    from ..util.times import parse_time_of_day

    punches = [Punch(code, parse_time_of_day(at, "punch time")) for code, at in pairs]
    return CardRead(
        card=card,
        punches=punches,
        start_seconds=None if start is None else parse_time_of_day(start, "start"),
        finish_seconds=None if finish is None else parse_time_of_day(finish, "finish"),
    )


def require_read(value: object) -> CardRead:
    if not isinstance(value, CardRead):
        raise ValidationError("a card read is required", field="read")
    return value
