"""Start blocks, punching starts and the people who miss theirs.

Three ways an event starts its runners, and they need different arithmetic:

**Timed start.** Everybody has a slot. Your time runs from your slot whether
you are standing on the line or still in the car park, which is the rule people
find harsh and which is the only one that works when four hundred runners share
one start lane.

**Punching start.** You start when you punch. There are no slots, only an open
window, and the arithmetic is trivial -- which is why small events do it.

**Blocks.** Classes are grouped into blocks with their own windows, so that the
juniors are not sent out into the dark and the elites do not follow each other
round. A block is a window and a set of classes, and the draw runs inside it.

A runner who misses their slot is **not** given a new one automatically. The
start official decides, and whatever they decide is recorded here: reinstated
at a new time, or started late on the original time, which is the difference
between a courtesy and a result.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..entries.competitor import Entry
from ..errors import ConflictError, RuleError, ValidationError
from ..util.order import sorted_by
from ..util.times import difference, format_time_of_day
from ..util.validate import require_int, require_list, require_one_of, require_str

START_KINDS = ["timed", "punching", "blocks"]

#: How late a runner may be and still be started on their own time.
GRACE_SECONDS = 120


@dataclass
class Block:
    """A window, and the classes that start in it."""

    name: str
    first_seconds: int
    last_seconds: int
    classes: list[str] = field(default_factory=list)
    interval_seconds: int = 60

    def __post_init__(self) -> None:
        self.name = require_str(self.name, "name", max_len=40)
        self.first_seconds = require_int(self.first_seconds, "first_seconds", minimum=0, maximum=86_399)
        self.last_seconds = require_int(self.last_seconds, "last_seconds", minimum=0, maximum=86_399)
        if self.last_seconds < self.first_seconds:
            raise ValidationError("a block cannot end before it starts", block=self.name)
        self.classes = [str(code).upper() for code in require_list(self.classes, "classes", max_len=60)]
        self.interval_seconds = require_int(self.interval_seconds, "interval_seconds",
                                            minimum=10, maximum=3600)

    @property
    def slots(self) -> int:
        """How many runners fit in the window."""
        return (self.last_seconds - self.first_seconds) // self.interval_seconds + 1

    def holds(self, class_code: str) -> bool:
        return str(class_code).upper() in self.classes

    def contains(self, seconds: int) -> bool:
        return self.first_seconds <= seconds <= self.last_seconds

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "first": format_time_of_day(self.first_seconds),
            "last": format_time_of_day(self.last_seconds),
            "classes": list(self.classes),
            "interval": self.interval_seconds,
            "slots": self.slots,
        }


@dataclass
class StartPlan:
    """How an event starts its runners."""

    kind: str = "timed"
    blocks: list[Block] = field(default_factory=list)
    window_first: int | None = None
    window_last: int | None = None

    def __post_init__(self) -> None:
        self.kind = require_one_of(self.kind, "kind", START_KINDS)
        if self.kind == "blocks" and not self.blocks:
            raise ValidationError("a block start needs blocks")
        if self.kind == "punching" and (self.window_first is None or self.window_last is None):
            raise ValidationError("a punching start needs a window")

    def block_for(self, class_code: str) -> Block | None:
        for block in self.blocks:
            if block.holds(class_code):
                return block
        return None

    def capacity(self) -> dict[str, int]:
        return {block.name: block.slots for block in self.blocks}

    def check(self, entries: list[Entry]) -> list[str]:
        """Everything that would stop the start working."""
        problems: list[str] = []
        if self.kind != "blocks":
            return problems

        wanted: dict[str, int] = {}
        for entry in entries:
            block = self.block_for(entry.class_code)
            if block is None:
                problems.append(f"class {entry.class_code} is not in any block")
                continue
            wanted[block.name] = wanted.get(block.name, 0) + 1

        for block in self.blocks:
            if wanted.get(block.name, 0) > block.slots:
                problems.append(f"block {block.name} holds {block.slots} but "
                                f"{wanted[block.name]} runners are in it")

        seen: set[str] = set()
        for block in self.blocks:
            for code in block.classes:
                if code in seen:
                    problems.append(f"class {code} is in more than one block")
                seen.add(code)
        return sorted(set(problems))


@dataclass
class LateStart:
    """A runner who missed their slot, and what was decided about it."""

    entry: str
    due_seconds: int
    arrived_seconds: int
    decision: str = "own-time"
    new_seconds: int | None = None

    def __post_init__(self) -> None:
        self.decision = require_one_of(self.decision, "decision",
                                       ["own-time", "reinstated", "refused"])
        if self.decision == "reinstated" and self.new_seconds is None:
            raise ValidationError("a reinstated runner needs a new start time",
                                  entry=self.entry)

    @property
    def late_by(self) -> int:
        return difference(self.due_seconds, self.arrived_seconds)

    @property
    def start_seconds(self) -> int | None:
        """The time their run is measured from, whatever was decided."""
        if self.decision == "refused":
            return None
        if self.decision == "reinstated":
            return self.new_seconds
        return self.due_seconds

    def to_dict(self) -> dict[str, object]:
        return {
            "entry": self.entry,
            "due": format_time_of_day(self.due_seconds),
            "arrived": format_time_of_day(self.arrived_seconds),
            "late_by": self.late_by,
            "decision": self.decision,
            "start": None if self.start_seconds is None else format_time_of_day(self.start_seconds),
        }


def late_runners(entries: list[Entry], punched: dict[str, int], *,
                 grace: int = GRACE_SECONDS) -> list[dict[str, object]]:
    """Who was late, and by how much.

    ``punched`` maps entry reference to when they actually went. Anybody inside
    the grace is not late at all -- the start lane is not a stopwatch.
    """
    require_int(grace, "grace", minimum=0, maximum=3600)
    rows = []
    for entry in entries:
        if entry.start_seconds is None or entry.reference not in punched:
            continue
        late = difference(entry.start_seconds, punched[entry.reference])
        if late > grace:
            rows.append({"entry": entry.reference,
                         "name": entry.competitor.listed_name,
                         "due": format_time_of_day(entry.start_seconds),
                         "arrived": format_time_of_day(punched[entry.reference]),
                         "late_by": late})
    return sorted_by(rows, lambda row: (-int(row["late_by"]), str(row["entry"])))


def assign_block_times(plan: StartPlan, entries: list[Entry]) -> dict[str, int]:
    """Give every entry a slot inside its block, in reference order.

    Deliberately simple: the separation draw runs afterwards, on the runners
    within each block. Doing both at once produces a draw nobody can check.
    """
    if plan.kind != "blocks":
        raise RuleError("that start plan does not use blocks", kind=plan.kind)

    times: dict[str, int] = {}
    used: dict[str, int] = {}
    for entry in sorted_by(entries, "reference"):
        block = plan.block_for(entry.class_code)
        if block is None:
            raise ConflictError("that class is not in any block", class_code=entry.class_code)
        index = used.get(block.name, 0)
        seconds = block.first_seconds + index * block.interval_seconds
        if seconds > block.last_seconds:
            raise ConflictError("that block is full", block=block.name, slots=block.slots)
        times[entry.reference] = seconds
        used[block.name] = index + 1
    return times
