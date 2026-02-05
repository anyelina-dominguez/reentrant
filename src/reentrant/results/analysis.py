"""Split analysis: where the time actually went.

Two questions get asked of a set of splits, and the second is the interesting
one.

**Who was fastest on each leg.** Straightforward, and the sum of those fastest
legs is the *superman time* -- what a runner who won every leg would have done.
It is always faster than the winner, usually by several minutes, and it is the
number people quote in the pub.

**Where did I lose time.** Harder, because a runner who is simply slower than
the winner has not "lost" time anywhere in particular. The method here is the
standard one: work out each runner's ratio to the leg winner on every leg, take
the **median** of those ratios as their form for the day, and then call a leg a
loss where they were slower than their own form by more than a margin.

The median matters. A mean is dragged upwards by the one leg where somebody
spent four minutes in a thicket, which is precisely the leg being looked for,
and using it would hide the thing the analysis exists to find.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from ..util.order import sorted_by
from ..util.times import format_clock
from ..util.validate import require_number

#: A leg slower than the runner's own form by more than this is a loss.
LOSS_MARGIN = 1.25

#: Legs shorter than this are too noisy to analyse: a mistake and a good route
#: choice differ by seconds, and everybody's ratio is meaningless.
MINIMUM_LEG_SECONDS = 30


@dataclass(frozen=True)
class LegTime:
    """One runner's time on one leg."""

    entry: str
    number: int
    code: str
    seconds: int


@dataclass
class LegAnalysis:
    """What happened on one leg, across the field."""

    number: int
    code: str
    fastest: int | None
    fastest_entry: str | None
    times: dict[str, int]

    def place_of(self, entry: str) -> int | None:
        """Where a runner came on this leg, ties sharing a place."""
        if entry not in self.times:
            return None
        wanted = self.times[entry]
        return 1 + sum(1 for seconds in self.times.values() if seconds < wanted)


def leg_times(splits_by_entry: dict[str, list[dict[str, object]]]) -> list[LegTime]:
    """Flatten the splits of a whole class into one list."""
    out: list[LegTime] = []
    for entry, rows in splits_by_entry.items():
        for row in rows:
            out.append(LegTime(entry=entry, number=int(row["number"]),
                               code=str(row["code"]), seconds=int(row["leg_seconds"])))
    return sorted_by(out, "number", "seconds", "entry")


def analyse_legs(splits_by_entry: dict[str, list[dict[str, object]]]) -> list[LegAnalysis]:
    """One :class:`LegAnalysis` per leg, in course order."""
    grouped: dict[int, LegAnalysis] = {}
    for leg in leg_times(splits_by_entry):
        found = grouped.get(leg.number)
        if found is None:
            found = LegAnalysis(number=leg.number, code=leg.code,
                                fastest=None, fastest_entry=None, times={})
            grouped[leg.number] = found
        found.times[leg.entry] = leg.seconds
        if found.fastest is None or leg.seconds < found.fastest:
            found.fastest = leg.seconds
            found.fastest_entry = leg.entry
    return [grouped[number] for number in sorted(grouped)]


def superman_seconds(legs: list[LegAnalysis]) -> int | None:
    """The sum of the fastest split on every leg."""
    if not legs or any(leg.fastest is None for leg in legs):
        return None
    return sum(int(leg.fastest) for leg in legs)  # type: ignore[arg-type]


def form_of(entry: str, legs: list[LegAnalysis]) -> float | None:
    """A runner's median ratio to the leg winner, over the legs worth counting."""
    ratios = []
    for leg in legs:
        seconds = leg.times.get(entry)
        if seconds is None or not leg.fastest or leg.fastest < MINIMUM_LEG_SECONDS:
            continue
        ratios.append(seconds / leg.fastest)
    return median(ratios) if ratios else None


def losses_for(entry: str, legs: list[LegAnalysis], *,
               margin: float = LOSS_MARGIN) -> list[dict[str, object]]:
    """The legs where a runner was slower than their own form.

    Each row carries the leg, what they did, what their form says they should
    have done, and the difference -- which is the number people mean by "I lost
    two minutes at 4".
    """
    require_number(margin, "margin", minimum=1.0, maximum=10.0)
    form = form_of(entry, legs)
    if form is None:
        return []

    rows = []
    for leg in legs:
        seconds = leg.times.get(entry)
        if seconds is None or not leg.fastest or leg.fastest < MINIMUM_LEG_SECONDS:
            continue
        expected = leg.fastest * form
        if seconds > expected * margin:
            rows.append({
                "number": leg.number,
                "code": leg.code,
                "seconds": seconds,
                "expected_seconds": int(round(expected)),
                "lost_seconds": int(round(seconds - expected)),
                "ratio": round(seconds / leg.fastest, 3),
            })
    return sorted_by(rows, lambda row: (-int(row["lost_seconds"]), int(row["number"])))


def total_lost(entry: str, legs: list[LegAnalysis], *, margin: float = LOSS_MARGIN) -> int:
    return sum(int(row["lost_seconds"]) for row in losses_for(entry, legs, margin=margin))


def leg_table(legs: list[LegAnalysis], entry: str) -> list[dict[str, object]]:
    """One runner's splits with their place on each leg, for the printout."""
    rows = []
    for leg in legs:
        seconds = leg.times.get(entry)
        rows.append({
            "number": leg.number,
            "code": leg.code,
            "time": format_clock(seconds),
            "place": leg.place_of(entry),
            "fastest": format_clock(leg.fastest),
            "behind": format_clock(None if seconds is None or leg.fastest is None
                                   else seconds - leg.fastest),
        })
    return rows
