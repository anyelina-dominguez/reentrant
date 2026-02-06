"""Drawing a start list.

Every runner on a course gets a start slot, one every ``interval_seconds``.
Given that, the draw has one job: **keep people who might follow each other
apart**.

Two runners from the same club, starting one behind the other on the same
course, will end up running together whether they mean to or not. So will two
people with the same surname, who are usually a parent and a child. The draw
therefore separates:

* the same club, within ``club_gap`` slots;
* the same surname, within ``family_gap`` slots.

The method is a first pass in a fixed pseudo-random order, then a repair pass
that swaps offending runners with the furthest-away slot that fixes it. It is
not optimal and does not pretend to be -- a perfect separation is not always
possible, and where it is not, the draw says which pairs it could not fix
rather than shuffling forever.

The order is seeded from the event and the course name, so the same entries
always draw the same list. An organiser who reruns the draw after a late entry
should get the old list with the newcomer slotted in, not a completely
different one, or every start list already printed is wrong.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from ..entries.competitor import Entry
from ..util.order import sorted_by
from ..util.times import format_time_of_day
from ..util.validate import require_int, require_str

#: How many slots apart two runners of the same club must be.
DEFAULT_CLUB_GAP = 2

#: And two runners sharing a surname.
DEFAULT_FAMILY_GAP = 3


@dataclass(frozen=True)
class Slot:
    """One start time, and who is in it."""

    seconds: int
    entry: str
    name: str
    club: str

    @property
    def time(self) -> str:
        return format_time_of_day(self.seconds)


@dataclass
class Draw:
    """A drawn start list for one course."""

    course: str
    slots: list[Slot]
    unresolved: list[dict[str, object]]

    @property
    def first_seconds(self) -> int | None:
        return self.slots[0].seconds if self.slots else None

    @property
    def last_seconds(self) -> int | None:
        return self.slots[-1].seconds if self.slots else None

    def of(self, entry: str) -> Slot | None:
        return next((slot for slot in self.slots if slot.entry == entry), None)

    def to_list(self) -> list[dict[str, object]]:
        return [{"time": slot.time, "seconds": slot.seconds, "entry": slot.entry,
                 "name": slot.name, "club": slot.club} for slot in self.slots]


def _conflicts(order: list[Entry], club_gap: int, family_gap: int) -> list[dict[str, object]]:
    found = []
    for index, entry in enumerate(order):
        for ahead in range(1, max(club_gap, family_gap) + 1):
            other_index = index + ahead
            if other_index >= len(order):
                break
            other = order[other_index]
            same_club = (entry.competitor.club and entry.competitor.club == other.competitor.club)
            same_name = entry.competitor.surname.lower() == other.competitor.surname.lower()
            if same_club and ahead <= club_gap:
                found.append({"first": entry.reference, "second": other.reference,
                              "gap": ahead, "reason": "same club"})
            elif same_name and ahead <= family_gap:
                found.append({"first": entry.reference, "second": other.reference,
                              "gap": ahead, "reason": "same surname"})
    return found


def _repair(order: list[Entry], club_gap: int, family_gap: int, rounds: int = 40) -> list[Entry]:
    """Swap offenders away from each other, worst first, a bounded number of times.

    Either member of an offending pair may be the one that moves. Trying only
    the second gets stuck: two runners who are both same-club *and* same-family
    with the person on their other side cannot be fixed by moving one of them.
    """
    working = list(order)
    for _ in range(rounds):
        problems = _conflicts(working, club_gap, family_gap)
        if not problems:
            break
        problem = min(problems, key=lambda row: int(row["gap"]))
        best: tuple[int, list[Entry]] | None = None
        for which in ("first", "second"):
            position = next(index for index, entry in enumerate(working)
                            if entry.reference == problem[which])
            for candidate in range(len(working)):
                if candidate == position:
                    continue
                swapped = list(working)
                swapped[position], swapped[candidate] = swapped[candidate], swapped[position]
                remaining = len(_conflicts(swapped, club_gap, family_gap))
                if best is None or remaining < best[0]:
                    best = (remaining, swapped)
        if best is None or best[0] >= len(problems):
            break
        working = best[1]
    return working


def _clashes_with(candidate: Entry, placed: list[Entry], club_gap: int, family_gap: int) -> bool:
    """Whether putting ``candidate`` next would break a separation rule."""
    window = max(club_gap, family_gap)
    for distance, earlier in enumerate(reversed(placed[-window:] if window else []), start=1):
        if (candidate.competitor.club and candidate.competitor.club == earlier.competitor.club
                and distance <= club_gap):
            return True
        if (candidate.competitor.surname.lower() == earlier.competitor.surname.lower()
                and distance <= family_gap):
            return True
    return False


def _build(runners: list[Entry], club_gap: int, family_gap: int, seed: str) -> list[Entry]:
    """Build the order a slot at a time, biggest club first.

    Shuffling and then repairing gets stuck: on a course where one club has
    brought half the field, the arrangement that works needs several runners to
    move at once and no single swap improves anything. Placing the scarcest
    slot first -- which means the biggest club first -- finds those
    arrangements directly.
    """
    remaining = list(runners)
    random.Random(seed).shuffle(remaining)
    # The shuffle is what breaks ties between equally good candidates. Without
    # it the construction is entirely deterministic and the same people start
    # first at every event, which competitors notice within about two fixtures.
    order = {entry.reference: index for index, entry in enumerate(remaining)}

    placed: list[Entry] = []
    while remaining:
        sizes: dict[str, int] = {}
        for entry in remaining:
            sizes[entry.competitor.club] = sizes.get(entry.competitor.club, 0) + 1

        # Prefer somebody who fits; among those, somebody from the club with the
        # most runners still to place, since they are the hardest to fit later.
        allowed = [entry for entry in remaining
                   if not _clashes_with(entry, placed, club_gap, family_gap)]
        pool = allowed or remaining
        chosen = max(pool, key=lambda entry: (sizes[entry.competitor.club], -order[entry.reference]))
        placed.append(chosen)
        remaining.remove(chosen)
    return placed


def _best_order(runners: list[Entry], club_gap: int, family_gap: int, seed: str) -> list[Entry]:
    """Build a draw, then repair whatever the build could not avoid."""
    built = _build(runners, club_gap, family_gap, seed)
    repaired = _repair(built, club_gap, family_gap)
    if len(_conflicts(repaired, club_gap, family_gap)) <= len(_conflicts(built, club_gap, family_gap)):
        return repaired
    return built


def draw_course(course: str, entries: list[Entry], *,
                first_seconds: int,
                interval_seconds: int = 60,
                club_gap: int = DEFAULT_CLUB_GAP,
                family_gap: int = DEFAULT_FAMILY_GAP,
                seed: str = "") -> Draw:
    """Draw the start list for one course."""
    require_str(course, "course", max_len=40)
    require_int(first_seconds, "first_seconds", minimum=0, maximum=86_399)
    require_int(interval_seconds, "interval_seconds", minimum=10, maximum=3600)
    require_int(club_gap, "club_gap", minimum=0, maximum=20)
    require_int(family_gap, "family_gap", minimum=0, maximum=20)

    runners = sorted_by(entries, "reference")
    if not runners:
        return Draw(course=course, slots=[], unresolved=[])

    # A fixed seed so that redrawing gives the same list.
    placed = _best_order(runners, club_gap, family_gap, f"{seed}|{course}")

    slots = [
        Slot(seconds=first_seconds + index * interval_seconds,
             entry=entry.reference,
             name=entry.competitor.listed_name,
             club=entry.competitor.club)
        for index, entry in enumerate(placed)
    ]
    return Draw(course=course, slots=slots,
                unresolved=_conflicts(placed, club_gap, family_gap))


def apply_draw(entries: list[Entry], draw: Draw) -> list[Entry]:
    """Write the drawn times onto the entries."""
    times = {slot.entry: slot.seconds for slot in draw.slots}
    out = []
    for entry in entries:
        if entry.reference in times:
            out.append(Entry.from_dict({**entry.to_dict(), "start_seconds": times[entry.reference]}))
        else:
            out.append(entry)
    return out


def start_list(draws: list[Draw]) -> list[dict[str, object]]:
    """Every course's draw in one list, in time order, for the board."""
    rows = []
    for drawn in draws:
        for slot in drawn.slots:
            rows.append({"time": slot.time, "seconds": slot.seconds, "course": drawn.course,
                         "entry": slot.entry, "name": slot.name, "club": slot.club})
    return sorted_by(rows, lambda row: (row["seconds"], row["course"], row["name"]))
