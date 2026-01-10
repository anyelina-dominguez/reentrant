"""Fixed-width text.

Results go on a board in a field, in a font nobody chose, printed by whatever
was in the van. Seventy-two columns, no colour, no box-drawing characters.
"""

from __future__ import annotations

from typing import Any, Iterable, Sequence


def pad_right(value: Any, width: int) -> str:
    text = "" if value is None else str(value)
    return text if len(text) >= width else text + " " * (width - len(text))


def pad_left(value: Any, width: int) -> str:
    text = "" if value is None else str(value)
    return text if len(text) >= width else " " * (width - len(text)) + text


def truncate(value: Any, width: int) -> str:
    text = "" if value is None else str(value)
    if len(text) <= width:
        return text
    if width <= 1:
        return text[:width]
    return text[: width - 1] + "."


def table(columns: Sequence[dict[str, Any]], rows: Sequence[dict[str, Any]]) -> str:
    """Render rows as a table.

    A column is ``{"key", "title", "width"?, "align"?}``. A column with no
    width takes the width of its widest cell, which is what makes a results
    list line up whether the club codes are three letters or five.
    """
    specs = []
    for column in columns:
        cells = [str(row.get(column["key"], "") or "") for row in rows]
        natural = max([len(column["title"])] + [len(cell) for cell in cells] + [1])
        specs.append({**column, "width": column.get("width") or natural})

    def line(cells: Sequence[Any]) -> str:
        parts = []
        for spec, cell in zip(specs, cells):
            text = truncate(cell, spec["width"])
            parts.append(pad_left(text, spec["width"]) if spec.get("align") == "right"
                         else pad_right(text, spec["width"]))
        return "  ".join(parts).rstrip()

    out = [line([spec["title"] for spec in specs]),
           line(["-" * spec["width"] for spec in specs])]
    out.extend(line([row.get(spec["key"], "") for spec in specs]) for row in rows)
    return "\n".join(out)


def heading(text: str, width: int = 66) -> str:
    return f"{text} " + "=" * max(0, width - len(text) - 1)


def wrap(text: str, width: int = 72) -> list[str]:
    words = str(text).split()
    lines: list[str] = []
    current = ""
    for word in words:
        if not current:
            current = word
        elif len(current) + 1 + len(word) <= width:
            current += " " + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def plural(count: int, singular: str, plural_form: str | None = None) -> str:
    word = singular if count == 1 else (plural_form or singular + "s")
    return f"{count} {word}"


def columns(items: Iterable[str], per_row: int = 4, width: int = 18) -> list[str]:
    """Lay a list out in columns, for a start list pinned to a tree."""
    entries = list(items)
    lines = []
    for start in range(0, len(entries), per_row):
        lines.append("".join(pad_right(truncate(entry, width - 1), width)
                             for entry in entries[start:start + per_row]).rstrip())
    return lines
