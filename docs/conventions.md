# Conventions

Written down once, because every one of these has been got wrong at least once
in somebody's results and the argument is not worth having twice.

## Time

- Everything timed is a **whole number of seconds**. Not a float, not a
  `timedelta`, not a wall clock. Splits have to add up to the total exactly,
  and floats do not.
- A **time of day** is seconds since midnight. An **elapsed time** is a
  duration. `difference(start, finish)` handles a finish after midnight; a
  plain subtraction does not.
- Times are written `mm:ss` under an hour and `h:mm:ss` over it. Minutes may
  run past sixty in the two-field form, because a results list prints a
  seventy-three minute run as `73:12` at least as often as `1:13:12`.

## The sky is not involved, but the grid is

- Positions are **British National Grid**, in metres, as a `Point`.
- A point carries the **precision it was given to**. Two controls given to a
  kilometre are not a hundred metres apart no matter what the subtraction says,
  and every distance comes back with the uncertainty its inputs justify.
- Bearings run **clockwise from grid north**, in degrees.
- **Climb is the sum of the rises only.** A course that drops two hundred
  metres and climbs fifty has fifty metres of climb. Printing the net figure is
  a mistake somebody makes every season.

## Control codes

- Two or three digits, **thirty-one or above**. Below 31 a code could be read
  as the control's number on the map.
- `S1` is the start and `F1` the finish. They are controls for most purposes
  and exempt from the separation rules.
- Codes are unique within an event. Two kites with 104 on them produces an
  unwinnable protest.

## Whether a run counts

One sentence: **the punches must contain the course's controls, in order, as a
subsequence.** Everything else follows:

- extra punches are ignored, never penalised;
- the first punch that fits is the one that counts, which is what makes an
  overshoot-and-return a valid run;
- a missing finish is not a mispunch -- it is a run that cannot be timed, and
  the fix is different.

## Ordering

Every list this system returns is sorted by an explicit key whose last field
cannot tie. Two runs of the results processor over the same download produce
the same list in the same order, on any machine, in any locale. `util/order.py`
is the only place sorting is decided.

Ties in a results list **share a place and skip the next**. There is no
tie-break; orienteering does not have one and inventing one here would be
inventing a result.

## Decisions are recorded, never typed over the data

A reinstated mispunch, a disqualification, a voided control, a jury's finding:
all of them are separate records with a name and a reason against them. The
punches are never edited. Re-running the results over the same download with
the same decisions gives the same answer, and the original is still there to be
argued with.
