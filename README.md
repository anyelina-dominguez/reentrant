# reentrant

Running an orienteering event: the courses, who entered, what they punched, and
who won.

Python 3.12. No dependencies.

    make test

## What it is for

A club fixture with four hundred runners, eight courses and a download tent
staffed by whoever got there first. The software has to be right about one
thing above all: **whether a run counts**. Everything else can be fixed in the
morning; a wrongly voided run means somebody drove two hours for nothing.

    python3 -m reentrant.cli.main --help
    python3 -m reentrant.cli.main new "Longshaw club fixture" 2026-05-09
    python3 -m reentrant.cli.main import --file entries.csv
    python3 -m reentrant.cli.main draw --first 10:00:00
    python3 -m reentrant.cli.main download --file cards.json
    python3 -m reentrant.cli.main results
    python3 -m reentrant.cli.main serve --port 8080

Or watch the whole thing happen in memory:

    python3 examples/run_the_day.py
    python3 examples/plan_check.py

## What is here

    reentrant.geo          grid references, distances, map scales, route traces
    reentrant.courses      controls, descriptions, courses, planning checks,
                           description sheets, course statistics
    reentrant.entries      competitors, age classes, entries, hire cards
    reentrant.starts       the draw, start blocks, late starts
    reentrant.timing       punches, whether a run counts, backup punching,
                           corrections at the desk
    reentrant.results      the results list, splits, relays, handicaps, club
                           teams, protests
    reentrant.event        the event, the download tent, fixtures, the report
    reentrant.reports      the printed sheets, the board, CSV out
    reentrant.store        the event file and its migrations
    reentrant.api          a small router and an http surface over all of it
    reentrant.cli          sixteen commands over the same objects

## The one rule

**The punches must contain the course's controls, in order, as a subsequence.**

Everything about scoring a run follows from that sentence:

- extra punches are ignored, never penalised -- a runner who punches somebody
  else's control on the way past has done nothing wrong;
- the first punch that fits is the one that counts, which is what makes an
  overshoot and return a valid run: `101, 103, 102, 103` is a clean run of
  `101, 102, 103`;
- a missing finish is not a mispunch. It is a run that cannot be timed, which
  is a different thing with a different fix.

## The other rule

**Decisions are recorded, never typed over the data.** A reinstated mispunch, a
disqualification, a voided control, a jury's finding: each is a separate record
with a name and a reason on it. Re-running the results over the same download
with the same decisions gives the same answer, and the original card read is
still there to be argued with.

There is a revert in this repository's history for a change that broke that
rule, with the reasoning in the commit message.

## The documents worth reading first

- `docs/a-day.md` -- an event from the entry list to the write-up
- `docs/conventions.md` -- the arguments not worth having twice
- `docs/api.md` -- the http surface
- `CONTRIBUTING.md` -- what a change is expected to look like

## What it does not do

No map drawing, no course planning, no printing, and nothing that talks to an
SI station. Cards arrive as JSON from whatever read them. Courses arrive as a
text file from whatever drew them. This is the part in the middle.
