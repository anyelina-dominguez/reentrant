#!/usr/bin/env python3
"""The command line.

Nothing prints except :func:`main`, at the very bottom. Every command returns
the lines it would have printed, which is what makes them testable without
capturing stdout.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Sequence

from ..errors import ReentrantError, status_of
from ..store.jsonstore import EventFile, load, save
from . import commands
from .options import Arguments, parse_args

DEFAULT_PATH = "event.json"

FLAGS = ["csv", "help", "quiet"]

COMMANDS: dict[str, Callable[..., commands.Outcome]] = {
    "new": commands.new_event,
    "show": commands.show,
    "check": commands.check,
    "import": commands.import_entries,
    "draw": commands.draw,
    "starts": commands.starts,
    "download": commands.download,
    "results": commands.results,
    "splits": commands.splits,
    "export-entries": commands.export_entries,
}

#: Commands that work without an event file already existing.
WITHOUT_FILE = {"new"}

USAGE = [
    "usage: reentrant <command> [options]",
    "",
    "  new <name> <date>      start an event file",
    "  show                   what is in it",
    "  check                  everything that would stop the event running",
    "  import --file f.csv    read an entry list",
    "  draw --first 10:00:00  draw the start list",
    "  starts                 the start list as it stands",
    "  download --file f.json put a log of card reads through",
    "  results [--by course]  the results, --csv for the spreadsheet",
    "  splits --course Blue   the splits for one course",
    "  export-entries         the entry list back out as csv",
    "",
    "common options:",
    "  --event <path>         the event file (default event.json)",
]


def run(argv: Sequence[str]) -> commands.Outcome:
    arguments: Arguments = parse_args(argv, flags=FLAGS)
    if not arguments.positional or arguments.flag("help"):
        return commands.Outcome(0 if arguments.positional else 1, USAGE)

    name = arguments.positional[0]
    command = COMMANDS.get(name)
    if command is None:
        return commands.Outcome(1, [f"no such command: {name}", ""] + USAGE)

    arguments.positional = list(arguments.positional[1:])
    path = Path(arguments.value("event", DEFAULT_PATH) or DEFAULT_PATH)

    try:
        held = load(path)
        if held is None and name not in WITHOUT_FILE:
            return commands.Outcome(1, [f"there is no event file at {path}",
                                        "start one with: reentrant new <name> <date>"])
        outcome = command(arguments, held, path)
        if outcome.save:
            if outcome.event is not None:
                held = EventFile(event=outcome.event)
            if held is not None:
                save(path, held)
        return outcome
    except ReentrantError as error:
        return commands.Outcome(1 if status_of(error) < 500 else 2,
                                [f"{type(error).__name__}: {error.message}"])
    except (OSError, ValueError) as error:
        return commands.Outcome(2, [f"{type(error).__name__}: {error}"])


def main(argv: Sequence[str] | None = None) -> int:
    outcome = run(sys.argv[1:] if argv is None else argv)
    for line in outcome.lines:
        print(line)
    return outcome.status


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
