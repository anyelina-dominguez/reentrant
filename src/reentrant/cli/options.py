"""Argument parsing, without a dependency.

``--name value``, ``--name=value``, ``--flag``, and everything else is a
positional. That is the whole grammar. Short options are deliberately absent:
this gets run a dozen times on a Sunday morning by whoever is holding the
laptop, and ``--course`` is clearer than ``-c`` when it is raining.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from ..errors import ValidationError


@dataclass
class Arguments:
    options: dict[str, str | bool] = field(default_factory=dict)
    positional: list[str] = field(default_factory=list)

    def flag(self, name: str) -> bool:
        return bool(self.options.get(name))

    def value(self, name: str, default: str | None = None) -> str | None:
        got = self.options.get(name)
        if got is None or got is True:
            return default
        return str(got)

    def require(self, name: str) -> str:
        got = self.value(name)
        if got is None:
            raise ValidationError(f"--{name} is required", option=name)
        return got

    def number(self, name: str, default: int | None = None) -> int | None:
        got = self.value(name)
        if got is None:
            return default
        try:
            return int(got)
        except ValueError:
            raise ValidationError(f"--{name} must be a whole number", option=name) from None


def parse_args(argv: Sequence[str], *, flags: Sequence[str] = ()) -> Arguments:
    options: dict[str, str | bool] = {}
    positional: list[str] = []

    index = 0
    while index < len(argv):
        argument = argv[index]
        if not argument.startswith("--"):
            positional.append(argument)
            index += 1
            continue
        body = argument[2:]
        if body == "":
            positional.extend(argv[index + 1:])
            break
        if "=" in body:
            name, _, value = body.partition("=")
            options[name] = value
            index += 1
            continue
        if body in flags:
            options[body] = True
            index += 1
            continue
        following = argv[index + 1] if index + 1 < len(argv) else None
        if following is None or following.startswith("--"):
            options[body] = True
            index += 1
        else:
            options[body] = following
            index += 2
    return Arguments(options=options, positional=positional)
