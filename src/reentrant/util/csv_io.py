"""Reading and writing the CSV that an event actually swims in.

Entry lists arrive as CSV from the club's entry system, from a spreadsheet
somebody made, and from the national entry site, and no two of them agree on
what the columns are called. So the reader maps a handful of known aliases onto
canonical names and leaves everything else alone.

The stdlib ``csv`` module does the quoting; this module does the naming, and
the one rule that matters: **a row that cannot be read does not lose the file**.
"""

from __future__ import annotations

import csv
import io
from typing import Any, Iterable, Sequence

from ..errors import ValidationError


def _normalise(name: str) -> str:
    return name.strip().lower().replace(" ", "_").replace("-", "_")


def read_rows(text: str) -> list[dict[str, str]]:
    """Every row as a dict, with the header normalised to lower_snake_case."""
    reader = csv.reader(io.StringIO(text))
    rows = [row for row in reader if any(cell.strip() for cell in row)]
    if not rows:
        return []
    header = [_normalise(cell) for cell in rows[0]]
    out = []
    for cells in rows[1:]:
        record = {name: (cells[index].strip() if index < len(cells) else "")
                  for index, name in enumerate(header)}
        out.append(record)
    return out


def map_columns(header: Iterable[str], aliases: dict[str, Sequence[str]],
                *, required: Sequence[str] = ()) -> dict[str, str]:
    """Work out which column holds each field.

    ``aliases`` maps a canonical field name to the spellings seen in the wild.
    Missing required fields raise, so that a file with no name column fails at
    the top rather than four hundred rows later.
    """
    present = [_normalise(name) for name in header]
    mapping: dict[str, str] = {}
    for field, options in aliases.items():
        for option in options:
            if _normalise(option) in present:
                mapping[field] = _normalise(option)
                break
    missing = [field for field in required if field not in mapping]
    if missing:
        raise ValidationError(
            "the file has no column for " + ", ".join(missing),
            missing=missing, columns=present,
        )
    return mapping


def write_rows(columns: Sequence[dict[str, str]], rows: Sequence[dict[str, Any]]) -> str:
    """Write CSV with a header row, quoting whatever needs it."""
    if not columns:
        raise ValidationError("a csv needs at least one column")
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([column.get("title", column["key"]) for column in columns])
    for row in rows:
        writer.writerow(["" if row.get(column["key"]) is None else row.get(column["key"], "")
                         for column in columns])
    return buffer.getvalue()
