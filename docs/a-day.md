# A day, from the entry list to the write-up

The same sequence `examples/run_the_day.py` runs, in the commands you would
actually type. Everything works on one file.

    reentrant new "Longshaw club fixture" 2026-05-09 --venue Longshaw

## The week before: courses

Courses come out of whatever drew them as two text files -- see
`reentrant.courses.exchange` for the shape -- and go in with the controls. Then:

    reentrant check

That prints two things and they are different. **Problems** stop the event:
a course using a control that is not out, a class pointed at a course that does
not exist, two controls too close to tell apart. **Notes** are what a
controller would mention: dog-legs, legs under a hundred metres, courses that
all start to the same control.

    reentrant describe --course Blue
    reentrant collect

The first is the description slip. The second is the list for whoever picks the
kites up, which is by code rather than by course, and includes controls no
course used -- they are still out there.

## Entries

    reentrant import --file entries.csv

Column names are matched against the spellings that actually turn up: `SI
Card`, `Chip`, `YOB`, `Year of Birth`. **One bad row does not lose the file** --
the import says which lines it could not use and imports the rest.

    reentrant draw --first 10:00:00 --interval 60
    reentrant starts

The draw keeps clubmates two slots apart and families three, and reports any
pair it could not separate rather than shuffling forever. It is seeded from the
event name, so redrawing after a late entry gives the same list with the
newcomer slotted in.

## The day

    reentrant download --file cards.json
    reentrant board --at 13:30:00

A card read produces a slip with the splits on it. A card nobody entered, a
mispunch, a missing finish -- all of them come back as a sentence for the
person at the desk, not an exception.

The board says **PROVISIONAL** while anybody is still out, prints the time it
was printed, and shows how many are unaccounted for on each course. Both of
those exist because somebody once argued from a copy printed two hours earlier.

### When something is wrong

A control found knocked over, a card that failed to record a punch everybody
watched happen, a runner who cut the course and said so. Each is a decision:

    curl -sX POST localhost:8080/corrections -H 'content-type: application/json' \
      -d '{"entry":"ENT-0042","decision":"reinstate","reason":"102 was found in the bracken","by":"organiser"}'

The punches are never edited. The decision is a separate record with a name on
it, and the results are rebuilt from the download plus the decisions -- so
re-running gives the same answer and the original is still there to argue with.

A formal complaint follows the same route: complaint to the organiser within
fifteen minutes of the results going up, protest to the jury within fifteen of
the answer, and the jury's finding produces a correction like any other.

## Afterwards

    reentrant results
    reentrant results --by course --csv
    reentrant splits --course Blue
    reentrant report --note "the download queue reached eleven people at 13:10"

The splits carry the analysis: who was fastest on each leg, the superman time,
and where each runner lost time against **their own** form for the day -- taken
as a median, so the one leg they spent in a thicket does not set the standard
they are judged by.

The report says whether each course came out at its target winning time, which
is the only feedback a planner ever gets.
