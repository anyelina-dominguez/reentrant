"""British National Grid references.

Controls are pegged out with a GPS and written down as grid references, and
they arrive in every precision anyone has ever used::

    SK 12 34          a kilometre square
    SK 123 456        a hundred metres
    SK 1234 5678      ten metres
    SK 12345 67890    a metre
    433210,367890     eastings and northings, no square at all

All of them parse. The precision is kept, because it is the honest answer to
"how far apart are these two controls" -- two references given to a kilometre
are not a hundred metres apart no matter what the subtraction says.

The letter pair is the standard OS scheme: twenty-five 500 km squares lettered
A to Z without I, each divided into twenty-five 100 km squares the same way,
counted west to east and *north to south*, which is why the northing formula
subtracts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..errors import ValidationError

LETTERS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"

_LETTERED = re.compile(r"^([A-Z]{2})[\s]*([\d\s]+)$")
_NUMERIC = re.compile(r"^(\d{5,7})\s*[, ]\s*(\d{5,7})$")


def _square_origin(letters: str) -> tuple[int, int]:
    try:
        first = LETTERS.index(letters[0])
        second = LETTERS.index(letters[1])
    except ValueError:
        raise ValidationError("that is not a grid square", square=letters) from None
    easting = ((first - 2) % 5) * 500_000 + (second % 5) * 100_000
    northing = (19 - (first // 5) * 5 - (second // 5)) * 100_000
    if northing < 0:
        raise ValidationError("that grid square is off the national grid", square=letters)
    return easting, northing


def _square_letters(easting: int, northing: int) -> str:
    """The inverse of :func:`_square_origin`, derived from it rather than guessed."""
    if not (0 <= easting < 700_000 and 0 <= northing < 1_300_000):
        raise ValidationError("that position is off the national grid",
                              easting=easting, northing=northing)
    east_100 = easting // 100_000
    north_100 = northing // 100_000
    # northing = (19 - (first // 5) * 5 - (second // 5)) * 100_000
    remaining = 19 - north_100
    first = (remaining // 5) * 5 + ((east_100 // 5) + 2) % 5
    second = (remaining % 5) * 5 + east_100 % 5
    return LETTERS[first] + LETTERS[second]


@dataclass(frozen=True)
class Point:
    """A position, in metres, with the precision it was given to."""

    easting: int
    northing: int
    precision: int = 1

    def __post_init__(self) -> None:
        if self.precision not in (1, 10, 100, 1000, 10_000):
            raise ValidationError("precision must be a power of ten metres",
                                  precision=self.precision)

    @property
    def square(self) -> str:
        return _square_letters(self.easting, self.northing)

    def reference(self, digits: int = 3) -> str:
        """A lettered reference with ``digits`` digits in each half."""
        if digits not in (2, 3, 4, 5):
            raise ValidationError("a grid reference has two to five digits a side", digits=digits)
        scale = 10 ** (5 - digits)
        east = (self.easting % 100_000) // scale
        north = (self.northing % 100_000) // scale
        return f"{self.square} {east:0{digits}d} {north:0{digits}d}"

    def __str__(self) -> str:
        digits = {1: 5, 10: 4, 100: 3, 1000: 2, 10_000: 2}[self.precision]
        return self.reference(digits)


def parse(text: str, field: str = "position") -> Point:
    """A point from any of the forms above."""
    if not isinstance(text, str):
        raise ValidationError(f"{field} must be a grid reference", field=field)
    cleaned = text.strip().upper()

    numeric = _NUMERIC.match(cleaned)
    if numeric:
        east, north = int(numeric.group(1)), int(numeric.group(2))
        return Point(east, north, 1)

    lettered = _LETTERED.match(cleaned)
    if not lettered:
        raise ValidationError(f"{field} is not a grid reference", field=field, value=text)
    square, digit_text = lettered.groups()

    pieces = digit_text.split()
    if len(pieces) == 1:
        # Written without a gap: SK123456 is three digits each side, and an odd
        # number of digits has no honest reading at all.
        run = pieces[0]
        if len(run) % 2:
            raise ValidationError(f"{field} has an odd number of digits", field=field, value=text)
        half = len(run) // 2
        east_text, north_text = run[:half], run[half:]
    elif len(pieces) == 2:
        east_text, north_text = pieces
    else:
        raise ValidationError(f"{field} is not a grid reference", field=field, value=text)

    if len(east_text) != len(north_text):
        raise ValidationError(f"{field} has a different number of digits either side",
                              field=field, value=text)
    digits = len(east_text)
    if not 2 <= digits <= 5:
        raise ValidationError(f"{field} has two to five digits a side", field=field, value=text)

    origin_east, origin_north = _square_origin(square)
    scale = 10 ** (5 - digits)
    return Point(
        origin_east + int(east_text) * scale,
        origin_north + int(north_text) * scale,
        precision=scale,
    )


def coarsest(*points: Point) -> int:
    """The precision of the least precise point, which bounds any answer."""
    return max((point.precision for point in points), default=1)
