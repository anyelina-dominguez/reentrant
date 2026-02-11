"""Migrations for the event file.

The file carries a version, and opening one written by an older build upgrades
it in memory on the way past. Nothing rewrites the file until something saves
it, so an old file opened and closed unchanged stays as it was.

There is no downgrade. An old build opening a new file is refused, because the
alternative is an old build silently dropping fields it does not understand --
and the field it drops will be the one holding somebody's result.
"""

from __future__ import annotations

from typing import Any, Callable

from ..errors import SchemaError

CURRENT_VERSION = 2

_STEPS: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}


def step(version: int) -> Callable[[Callable[[dict[str, Any]], dict[str, Any]]],
                                   Callable[[dict[str, Any]], dict[str, Any]]]:
    """Register the upgrade from ``version`` to ``version + 1``."""

    def register(upgrade: Callable[[dict[str, Any]], dict[str, Any]]):
        _STEPS[version] = upgrade
        return upgrade

    return register


def migrate(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise SchemaError("the event file is not an object")
    version = raw.get("version", 0)
    if not isinstance(version, int) or isinstance(version, bool) or version < 0:
        raise SchemaError("the event file has no usable version", version=raw.get("version"))
    if version > CURRENT_VERSION:
        raise SchemaError("that file was written by a newer version of reentrant",
                          version=version, understood=CURRENT_VERSION)

    current = dict(raw)
    for from_version in range(version, CURRENT_VERSION):
        upgrade = _STEPS.get(from_version)
        if upgrade is None:
            raise SchemaError("no way to upgrade that file",
                              **{"from": from_version, "to": from_version + 1})
        current = {**upgrade(current), "version": from_version + 1}
    return current


@step(0)
def _from_nothing(raw: dict[str, Any]) -> dict[str, Any]:
    """Version 0 is what the first fortnight wrote: an event and nothing else."""
    return {
        "event": raw.get("event", raw),
        "downloads": raw.get("downloads", []),
    }


@step(1)
def _add_results(raw: dict[str, Any]) -> dict[str, Any]:
    """Version 2 keeps the results as saved, rather than recomputing them.

    Recomputing was the original plan and it was wrong: a result that has been
    corrected by hand at the desk -- a reinstated mispunch, a disqualification
    -- has to survive the file being reopened, and the punches alone cannot say
    that happened.
    """
    return {**raw, "results": raw.get("results", []), "draws": raw.get("draws", [])}
