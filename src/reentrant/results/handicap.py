"""Age handicaps.

Some leagues score veterans and juniors against the open classes by dividing
their time by a factor. The factors here are the ones a club league actually
uses: one hundred per cent at the open ages, rising with age and falling for
the youngest, applied to the raw time to give a handicapped one.

Two decisions worth stating, because both are arbitrary and both matter:

* **The factor is interpolated between the class ages**, not stepped. A runner
  is not suddenly six per cent faster on the first of January they turn fifty.
* **It divides, it does not multiply.** A factor of 1.20 for an M60 means their
  time is divided by 1.20, so a sixty year old running thirty minutes scores
  the same as an open runner doing twenty-five. Multiplying is the other
  convention and gives the opposite ordering, which is why it is spelled out.
"""

from __future__ import annotations

from ..errors import ValidationError
from ..util.order import sorted_by
from ..util.validate import require_int, require_number

#: Age to factor, for each sex. Between the listed ages the factor is
#: interpolated; outside them it is held flat.
FACTORS: dict[str, dict[int, float]] = {
    "M": {10: 0.72, 12: 0.78, 14: 0.86, 16: 0.94, 18: 0.99, 21: 1.00,
          35: 1.02, 40: 1.05, 45: 1.09, 50: 1.14, 55: 1.20, 60: 1.27,
          65: 1.35, 70: 1.44, 75: 1.55, 80: 1.68, 85: 1.83},
    "W": {10: 0.70, 12: 0.76, 14: 0.84, 16: 0.92, 18: 0.97, 21: 1.00,
          35: 1.03, 40: 1.06, 45: 1.10, 50: 1.16, 55: 1.23, 60: 1.31,
          65: 1.40, 70: 1.50, 75: 1.62, 80: 1.76, 85: 1.92},
}


def factor_for(age: int, sex: str) -> float:
    """The handicap factor for an age, interpolated between the listed ones."""
    letter = str(sex).upper()
    if letter not in FACTORS:
        raise ValidationError("no handicap table for that", sex=sex)
    require_int(age, "age", minimum=0, maximum=120)

    table = FACTORS[letter]
    ages = sorted(table)
    if age <= ages[0]:
        return table[ages[0]]
    if age >= ages[-1]:
        return table[ages[-1]]
    for lower, upper in zip(ages, ages[1:]):
        if lower <= age <= upper:
            if upper == lower:
                return table[lower]
            share = (age - lower) / (upper - lower)
            return round(table[lower] + share * (table[upper] - table[lower]), 4)
    raise ValidationError("that age fell through the table", age=age)  # pragma: no cover


def handicapped_seconds(seconds: int, age: int, sex: str) -> int:
    """The time a run is worth once the handicap is applied."""
    require_int(seconds, "seconds", minimum=0)
    factor = factor_for(age, sex)
    return int(round(seconds / factor))


def handicap_table(runs: list[dict[str, object]]) -> list[dict[str, object]]:
    """Handicap a list of runs and order them by the result.

    Each run needs ``seconds``, ``age`` and ``sex``; everything else is carried
    through untouched. Runs with no time are carried through unplaced.
    """
    rows = []
    for run in runs:
        seconds = run.get("seconds")
        if seconds is None:
            rows.append({**run, "factor": None, "handicapped": None})
            continue
        factor = factor_for(int(run["age"]), str(run["sex"]))  # type: ignore[arg-type]
        rows.append({
            **run,
            "factor": factor,
            "handicapped": handicapped_seconds(int(seconds), int(run["age"]), str(run["sex"])),  # type: ignore[arg-type]
        })
    placed = [row for row in rows if row["handicapped"] is not None]
    unplaced = [row for row in rows if row["handicapped"] is None]
    return sorted_by(placed, "handicapped") + sorted_by(unplaced, "name")


def points_for(place: int, *, top: int = 100, step: int = 2, floor: int = 20) -> int:
    """League points for a place: ``top`` for a win, falling by ``step``."""
    require_int(place, "place", minimum=1)
    require_number(top, "top", minimum=1)
    return max(floor, top - (place - 1) * step)
