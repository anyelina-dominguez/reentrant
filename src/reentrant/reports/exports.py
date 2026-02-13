"""CSV out.

Three shapes, because three different people ask for the results and none of
them want the same file:

* **results** -- what goes to the club website and the league secretary;
* **splits** -- one row per leg, which is what the analysis sites eat;
* **entries** -- the entry list back out again, so that a corrected file can go
  round the loop without being retyped.
"""

from __future__ import annotations

from ..entries.competitor import Entry
from ..results.classify import Result
from ..util.csv_io import write_rows
from ..util.times import format_clock

RESULT_COLUMNS = [
    {"key": "place", "title": "place"},
    {"key": "name", "title": "name"},
    {"key": "club", "title": "club"},
    {"key": "class", "title": "class"},
    {"key": "course", "title": "course"},
    {"key": "time", "title": "time"},
    {"key": "seconds", "title": "seconds"},
    {"key": "outcome", "title": "outcome"},
]


def results_csv(results: list[Result]) -> str:
    return write_rows(RESULT_COLUMNS, [{
        "place": row.place,
        "name": row.name,
        "club": row.club,
        "class": row.class_code,
        "course": row.course,
        "time": row.time_text if row.placed else "",
        "seconds": row.seconds,
        "outcome": row.outcome,
    } for row in results])


def splits_csv(splits_by_entry: dict[str, list[dict[str, object]]],
               names: dict[str, str]) -> str:
    """One row per leg, per runner."""
    rows = []
    for reference, legs in splits_by_entry.items():
        for leg in legs:
            rows.append({
                "entry": reference,
                "name": names.get(reference, ""),
                "number": leg["number"],
                "code": leg["code"],
                "leg": format_clock(int(leg["leg_seconds"])),
                "leg_seconds": leg["leg_seconds"],
                "elapsed": format_clock(int(leg["elapsed_seconds"])),
                "elapsed_seconds": leg["elapsed_seconds"],
            })
    return write_rows([
        {"key": "entry", "title": "entry"},
        {"key": "name", "title": "name"},
        {"key": "number", "title": "number"},
        {"key": "code", "title": "code"},
        {"key": "leg", "title": "leg"},
        {"key": "leg_seconds", "title": "leg_seconds"},
        {"key": "elapsed", "title": "elapsed"},
        {"key": "elapsed_seconds", "title": "elapsed_seconds"},
    ], rows)


def entries_csv(entries: list[Entry]) -> str:
    return write_rows([
        {"key": "reference", "title": "reference"},
        {"key": "surname", "title": "surname"},
        {"key": "forename", "title": "forename"},
        {"key": "club", "title": "club"},
        {"key": "birth_year", "title": "birth_year"},
        {"key": "sex", "title": "sex"},
        {"key": "class", "title": "class"},
        {"key": "course", "title": "course"},
        {"key": "card", "title": "card"},
        {"key": "hired", "title": "hired"},
    ], [{
        "reference": entry.reference,
        "surname": entry.competitor.surname,
        "forename": entry.competitor.forename,
        "club": entry.competitor.club,
        "birth_year": entry.competitor.birth_year,
        "sex": entry.competitor.sex,
        "class": entry.class_code,
        "course": entry.course,
        "card": entry.card,
        "hired": "y" if entry.hired else "",
    } for entry in entries])
