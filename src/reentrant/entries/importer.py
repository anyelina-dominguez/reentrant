"""Reading an entry list.

Entry lists arrive from the club's system, from the national entry site, and
from a spreadsheet somebody made, and no two agree on what the columns are
called. The aliases here are the spellings actually seen.

The rule, as everywhere else in this codebase: **one bad row does not lose the
file**. Four hundred entries with three broken dates of birth import three
hundred and ninety-seven and tell you which three to fix.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..errors import ValidationError
from ..util.csv_io import map_columns, read_rows
from ..util.validate import require_str
from .classes import parse_class
from .competitor import Competitor, Entry, EntryList

ALIASES = {
    "surname": ["surname", "last name", "family name", "lastname"],
    "forename": ["forename", "first name", "given name", "firstname"],
    "club": ["club", "team", "organisation"],
    "class": ["class", "age class", "category", "short class"],
    "course": ["course"],
    "card": ["card", "si", "si card", "sicard", "chip", "e card"],
    "birth_year": ["birth year", "yob", "year of birth", "birthyear"],
    "sex": ["sex", "gender", "s"],
    "membership": ["membership", "member", "bof number", "membership number"],
    "hired": ["hired", "hire", "rented"],
}

REQUIRED = ["surname", "forename", "class"]

TRUE_WORDS = {"y", "yes", "true", "1", "hired"}


@dataclass
class ImportReport:
    """What came of reading a file."""

    added: list[Entry] = field(default_factory=list)
    rejected: list[dict[str, object]] = field(default_factory=list)
    read: int = 0

    @property
    def ok(self) -> bool:
        return not self.rejected

    def to_dict(self) -> dict[str, object]:
        return {
            "read": self.read,
            "added": [entry.reference for entry in self.added],
            "rejected": list(self.rejected),
        }


def _year(text: str) -> int | None:
    cleaned = text.strip()
    if not cleaned:
        return None
    if len(cleaned) == 2 and cleaned.isdigit():
        # Two-digit years still turn up. Anything over the current decade is
        # last century, which is the convention every entry system uses.
        number = int(cleaned)
        return 1900 + number if number > 30 else 2000 + number
    if not cleaned.isdigit():
        raise ValidationError("that is not a year", value=text)
    return int(cleaned)


def parse_entries(text: str, *, entries: EntryList | None = None) -> ImportReport:
    """Read a CSV entry list into an :class:`EntryList`."""
    rows = read_rows(require_str(text, "text", min_len=0, max_len=20_000_000))
    report = ImportReport(read=len(rows))
    if not rows:
        return report

    listed = entries if entries is not None else EntryList()
    mapping = map_columns(rows[0].keys(), ALIASES, required=REQUIRED)

    def field_of(row: dict[str, str], name: str) -> str:
        column = mapping.get(name)
        return row.get(column, "").strip() if column else ""

    for number, row in enumerate(rows, start=2):
        try:
            entry = Entry(
                reference=listed.next_reference(),
                competitor=Competitor(
                    surname=field_of(row, "surname"),
                    forename=field_of(row, "forename"),
                    club=field_of(row, "club"),
                    birth_year=_year(field_of(row, "birth_year")),
                    sex=field_of(row, "sex").upper() or None,
                    membership=field_of(row, "membership"),
                ),
                course=field_of(row, "course"),
                class_code=parse_class(field_of(row, "class"), "class").code,
                card=int(field_of(row, "card")) if field_of(row, "card").isdigit() else None,
                hired=field_of(row, "hired").lower() in TRUE_WORDS,
            )
            listed.add(entry)
            report.added.append(entry)
        except Exception as error:  # noqa: BLE001 - one bad row must not lose the file
            report.rejected.append({
                "line": number,
                "name": f"{field_of(row, 'forename')} {field_of(row, 'surname')}".strip(),
                "reason": getattr(error, "message", str(error)),
            })
    return report


def import_into(entries: EntryList, text: str) -> ImportReport:
    """Read a file straight into an existing list."""
    return parse_entries(text, entries=entries)
