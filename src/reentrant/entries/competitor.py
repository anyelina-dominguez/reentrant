"""Competitors and their entries.

An **entry** is one person, on one course, in one class, on one card, at one
event. The rule that the whole download depends on:

    one card, one run.

If two people enter on the same card the download cannot tell their runs apart,
because the card is the only thing the timing kit knows about. Clubs hire cards
out and people forget to say, so this is checked at entry time and again when
the card is read, and it is a conflict rather than a warning.

Names are held as surname and forename separately, because a results list sorts
by surname and no amount of splitting on a space gets "van der Berg" right.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import ConflictError, NotFoundError, ValidationError
from ..util.ids import Sequence, reference
from ..util.order import group_by, sorted_by
from ..util.validate import (
    optional, require_bool, require_int, require_mapping, require_one_of, require_str,
)
from .classes import AgeClass, class_for, may_enter, parse_class

#: What has happened to an entry. ``entered`` until the card is read.
ENTRY_STATES = ["entered", "started", "finished", "dns", "dnf", "disqualified"]

#: Card numbers in use by the SI system. Anything outside is a typo.
LOWEST_CARD = 1
HIGHEST_CARD = 9_999_999


@dataclass(frozen=True)
class Competitor:
    """A person. The same person at two events is two entries, one competitor."""

    surname: str
    forename: str
    club: str = ""
    birth_year: int | None = None
    sex: str | None = None
    membership: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "surname", require_str(self.surname, "surname", max_len=60))
        object.__setattr__(self, "forename", require_str(self.forename, "forename", max_len=60))
        object.__setattr__(self, "club", require_str(self.club, "club", min_len=0, max_len=40))
        if self.birth_year is not None:
            object.__setattr__(self, "birth_year",
                               require_int(self.birth_year, "birth_year", minimum=1900, maximum=2200))
        if self.sex is not None:
            object.__setattr__(self, "sex", require_one_of(str(self.sex).upper(), "sex", ["M", "W"]))
        object.__setattr__(self, "membership", require_str(self.membership, "membership",
                                                          min_len=0, max_len=20))

    @property
    def name(self) -> str:
        """``Forename Surname``, for a start list."""
        return f"{self.forename} {self.surname}".strip()

    @property
    def listed_name(self) -> str:
        """``Surname, Forename``, for a results list that sorts by surname."""
        return f"{self.surname}, {self.forename}".strip(", ")

    def natural_class(self, event_year: int) -> AgeClass | None:
        """The class they belong in, if we know enough to say."""
        if self.birth_year is None or self.sex is None:
            return None
        return class_for(self.birth_year, event_year, self.sex)

    def to_dict(self) -> dict[str, object]:
        return {
            "surname": self.surname,
            "forename": self.forename,
            "club": self.club,
            "birth_year": self.birth_year,
            "sex": self.sex,
            "membership": self.membership,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "Competitor":
        data = require_mapping(raw, "competitor")
        return cls(
            surname=str(data.get("surname", "")),
            forename=str(data.get("forename", "")),
            club=str(data.get("club") or ""),
            birth_year=optional(data.get("birth_year"), lambda v: require_int(v, "birth_year")),
            sex=optional(data.get("sex"), lambda v: require_str(v, "sex")),
            membership=str(data.get("membership") or ""),
        )


def require_card(value: object, field: str = "card") -> int:
    return require_int(value, field, minimum=LOWEST_CARD, maximum=HIGHEST_CARD)


@dataclass
class Entry:
    """One person's entry to one event.

    ``course`` may be blank, in which case the course comes from the class.
    """

    reference: str
    competitor: Competitor
    course: str
    class_code: str
    card: int | None = None
    hired: bool = False
    start_seconds: int | None = None
    state: str = "entered"
    note: str = ""

    def __post_init__(self) -> None:
        self.reference = require_str(self.reference, "reference", max_len=16)
        if not isinstance(self.competitor, Competitor):
            raise ValidationError("an entry needs a competitor", field="competitor")
        # An entry may name no course at all: a competitor enters a *class*,
        # and which course that class runs is the organiser's to change on the
        # morning. Event.entry_course resolves it.
        self.course = require_str(self.course, "course", min_len=0, max_len=40)
        self.class_code = parse_class(self.class_code, "class_code").code
        self.card = optional(self.card, lambda v: require_card(v))
        self.hired = require_bool(self.hired, "hired")
        self.start_seconds = optional(self.start_seconds,
                                      lambda v: require_int(v, "start_seconds", minimum=0, maximum=86_399))
        self.state = require_one_of(self.state, "state", ENTRY_STATES)
        self.note = (self.note or "").strip()
        if self.hired and self.card is None:
            raise ValidationError("a hired card still has a number", field="card")

    @property
    def age_class(self) -> AgeClass:
        return parse_class(self.class_code)

    @property
    def has_run(self) -> bool:
        return self.state in ("finished", "dnf", "disqualified")

    def eligible(self, event_year: int) -> bool:
        """Whether the class they entered is one they may run."""
        if self.competitor.birth_year is None or self.competitor.sex is None:
            return True  # nothing to check against; the entry desk decides
        return may_enter(self.competitor.birth_year, event_year, self.competitor.sex, self.class_code)

    def with_state(self, state: str, *, note: str = "") -> "Entry":
        require_one_of(state, "state", ENTRY_STATES)
        return Entry(**{**self.to_dict_shallow(), "state": state, "note": note or self.note})

    def to_dict_shallow(self) -> dict[str, object]:
        return {
            "reference": self.reference,
            "competitor": self.competitor,
            "course": self.course,
            "class_code": self.class_code,
            "card": self.card,
            "hired": self.hired,
            "start_seconds": self.start_seconds,
            "state": self.state,
            "note": self.note,
        }

    def to_dict(self) -> dict[str, object]:
        return {**self.to_dict_shallow(), "competitor": self.competitor.to_dict()}

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "Entry":
        data = require_mapping(raw, "entry")
        return cls(
            reference=str(data.get("reference", "")),
            competitor=Competitor.from_dict(data.get("competitor", {})),  # type: ignore[arg-type]
            course=str(data.get("course", "")),
            class_code=str(data.get("class_code", "")),
            card=optional(data.get("card"), require_card),
            hired=bool(data.get("hired", False)),
            start_seconds=optional(data.get("start_seconds"), lambda v: require_int(v, "start_seconds")),
            state=str(data.get("state", "entered")),
            note=str(data.get("note") or ""),
        )


class EntryList:
    """Every entry at an event, indexed by the two things people look up by."""

    def __init__(self) -> None:
        self._entries: dict[str, Entry] = {}
        self._by_card: dict[int, str] = {}
        self._sequence = Sequence(1)

    def __len__(self) -> int:
        return len(self._entries)

    def next_reference(self) -> str:
        candidate = reference("ENT", self._sequence.take())
        while candidate in self._entries:
            candidate = reference("ENT", self._sequence.take())
        return candidate

    def add(self, entry: Entry) -> Entry:
        if entry.reference in self._entries:
            raise ConflictError("that entry reference is taken", reference=entry.reference)
        if entry.card is not None and entry.card in self._by_card:
            raise ConflictError(
                "that card is already entered", card=entry.card,
                held_by=self._by_card[entry.card],
            )
        self._entries[entry.reference] = entry
        if entry.card is not None:
            self._by_card[entry.card] = entry.reference
        self._sequence.observe(_number_of(entry.reference))
        return entry

    def put(self, entry: Entry) -> Entry:
        """Add or replace, for loading a file."""
        held = self._entries.get(entry.reference)
        if held is not None and held.card is not None:
            self._by_card.pop(held.card, None)
        self._entries[entry.reference] = entry
        if entry.card is not None:
            self._by_card[entry.card] = entry.reference
        self._sequence.observe(_number_of(entry.reference))
        return entry

    def update(self, entry: Entry) -> Entry:
        self.require(entry.reference)
        return self.put(entry)

    def require(self, reference_: str) -> Entry:
        entry = self._entries.get(require_str(reference_, "entry"))
        if entry is None:
            raise NotFoundError("no such entry", entry=reference_)
        return entry

    def get(self, reference_: str) -> Entry | None:
        return self._entries.get(str(reference_))

    def by_card(self, card: int) -> Entry | None:
        held = self._by_card.get(require_card(card))
        return None if held is None else self._entries.get(held)

    def require_card(self, card: int) -> Entry:
        entry = self.by_card(card)
        if entry is None:
            raise NotFoundError("no entry on that card", card=card)
        return entry

    def remove(self, reference_: str) -> Entry:
        entry = self.require(reference_)
        del self._entries[entry.reference]
        if entry.card is not None:
            self._by_card.pop(entry.card, None)
        return entry

    def all(self) -> list[Entry]:
        return sorted_by(self._entries.values(), "reference")

    def on_course(self, course: str) -> list[Entry]:
        return [entry for entry in self.all() if entry.course == str(course)]

    def in_class(self, class_code: str) -> list[Entry]:
        return [entry for entry in self.all() if entry.class_code == str(class_code).upper()]

    def by_club(self) -> dict[str, list[Entry]]:
        return group_by(sorted_by(self._entries.values(),
                                  lambda e: (e.competitor.club, e.competitor.listed_name)),
                        lambda entry: entry.competitor.club)

    def hired_cards(self) -> list[Entry]:
        return [entry for entry in self.all() if entry.hired]

    def ineligible(self, event_year: int) -> list[Entry]:
        """Entries in a class the competitor may not run."""
        return [entry for entry in self.all() if not entry.eligible(event_year)]

    def to_list(self) -> list[dict[str, object]]:
        return [entry.to_dict() for entry in self.all()]

    @classmethod
    def from_list(cls, rows: list[dict[str, object]]) -> "EntryList":
        entries = cls()
        for row in rows:
            entries.put(Entry.from_dict(row))
        return entries


def _number_of(text: str) -> int | None:
    tail = text.rsplit("-", 1)[-1]
    return int(tail) if tail.isdigit() else None
