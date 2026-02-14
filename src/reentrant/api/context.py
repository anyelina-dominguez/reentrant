"""What the routes are given.

One of these is built at start-up and handed to every handler. It holds the
event, the cards read so far, the results as corrected, and -- when the server
was started against a file -- where to save them.

The clock is here rather than read from ``datetime.now()`` at the point of use,
because half the behaviour depends on what time it is and a system whose
behaviour depends on the wall clock cannot be tested.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..event.download import Download
from ..event.event import Event
from ..results.classify import Result
from ..store.jsonstore import EventFile, save
from ..timing.punch import CardRead


class Clock:
    """The time of day in seconds, stoppable for tests."""

    def __init__(self, fixed: int | None = None) -> None:
        self._fixed = fixed

    def seconds(self) -> int:
        if self._fixed is not None:
            return self._fixed
        now = datetime.now(timezone.utc)
        return now.hour * 3600 + now.minute * 60 + now.second

    @classmethod
    def stopped_at(cls, seconds: int) -> "Clock":
        return cls(seconds)


@dataclass
class Context:
    """Everything the handlers work on."""

    event: Event
    downloads: list[CardRead] = field(default_factory=list)
    processed: list[Download] = field(default_factory=list)
    results: list[Result] = field(default_factory=list)
    path: Path | None = None
    clock: Clock = field(default_factory=Clock)

    def as_file(self) -> EventFile:
        return EventFile(event=self.event, downloads=self.downloads, results=self.results)

    def persist(self) -> bool:
        """Write the file, if the server was started against one."""
        if self.path is None:
            return False
        save(self.path, self.as_file())
        return True

    @classmethod
    def from_file(cls, held: EventFile, path: Path | None = None) -> "Context":
        return cls(event=held.event, downloads=list(held.downloads),
                   results=list(held.results), path=path)
