"""Map scales.

A course is planned on the ground and printed on paper, and the two are
connected by a scale: 1:10000 means one millimetre on the map is ten metres on
the ground. Two things depend on it.

**Whether a course fits the paper.** A 7 km course on 1:15000 A4 fits; the same
course at 1:7500 does not, and the printer discovers this at eleven o'clock the
night before.

**Whether the control circles overlap.** A control circle is 5-6 mm across
whatever the scale, so two controls 40 m apart are 4 mm apart at 1:10000 and
their circles collide -- which is a map-drawing problem the planner would
rather know about while there is still time to move one.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..errors import ValidationError
from ..util.validate import require_int, require_number

#: The scales an orienteering map is printed at.
SCALES = [4000, 5000, 7500, 10000, 15000]

#: The diameter of a control circle on the printed map, in millimetres.
CIRCLE_MM = 6.0

#: Paper, in millimetres, portrait.
PAPER = {"A5": (148, 210), "A4": (210, 297), "A3": (297, 420)}


@dataclass(frozen=True)
class Scale:
    """One over something."""

    denominator: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "denominator",
                           require_int(self.denominator, "scale", minimum=500, maximum=100_000))

    @property
    def name(self) -> str:
        return f"1:{self.denominator}"

    def to_millimetres(self, metres: float) -> float:
        """Ground metres to millimetres on the paper."""
        return require_number(metres, "metres", minimum=0) * 1000 / self.denominator

    def to_metres(self, millimetres: float) -> float:
        """And back."""
        return require_number(millimetres, "millimetres", minimum=0) * self.denominator / 1000

    def circles_overlap(self, metres: float) -> bool:
        """Whether two controls that far apart have colliding circles."""
        return self.to_millimetres(metres) < CIRCLE_MM

    def __str__(self) -> str:
        return self.name


def standard(denominator: int) -> Scale:
    """A scale, refusing anything an orienteering map is not printed at."""
    if denominator not in SCALES:
        raise ValidationError("that is not a standard map scale",
                              scale=denominator, allowed=SCALES)
    return Scale(denominator)


def fits(width_metres: float, height_metres: float, scale: Scale,
         paper: str = "A4", *, margin_mm: float = 20.0) -> bool:
    """Whether a piece of ground fits the paper at a scale, either way up."""
    if paper not in PAPER:
        raise ValidationError("no paper that size", paper=paper, allowed=sorted(PAPER))
    short, long = PAPER[paper]
    usable = (short - margin_mm, long - margin_mm)
    wide = scale.to_millimetres(width_metres)
    tall = scale.to_millimetres(height_metres)
    return ((wide <= usable[0] and tall <= usable[1])
            or (wide <= usable[1] and tall <= usable[0]))


def largest_fitting(width_metres: float, height_metres: float, paper: str = "A4",
                    *, margin_mm: float = 20.0) -> Scale | None:
    """The most detailed standard scale that still fits, or ``None``."""
    for denominator in sorted(SCALES):
        scale = Scale(denominator)
        if fits(width_metres, height_metres, scale, paper, margin_mm=margin_mm):
            return scale
    return None


def extent(points) -> tuple[float, float]:
    """The width and height of the ground a set of positions covers, in metres."""
    eastings = [point.easting for point in points]
    northings = [point.northing for point in points]
    if not eastings:
        return 0.0, 0.0
    return float(max(eastings) - min(eastings)), float(max(northings) - min(northings))
