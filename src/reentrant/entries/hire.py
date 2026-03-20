"""Hired cards.

The club owns a box of cards and lends them to people who have not bought their
own. Two problems follow, and both of them happen at every event.

**Cards go home in pockets.** A hired card that is not returned costs the club
twenty pounds and is missing from the next event. So a hire is a loan with a
name against it, and the end of the day produces a list of who still has one.

**The same card cannot be lent twice.** Obvious, and yet: the desk lends 300111
to somebody at nine, they retire without downloading, and at eleven the desk
lends it again because the box says it is free. The second run overwrites the
first. A card is on loan until it is returned, whether it has been used or not.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..errors import ConflictError, NotFoundError
from ..util.order import sorted_by
from ..util.times import format_time_of_day
from ..util.validate import optional, require_int, require_str


@dataclass
class Hire:
    """One card, out on loan."""

    card: int
    entry: str
    name: str
    out_seconds: int
    back_seconds: int | None = None
    deposit: str = ""

    def __post_init__(self) -> None:
        self.card = require_int(self.card, "card", minimum=1, maximum=9_999_999)
        self.entry = require_str(self.entry, "entry", max_len=16)
        self.name = require_str(self.name, "name", max_len=120)
        self.out_seconds = require_int(self.out_seconds, "out_seconds", minimum=0, maximum=86_399)
        self.back_seconds = optional(self.back_seconds,
                                     lambda v: require_int(v, "back_seconds", minimum=0, maximum=86_399))
        self.deposit = require_str(self.deposit, "deposit", min_len=0, max_len=40)

    @property
    def returned(self) -> bool:
        return self.back_seconds is not None

    def to_dict(self) -> dict[str, object]:
        return {
            "card": self.card,
            "entry": self.entry,
            "name": self.name,
            "out": format_time_of_day(self.out_seconds),
            "back": None if self.back_seconds is None else format_time_of_day(self.back_seconds),
            "returned": self.returned,
            "deposit": self.deposit,
        }


@dataclass
class HireBox:
    """The box of cards, and what is in it."""

    owned: list[int] = field(default_factory=list)
    hires: list[Hire] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.owned = sorted({require_int(card, "card", minimum=1) for card in self.owned})

    def out_on(self, card: int) -> Hire | None:
        """The open loan of a card, if there is one."""
        for hire in self.hires:
            if hire.card == int(card) and not hire.returned:
                return hire
        return None

    def available(self) -> list[int]:
        """Cards in the box: owned, and not currently out."""
        lent = {hire.card for hire in self.hires if not hire.returned}
        return [card for card in self.owned if card not in lent]

    def lend(self, card: int, entry: str, name: str, out_seconds: int,
             *, deposit: str = "") -> Hire:
        number = require_int(card, "card", minimum=1)
        if number not in self.owned:
            raise NotFoundError("that card is not ours to lend", card=number)
        held = self.out_on(number)
        if held is not None:
            raise ConflictError("that card is already out", card=number,
                                held_by=held.entry, name=held.name)
        hire = Hire(card=number, entry=entry, name=name,
                    out_seconds=out_seconds, deposit=deposit)
        self.hires.append(hire)
        return hire

    def take_back(self, card: int, back_seconds: int) -> Hire:
        held = self.out_on(card)
        if held is None:
            raise NotFoundError("that card is not out", card=int(card))
        held.back_seconds = require_int(back_seconds, "back_seconds", minimum=0, maximum=86_399)
        return held

    def still_out(self) -> list[Hire]:
        """The list read out at the end of the day."""
        return sorted_by([hire for hire in self.hires if not hire.returned], "name", "card")

    def summary(self) -> dict[str, int]:
        return {
            "owned": len(self.owned),
            "out": len(self.still_out()),
            "available": len(self.available()),
            "lent_today": len(self.hires),
        }

    def to_dict(self) -> dict[str, object]:
        return {"owned": list(self.owned),
                "hires": [hire.to_dict() for hire in sorted_by(self.hires, "card", "out_seconds")]}
