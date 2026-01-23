"""Distances and bearings on the grid.

The national grid is a projection, so Pythagoras is right here in a way it is
not on a sphere: two points a few kilometres apart on the same grid are a
straight subtraction away from each other, and the scale error over the size of
an orienteering map is far below the precision anyone pegged the controls to.

The thing this module is careful about is **precision**. Two controls given to
the nearest hundred metres are not "1,043 m" apart; they are "1,000 m apart,
give or take a hundred and forty". Every distance therefore comes back with the
uncertainty its inputs justify, and the course length that goes on the results
sheet is rounded to something the map can support.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..errors import ValidationError
from .grid import Point, coarsest


@dataclass(frozen=True)
class Distance:
    """Metres, and how much of that is guesswork."""

    metres: float
    uncertainty: float

    def rounded(self, to: int = 10) -> int:
        """Rounded to a sensible multiple, which is what goes on paper."""
        if to <= 0:
            raise ValidationError("cannot round to that", to=to)
        return int(round(self.metres / to) * to)

    def __str__(self) -> str:
        if self.uncertainty >= 1:
            return f"{self.rounded()} m ± {int(round(self.uncertainty))}"
        return f"{self.rounded()} m"


def between(start: Point, finish: Point) -> Distance:
    """Straight-line distance, with the uncertainty the precisions imply."""
    east = finish.easting - start.easting
    north = finish.northing - start.northing
    metres = math.hypot(east, north)
    # Each coordinate is somewhere inside its own square; the worst case is the
    # two errors adding along the line, which is the diagonal of the coarser one.
    step = coarsest(start, finish)
    uncertainty = 0.0 if step <= 1 else math.hypot(step, step)
    return Distance(metres, uncertainty)


def bearing(start: Point, finish: Point) -> float:
    """Degrees clockwise from grid north, in ``[0, 360)``."""
    east = finish.easting - start.easting
    north = finish.northing - start.northing
    if east == 0 and north == 0:
        return 0.0
    degrees = math.degrees(math.atan2(east, north))
    return degrees + 360 if degrees < 0 else degrees


def compass_point(degrees: float) -> str:
    """The eight-point compass name, for a control description."""
    names = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    index = int((degrees % 360) / 45 + 0.5) % 8
    return names[index]


def path_length(points: list[Point]) -> Distance:
    """The total of the legs through a list of points, uncertainty included.

    Uncertainties add in quadrature rather than linearly: a course of twenty
    legs each uncertain by a hundred metres is not two kilometres uncertain,
    because the errors are independent and mostly cancel.
    """
    if len(points) < 2:
        return Distance(0.0, 0.0)
    total = 0.0
    variance = 0.0
    for start, finish in zip(points, points[1:]):
        leg = between(start, finish)
        total += leg.metres
        variance += leg.uncertainty ** 2
    return Distance(total, math.sqrt(variance))


def climb(heights: list[float]) -> float:
    """Total ascent along a list of control heights, in metres.

    Orienteering climb is the sum of the *rises* only. A course that drops two
    hundred metres and climbs fifty has fifty metres of climb, and printing the
    net figure on the results sheet is a mistake somebody makes every season.
    """
    if len(heights) < 2:
        return 0.0
    return float(sum(max(0.0, b - a) for a, b in zip(heights, heights[1:])))


def descent(heights: list[float]) -> float:
    """The other half, for the courses that are mostly downhill."""
    if len(heights) < 2:
        return 0.0
    return float(sum(max(0.0, a - b) for a, b in zip(heights, heights[1:])))
