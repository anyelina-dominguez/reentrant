"""Running an orienteering event: the courses, who entered, what they punched,
and who won.

The packages, in the order a day uses them::

    reentrant.geo          grid references, distances, map scales, route traces
    reentrant.courses      controls, descriptions, courses, planning checks
    reentrant.entries      competitors, age classes, entries, hire cards
    reentrant.starts       the draw, start blocks, late starts
    reentrant.timing       punches, whether a run counts, backup punching
    reentrant.results      the results list, splits, relays, handicaps, teams
    reentrant.event        the event itself, the download tent, fixtures
    reentrant.reports      the printed sheets and the board
    reentrant.store        the event file and its migrations
    reentrant.api          an http surface over all of it
    reentrant.cli          the command line, which is what gets used

Everything timed is a whole number of seconds. Every list that comes back is
sorted by an explicit key whose last field cannot tie. Both of those are in
``docs/conventions.md`` with the reasons.
"""

from .errors import (
    ConflictError, NotFoundError, ReentrantError, RuleError, SchemaError,
    ValidationError, status_of,
)

__version__ = "0.5.0"

__all__ = [
    "ReentrantError",
    "ValidationError",
    "NotFoundError",
    "ConflictError",
    "RuleError",
    "SchemaError",
    "status_of",
    "__version__",
]
