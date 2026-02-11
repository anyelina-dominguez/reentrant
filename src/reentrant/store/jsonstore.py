"""The event, in one JSON file.

An orienteering event is a few hundred entries and a few thousand punches. That
fits in memory, fits in a text file, and can be copied onto a memory stick by
somebody who has never used a database. It is also readable at four in the
afternoon when the results will not come out and the only person who can help
is on the phone.

The save is atomic: write a temporary file, rename it over the target. A laptop
whose battery goes halfway through leaves the previous file intact, which is
the whole reason to bother.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..errors import SchemaError
from ..event.event import Event
from ..results.classify import Result
from ..timing.punch import CardRead
from ..util.validate import require_str
from .migrations import CURRENT_VERSION, migrate


@dataclass
class EventFile:
    """Everything about one event that is worth keeping."""

    event: Event
    downloads: list[CardRead] = field(default_factory=list)
    results: list[Result] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": CURRENT_VERSION,
            "event": self.event.to_dict(),
            "downloads": [read.to_dict() for read in self.downloads],
            "results": [row.to_dict() for row in self.results],
            "draws": [],
        }

    @classmethod
    def from_dict(cls, raw: Any) -> "EventFile":
        data = migrate(raw)
        return cls(
            event=Event.from_dict(data.get("event") or {}),
            downloads=[CardRead.from_dict(row) for row in data.get("downloads") or []],
            results=[_result_from(row) for row in data.get("results") or []],
        )


def _result_from(raw: dict[str, Any]) -> Result:
    return Result(
        entry=str(raw.get("entry", "")),
        name=str(raw.get("name", "")),
        club=str(raw.get("club") or ""),
        class_code=str(raw.get("class") or raw.get("class_code") or ""),
        course=str(raw.get("course", "")),
        seconds=raw.get("seconds"),
        outcome=str(raw.get("outcome", "ok")),
        place=raw.get("place"),
        behind_seconds=raw.get("behind"),
    )


def load(path: str | Path) -> EventFile | None:
    """Read an event file, or ``None`` when there is not one yet."""
    where = Path(require_str(str(path), "path"))
    if not where.exists():
        return None
    try:
        raw = json.loads(where.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SchemaError("the event file is not valid JSON",
                          path=str(where), detail=error.msg) from None
    return EventFile.from_dict(raw)


def save(path: str | Path, held: EventFile) -> Path:
    """Write the file, atomically."""
    where = Path(require_str(str(path), "path"))
    where.parent.mkdir(parents=True, exist_ok=True)
    temporary = where.with_suffix(where.suffix + ".writing")
    temporary.write_text(json.dumps(held.to_dict(), indent=2, sort_keys=False) + "\n",
                         encoding="utf-8")
    os.replace(temporary, where)
    return where


def require(path: str | Path) -> EventFile:
    """Read an event file that has to be there."""
    held = load(path)
    if held is None:
        raise SchemaError("there is no event file there", path=str(path))
    return held
