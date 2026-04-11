"""The season's fixture list.

A club publishes its fixtures in August for the winter, and each one has dates
that matter separately:

* when **entries open**, which for a popular event is when they all arrive;
* when they **close**, after which it is late entry on the day at a higher
  price, if there is room;
* the **event** itself.

The list is what the club website shows and what an entry system checks against
before it takes anybody's money. Two rules are enforced here and nowhere else:

**A fixture cannot close before it opens**, and cannot run before it closes.
Obvious, and typed wrongly at least once a season.

**Capacity is per fixture, not per course.** A forest with parking for eighty
cars takes a certain number of people whatever courses they enter, and the
number that matters is the total. Where a fixture is full, entries are refused
with the count rather than silently queued.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date

from ..errors import ConflictError, RuleError, ValidationError
from ..util.order import sorted_by
from ..util.validate import optional, require_int, require_str

#: What a fixture is doing at a given date.
STATES = ["announced", "open", "closed", "run", "cancelled"]


def _as_date(text: str, field_name: str) -> _date:
    value = require_str(text, field_name, max_len=10, pattern=r"\d{4}-\d{2}-\d{2}")
    try:
        return _date.fromisoformat(value)
    except ValueError:
        raise ValidationError(f"{field_name} is not a real date", field=field_name,
                              value=text) from None


@dataclass
class Fixture:
    """One event in the season."""

    name: str
    date: str
    venue: str = ""
    opens: str | None = None
    closes: str | None = None
    capacity: int | None = None
    entered: int = 0
    cancelled: bool = False
    note: str = ""

    def __post_init__(self) -> None:
        self.name = require_str(self.name, "name", max_len=80)
        self.date = _as_date(self.date, "date").isoformat()
        self.venue = require_str(self.venue, "venue", min_len=0, max_len=80)
        self.opens = optional(self.opens, lambda v: _as_date(v, "opens").isoformat())
        self.closes = optional(self.closes, lambda v: _as_date(v, "closes").isoformat())
        self.capacity = optional(self.capacity,
                                 lambda v: require_int(v, "capacity", minimum=1, maximum=100_000))
        self.entered = require_int(self.entered, "entered", minimum=0, maximum=100_000)
        self.note = require_str(self.note, "note", min_len=0, max_len=200)

        if self.opens and self.closes and self.closes < self.opens:
            raise ValidationError("entries cannot close before they open", fixture=self.name)
        if self.closes and self.closes > self.date:
            raise ValidationError("entries cannot close after the event", fixture=self.name)

    @property
    def full(self) -> bool:
        return self.capacity is not None and self.entered >= self.capacity

    @property
    def room(self) -> int | None:
        return None if self.capacity is None else max(0, self.capacity - self.entered)

    def state_on(self, today: str) -> str:
        """What the fixture is doing on a given day."""
        when = _as_date(today, "today").isoformat()
        if self.cancelled:
            return "cancelled"
        if when > self.date:
            return "run"
        if self.closes and when > self.closes:
            return "closed"
        if self.opens and when >= self.opens:
            return "open"
        return "announced"

    def accepts(self, today: str) -> bool:
        """Whether an entry can be taken today."""
        return self.state_on(today) == "open" and not self.full

    def take_entry(self, today: str, *, count: int = 1) -> int:
        """Take entries, refusing when shut or full."""
        require_int(count, "count", minimum=1, maximum=1000)
        state = self.state_on(today)
        if state != "open":
            raise RuleError("entries are not open", fixture=self.name, state=state)
        if self.capacity is not None and self.entered + count > self.capacity:
            raise ConflictError("that fixture is full", fixture=self.name,
                                capacity=self.capacity, entered=self.entered)
        self.entered += count
        return self.entered

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "date": self.date,
            "venue": self.venue,
            "opens": self.opens,
            "closes": self.closes,
            "capacity": self.capacity,
            "entered": self.entered,
            "room": self.room,
            "full": self.full,
            "cancelled": self.cancelled,
            "note": self.note,
        }


@dataclass
class Season:
    """A club's fixtures for a winter."""

    name: str
    fixtures: list[Fixture] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.name = require_str(self.name, "name", max_len=80)

    def __len__(self) -> int:
        return len(self.fixtures)

    def add(self, fixture: Fixture) -> Fixture:
        if any(held.name == fixture.name for held in self.fixtures):
            raise ConflictError("there is already a fixture of that name", fixture=fixture.name)
        self.fixtures.append(fixture)
        return fixture

    def require(self, name: str) -> Fixture:
        for fixture in self.fixtures:
            if fixture.name == str(name):
                return fixture
        from ..errors import NotFoundError
        raise NotFoundError("no such fixture", fixture=name)

    def all(self) -> list[Fixture]:
        return sorted_by(self.fixtures, "date", "name")

    def on(self, state: str, today: str) -> list[Fixture]:
        return [fixture for fixture in self.all() if fixture.state_on(today) == str(state)]

    def next_after(self, today: str) -> Fixture | None:
        """The next fixture that has not run, for the front of the website."""
        when = _as_date(today, "today").isoformat()
        ahead = [fixture for fixture in self.all()
                 if fixture.date >= when and not fixture.cancelled]
        return ahead[0] if ahead else None

    def calendar(self, today: str) -> list[dict[str, object]]:
        """The list as the website shows it, with each fixture's state."""
        return [{**fixture.to_dict(), "state": fixture.state_on(today)}
                for fixture in self.all()]

    def to_list(self) -> list[dict[str, object]]:
        return [fixture.to_dict() for fixture in self.all()]
