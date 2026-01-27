"""Controls: the kites in the forest and the set of them for an event.

A control is a code, a place, and a description. The set of controls for an
event is not just a list: it enforces the two rules that stop a competitor
punching the wrong thing.

**Codes are unique within an event.** Two kites with 104 on them is the fault
that produces an unwinnable protest, because the punch record cannot say which
one was visited.

**Controls on similar features must not be close together.** The IOF rule is
that two controls on the same kind of feature must be at least
``SIMILAR_FEATURE_METRES`` apart, and any two controls at least
``ANY_FEATURE_METRES`` apart. A runner who finds a kite where they expected one
is entitled to assume it is theirs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..errors import ConflictError, NotFoundError, RuleError, ValidationError
from ..geo import distance as geo
from ..geo.grid import Point, parse as parse_grid
from ..util.ids import FINISH_CODE, START_CODE, next_free_code, require_control_code
from ..util.order import sorted_by
from ..util.validate import optional, require_mapping, require_number, require_str
from .descriptions import Description

#: Two controls on the same sort of feature must be this far apart.
SIMILAR_FEATURE_METRES = 60.0

#: And any two controls at all, this far.
ANY_FEATURE_METRES = 30.0


@dataclass(frozen=True)
class Control:
    """One kite."""

    code: str
    position: Point
    description: Description | None = None
    height: float | None = None
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", require_control_code(self.code))
        if not isinstance(self.position, Point):
            raise ValidationError("a control needs a position", field="position")
        if self.description is not None and not isinstance(self.description, Description):
            raise ValidationError("a description must be a Description", field="description")
        if self.height is not None:
            object.__setattr__(self, "height", require_number(self.height, "height",
                                                             minimum=-500, maximum=5000))
        object.__setattr__(self, "note", (self.note or "").strip())

    @property
    def is_start(self) -> bool:
        return self.code == START_CODE

    @property
    def is_finish(self) -> bool:
        return self.code == FINISH_CODE

    @property
    def feature(self) -> str | None:
        return None if self.description is None else self.description.feature

    def describe(self) -> str:
        """The line that goes on the description sheet."""
        text = "" if self.description is None else self.description.text()
        return f"{self.code:>4}  {text}".rstrip()

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "position": str(self.position),
            "description": None if self.description is None else self.description.to_dict(),
            "height": self.height,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, object]) -> "Control":
        data = require_mapping(raw, "control")
        described = data.get("description")
        return cls(
            code=str(data.get("code", "")),
            position=parse_grid(require_str(data.get("position"), "position")),
            description=None if described is None else Description.from_dict(described),  # type: ignore[arg-type]
            height=optional(data.get("height"), lambda v: require_number(v, "height")),
            note=str(data.get("note") or ""),
        )


@dataclass
class ControlSet:
    """Every control put out for an event."""

    controls: dict[str, Control] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.controls)

    def __contains__(self, code: object) -> bool:
        return str(code) in self.controls

    def add(self, control: Control) -> Control:
        if control.code in self.controls:
            raise ConflictError("that control code is already out", code=control.code)
        self.controls[control.code] = control
        return control

    def put(self, control: Control) -> Control:
        """Add or replace, for loading a file."""
        self.controls[control.code] = control
        return control

    def require(self, code: str) -> Control:
        control = self.controls.get(require_control_code(code))
        if control is None:
            raise NotFoundError("no such control", code=code)
        return control

    def get(self, code: str) -> Control | None:
        return self.controls.get(str(code))

    def remove(self, code: str) -> Control:
        control = self.require(code)
        del self.controls[control.code]
        return control

    def all(self) -> list[Control]:
        """Every control, start and finish last so the list reads as a plan."""
        return sorted_by(self.controls.values(),
                         lambda c: (c.is_start or c.is_finish, c.code))

    def codes(self) -> list[str]:
        return [control.code for control in self.all()]

    def next_code(self, *, start: int = 31) -> str:
        return next_free_code(self.controls, start=start)

    def near(self, position: Point, metres: float) -> list[tuple[Control, float]]:
        """Every control within a distance, nearest first."""
        found = []
        for control in self.all():
            gap = geo.between(position, control.position).metres
            if gap <= metres:
                found.append((control, gap))
        return sorted_by(found, lambda pair: (pair[1], pair[0].code))

    def conflicts(self) -> list[dict[str, object]]:
        """Pairs of controls that are too close to be told apart.

        Returns the offending pairs with the rule each one broke, rather than
        raising: a planner wants the whole list to fix in one pass.
        """
        found: list[dict[str, object]] = []
        controls = [control for control in self.all() if not (control.is_start or control.is_finish)]
        for index, control in enumerate(controls):
            for other in controls[index + 1:]:
                gap = geo.between(control.position, other.position).metres
                same_feature = (control.feature is not None and control.feature == other.feature)
                limit = SIMILAR_FEATURE_METRES if same_feature else ANY_FEATURE_METRES
                if gap < limit:
                    found.append({
                        "codes": [control.code, other.code],
                        "metres": round(gap, 1),
                        "limit": limit,
                        "reason": "similar features too close" if same_feature else "controls too close",
                    })
        return sorted_by(found, lambda row: (row["metres"], row["codes"][0]))

    def check(self) -> None:
        """Raise on the first conflict, for the code path that cannot continue."""
        problems = self.conflicts()
        if problems:
            first = problems[0]
            raise RuleError(
                f"controls {first['codes'][0]} and {first['codes'][1]} are {first['metres']} m apart",
                **first,
            )

    def to_list(self) -> list[dict[str, object]]:
        return [control.to_dict() for control in self.all()]

    @classmethod
    def from_list(cls, rows: list[dict[str, object]]) -> "ControlSet":
        controls = cls()
        for row in rows:
            controls.put(Control.from_dict(row))
        return controls
