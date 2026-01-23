"""IOF control descriptions.

The little grid of pictograms on a control description slip is a formal
language, and it has eight columns:

===  ==========================================================
 A   which control this is on the course -- 1, 2, 3
 B   the control code, the number on the kite
 C   which of several similar features -- northern, upper, middle
 D   the feature itself -- boulder, knoll, path junction
 E   what it looks like -- ruined, overgrown, marshy
 F   how big it is, or the second feature of a pair
 G   where the marker is on the feature -- north side, foot, between
 H   anything else -- manned, first aid, refreshments
===  ==========================================================

Only D is compulsory: a control is always *something*. This module holds the
vocabulary and renders a description in the text form used on a start list,
because rendering the pictograms is a font problem and this is not.

The vocabulary here is the subset a British forest event actually uses. It is
not the whole of the IOF table, and the missing symbols are the ones for
terrain nobody round here has.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import ValidationError
from ..util.validate import optional, require_one_of, require_str

#: Column D: the feature the control is on.
FEATURES = {
    "boulder": "boulder",
    "boulder-field": "boulder field",
    "cliff": "cliff",
    "crag": "crag",
    "knoll": "knoll",
    "depression": "depression",
    "pit": "pit",
    "re-entrant": "re-entrant",
    "spur": "spur",
    "gully": "gully",
    "earth-bank": "earth bank",
    "ditch": "ditch",
    "marsh": "marsh",
    "pond": "pond",
    "stream": "stream",
    "water-hole": "water hole",
    "well": "well",
    "clearing": "clearing",
    "thicket": "thicket",
    "vegetation-boundary": "vegetation boundary",
    "path": "path",
    "track": "track",
    "ride": "ride",
    "road": "road",
    "fence": "fence",
    "wall": "wall",
    "building": "building",
    "ruin": "ruin",
    "tower": "tower",
    "cairn": "cairn",
    "fodder-rack": "fodder rack",
    "charcoal-burning-platform": "charcoal burning platform",
    "special-item": "special item",
}

#: Column C: which of several.
WHICH = ["northern", "southern", "eastern", "western", "upper", "lower",
         "middle", "north-eastern", "north-western", "south-eastern", "south-western"]

#: Column E: what it looks like.
APPEARANCE = ["ruined", "overgrown", "marshy", "sandy", "rocky", "open",
              "needle-leaved", "broad-leaved", "indistinct", "deep", "shallow"]

#: Column G: where the marker hangs.
LOCATIONS = ["north-side", "south-side", "east-side", "west-side", "foot",
             "top", "between", "crossing", "junction", "bend", "end",
             "inside-corner", "outside-corner", "north-east-side", "north-west-side"]

#: Column H: what else is there.
OTHER = ["manned", "first-aid", "refreshments", "radio", "spectator",
         "map-exchange", "no-marker"]

_HYPHENS = str.maketrans({"-": " "})


def _words(value: str) -> str:
    return value.translate(_HYPHENS)


@dataclass(frozen=True)
class Description:
    """One row of the description sheet: columns C to H."""

    feature: str
    which: str | None = None
    appearance: str | None = None
    dimensions: str | None = None
    location: str | None = None
    other: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "feature", require_one_of(
            require_str(self.feature, "feature", max_len=40), "feature", sorted(FEATURES)))
        for field, allowed in (("which", WHICH), ("appearance", APPEARANCE),
                               ("location", LOCATIONS), ("other", OTHER)):
            value = getattr(self, field)
            if value is not None:
                object.__setattr__(self, field, require_one_of(value, field, allowed))
        if self.dimensions is not None:
            object.__setattr__(self, "dimensions", require_str(self.dimensions, "dimensions", max_len=20))

    def text(self) -> str:
        """The description as a person would read it out.

        Word order follows the columns: which, appearance, feature, dimensions,
        location, other -- so "northern overgrown re-entrant, foot" rather than
        anything a translation might rearrange.
        """
        parts: list[str] = []
        if self.which:
            parts.append(_words(self.which))
        if self.appearance:
            parts.append(_words(self.appearance))
        parts.append(FEATURES[self.feature])
        if self.dimensions:
            parts.append(self.dimensions)
        head = " ".join(parts)
        tail = [_words(value) for value in (self.location, self.other) if value]
        return head + ("" if not tail else ", " + ", ".join(tail))

    def to_dict(self) -> dict[str, str | None]:
        return {
            "feature": self.feature,
            "which": self.which,
            "appearance": self.appearance,
            "dimensions": self.dimensions,
            "location": self.location,
            "other": self.other,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, str | None]) -> "Description":
        if not isinstance(raw, dict):
            raise ValidationError("a description is an object")
        return cls(
            feature=raw.get("feature", ""),
            which=optional(raw.get("which"), lambda v: require_str(v, "which")),
            appearance=optional(raw.get("appearance"), lambda v: require_str(v, "appearance")),
            dimensions=optional(raw.get("dimensions"), lambda v: require_str(v, "dimensions")),
            location=optional(raw.get("location"), lambda v: require_str(v, "location")),
            other=optional(raw.get("other"), lambda v: require_str(v, "other")),
        )


def parse_description(text: str) -> Description:
    """A description from the shorthand a planner types: ``re-entrant/foot``.

    ``feature`` or ``which:feature`` or ``feature/location`` or the lot:
    ``northern:overgrown:re-entrant/foot``.
    """
    cleaned = require_str(text, "description", max_len=120).lower()
    head, _, location = cleaned.partition("/")
    parts = [part.strip() for part in head.split(":") if part.strip()]
    if not parts:
        raise ValidationError("a description needs a feature", value=text)

    feature = parts[-1]
    which = appearance = None
    for part in parts[:-1]:
        if part in WHICH:
            which = part
        elif part in APPEARANCE:
            appearance = part
        else:
            raise ValidationError("that is not a description word", word=part, value=text)
    return Description(
        feature=feature,
        which=which,
        appearance=appearance,
        location=location.strip() or None,
    )
