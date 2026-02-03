"""Age classes.

The rule that catches everyone: **a competitor's class is worked out from
their age on the thirty-first of December of the event's year**, not from their
age on the day. Somebody born in November is in next year's class from the
first of January, which feels wrong to them every single season.

Junior classes are ceilings: M14 is "fourteen or under on 31 December".
Veteran classes are floors: M45 is "forty-five or over". M21 is open, with no
age restriction in either direction, and it is the class everybody in between
runs.

Who may run what is a separate question from what class you are, and it is
deliberately generous: a junior may run up into an older class or into open, a
veteran may run down into open, and nobody may run in a junior class they have
aged out of. That last one is not snobbery -- junior courses are planned for
juniors, and an adult on them distorts the results.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from ..errors import ValidationError
from ..util.validate import require_int, require_one_of, require_str

SEXES = ["M", "W"]

#: Junior ceilings, youngest first.
JUNIOR_AGES = [10, 12, 14, 16, 18, 20]

#: Veteran floors, youngest first.
VETERAN_AGES = [35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95]

#: The open class, which has no age limit at either end.
OPEN_AGE = 21

_CLASS = re.compile(r"^([MW])(\d{2})$")


@dataclass(frozen=True)
class AgeClass:
    """One class, such as ``M45``."""

    sex: str
    age: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "sex", require_one_of(self.sex, "sex", SEXES))
        if self.age not in JUNIOR_AGES + [OPEN_AGE] + VETERAN_AGES:
            raise ValidationError("that is not a class that exists", age=self.age)

    @property
    def code(self) -> str:
        return f"{self.sex}{self.age}"

    @property
    def is_junior(self) -> bool:
        return self.age in JUNIOR_AGES

    @property
    def is_veteran(self) -> bool:
        return self.age in VETERAN_AGES

    @property
    def is_open(self) -> bool:
        return self.age == OPEN_AGE

    def admits(self, age: int) -> bool:
        """Whether somebody of this age is *in* this class, by age alone."""
        if self.is_open:
            return True
        if self.is_junior:
            return age <= self.age
        return age >= self.age

    def __str__(self) -> str:
        return self.code


def parse_class(text: str, field: str = "class") -> AgeClass:
    """``M45`` or ``w21`` to an :class:`AgeClass`."""
    cleaned = require_str(text, field, max_len=4).upper()
    match = _CLASS.match(cleaned)
    if match is None:
        raise ValidationError(f"{field} is not an age class", field=field, value=text)
    return AgeClass(sex=match.group(1), age=int(match.group(2)))


def age_at_year_end(birth_year: int, event_year: int) -> int:
    """Age on the thirty-first of December of the event's year."""
    birth = require_int(birth_year, "birth_year", minimum=1900, maximum=2200)
    event = require_int(event_year, "event_year", minimum=1900, maximum=2200)
    age = event - birth
    if age < 0:
        raise ValidationError("that competitor is not born yet",
                              birth_year=birth, event_year=event)
    return age


def class_for(birth_year: int, event_year: int, sex: str) -> AgeClass:
    """The class a competitor belongs in."""
    age = age_at_year_end(birth_year, event_year)
    letter = require_one_of(str(sex).upper(), "sex", SEXES)
    for ceiling in JUNIOR_AGES:
        if age <= ceiling:
            return AgeClass(letter, ceiling)
    floor = OPEN_AGE
    for veteran in VETERAN_AGES:
        if age >= veteran:
            floor = veteran
    return AgeClass(letter, floor)


def eligible_classes(birth_year: int, event_year: int, sex: str) -> list[AgeClass]:
    """Every class a competitor may enter, youngest first.

    Their own class, open, and -- for a junior -- the junior classes above
    theirs. A veteran may run open or any veteran class up to their own.
    """
    age = age_at_year_end(birth_year, event_year)
    letter = require_one_of(str(sex).upper(), "sex", SEXES)
    own = class_for(birth_year, event_year, letter)

    allowed: list[AgeClass] = []
    if own.is_junior:
        allowed.extend(AgeClass(letter, ceiling) for ceiling in JUNIOR_AGES if ceiling >= own.age)
        allowed.append(AgeClass(letter, OPEN_AGE))
    elif own.is_open:
        allowed.append(own)
    else:
        allowed.append(AgeClass(letter, OPEN_AGE))
        allowed.extend(AgeClass(letter, veteran) for veteran in VETERAN_AGES if veteran <= own.age)
    return sorted(allowed, key=lambda entry: (entry.age == OPEN_AGE, entry.age))


def may_enter(birth_year: int, event_year: int, sex: str, wanted: AgeClass | str) -> bool:
    """Whether a competitor may enter a class they have asked for."""
    target = wanted if isinstance(wanted, AgeClass) else parse_class(str(wanted))
    return any(entry.code == target.code for entry in eligible_classes(birth_year, event_year, sex))


def all_classes(sex: str) -> list[AgeClass]:
    """Every class that exists for one sex, youngest first."""
    letter = require_one_of(str(sex).upper(), "sex", SEXES)
    ages = JUNIOR_AGES + [OPEN_AGE] + VETERAN_AGES
    return [AgeClass(letter, age) for age in ages]
