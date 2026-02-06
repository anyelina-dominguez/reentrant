from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.entries.competitor import Competitor, Entry
from reentrant.errors import ValidationError
from reentrant.starts.draw import (
    DEFAULT_CLUB_GAP, DEFAULT_FAMILY_GAP, apply_draw, draw_course, start_list,
)
from reentrant.util.times import parse_time_of_day

TEN = parse_time_of_day("10:00:00")


def field(*people: tuple[str, str, str], course: str = "Blue") -> list[Entry]:
    return [
        Entry(f"ENT-{index + 1:04d}", Competitor(surname, forename, club),
              course, "M21", 200_000 + index)
        for index, (surname, forename, club) in enumerate(people)
    ]


MIXED = (
    ("Okonkwo", "Ada", "DPO"), ("Okonkwo", "Ben", "DPO"), ("Bergstrom", "Nils", "SYO"),
    ("Bo", "Sam", "DPO"), ("Cai", "Jo", "SYO"), ("Dee", "Kim", "HALO"), ("Eze", "Lin", "HALO"),
)


class Drawing(unittest.TestCase):
    def test_everybody_gets_a_slot_at_the_interval(self):
        drawn = draw_course("Blue", field(*MIXED), first_seconds=TEN, interval_seconds=120, seed="ev1")
        self.assertEqual(len(drawn.slots), 7)
        self.assertEqual(drawn.first_seconds, TEN)
        self.assertEqual(drawn.last_seconds, TEN + 6 * 120)
        gaps = {b.seconds - a.seconds for a, b in zip(drawn.slots, drawn.slots[1:])}
        self.assertEqual(gaps, {120})

    def test_a_mixed_field_separates_cleanly(self):
        drawn = draw_course("Blue", field(*MIXED), first_seconds=TEN, interval_seconds=120, seed="ev1")
        self.assertEqual(drawn.unresolved, [])
        clubs = [slot.club for slot in drawn.slots]
        for index, club in enumerate(clubs):
            self.assertNotIn(club, clubs[index + 1:index + 1 + DEFAULT_CLUB_GAP])

    def test_the_same_surname_is_kept_further_apart_than_the_same_club(self):
        drawn = draw_course("Blue", field(*MIXED), first_seconds=TEN, seed="ev1")
        names = [slot.name.split(",")[0] for slot in drawn.slots]
        first = names.index("Okonkwo")
        second = names.index("Okonkwo", first + 1)
        self.assertGreater(second - first, DEFAULT_FAMILY_GAP)

    def test_the_draw_is_stable_for_the_same_seed(self):
        entries = field(*MIXED)
        first = draw_course("Blue", entries, first_seconds=TEN, seed="ev1")
        second = draw_course("Blue", entries, first_seconds=TEN, seed="ev1")
        self.assertEqual([slot.entry for slot in first.slots], [slot.entry for slot in second.slots])

    def test_a_different_course_draws_differently(self):
        entries = field(*MIXED)
        blue = draw_course("Blue", entries, first_seconds=TEN, seed="ev1")
        green = draw_course("Green", entries, first_seconds=TEN, seed="ev1")
        self.assertNotEqual([slot.entry for slot in blue.slots], [slot.entry for slot in green.slots])

    def test_an_impossible_separation_is_reported_not_shuffled_forever(self):
        # Five runners from one club in eight slots cannot be three apart.
        crowded = field(*[(f"N{index}", f"F{index}", "DPO" if index < 5 else "SYO")
                          for index in range(8)])
        drawn = draw_course("Blue", crowded, first_seconds=TEN, seed="ev1")
        self.assertEqual(len(drawn.slots), 8)
        self.assertGreater(len(drawn.unresolved), 0)
        self.assertEqual(drawn.unresolved[0]["reason"], "same club")

    def test_relaxing_the_gaps_removes_the_problem(self):
        crowded = field(*[(f"N{index}", f"F{index}", "DPO" if index < 5 else "SYO")
                          for index in range(8)])
        drawn = draw_course("Blue", crowded, first_seconds=TEN, seed="ev1",
                            club_gap=0, family_gap=0)
        self.assertEqual(drawn.unresolved, [])

    def test_runners_with_no_club_are_not_treated_as_clubmates(self):
        unattached = field(("A", "One", ""), ("B", "Two", ""), ("C", "Three", ""))
        drawn = draw_course("Blue", unattached, first_seconds=TEN, seed="ev1")
        self.assertEqual(drawn.unresolved, [])

    def test_an_empty_course(self):
        drawn = draw_course("Blue", [], first_seconds=TEN, seed="ev1")
        self.assertEqual(drawn.slots, [])
        self.assertIsNone(drawn.first_seconds)
        self.assertIsNone(drawn.of("ENT-0001"))

    def test_the_arguments_are_checked(self):
        entries = field(*MIXED)
        self.assertRaises(ValidationError, draw_course, "Blue", entries, first_seconds=-1)
        self.assertRaises(ValidationError, draw_course, "Blue", entries, first_seconds=TEN,
                          interval_seconds=0)
        self.assertRaises(ValidationError, draw_course, "", entries, first_seconds=TEN)


class Applying(unittest.TestCase):
    def test_the_times_go_onto_the_entries(self):
        entries = field(*MIXED)
        drawn = draw_course("Blue", entries, first_seconds=TEN, interval_seconds=120, seed="ev1")
        updated = apply_draw(entries, drawn)
        for entry in updated:
            self.assertEqual(entry.start_seconds, drawn.of(entry.reference).seconds)

    def test_an_entry_not_in_the_draw_is_left_alone(self):
        entries = field(*MIXED)
        drawn = draw_course("Blue", entries[:3], first_seconds=TEN, seed="ev1")
        updated = apply_draw(entries, drawn)
        self.assertIsNone(updated[-1].start_seconds)

    def test_the_whole_board_is_in_time_order(self):
        blue = draw_course("Blue", field(*MIXED[:3]), first_seconds=TEN, interval_seconds=120, seed="ev1")
        green = draw_course("Green", field(*MIXED[3:], course="Green"),
                            first_seconds=TEN + 60, interval_seconds=120, seed="ev1")
        rows = start_list([blue, green])
        self.assertEqual(len(rows), 7)
        self.assertEqual([row["seconds"] for row in rows], sorted(row["seconds"] for row in rows))
        self.assertEqual(rows[0]["course"], "Blue")
        self.assertEqual(rows[1]["course"], "Green")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
