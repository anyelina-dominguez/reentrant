# Working on reentrant

## Before anything

    make test

Everything green, always. A commit that leaves the suite red is a commit
somebody has to bisect through in five years, on the Saturday night before a
badge event.

## The shape of a change

Tests go in with the code that makes them pass, in the same commit. Not
afterwards and not in a separate "add tests" commit -- writing them together is
what gets the interface designed by its first caller.

A module gets one test file named after it. A test file getting long usually
means the module is doing two things.

## Conventions that are not up for discussion

`docs/conventions.md` has them in full. The short version:

- everything timed is a whole number of seconds
- positions carry the precision they were given to
- control codes are 31 and above
- every returned list is sorted by a key that cannot tie
- decisions about a run are recorded, never typed over the punches

The last one has been broken twice and cost a protest both times.

## Dependencies

There are none. Adding one needs a reason that survives the question "what does
this cost in ten years, on a laptop in a field, with no signal". The standard
library has a test runner, an HTTP server, CSV and JSON; that has been enough.

## Rules of the sport

Anything that encodes a rule -- separation distances, age classes, protest
windows -- gets a comment saying which rule and a test with the boundary case
in it. The rules change every few years and the next person needs to know what
they are changing.
