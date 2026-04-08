from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.entries.competitor import Competitor, Entry
from reentrant.errors import ValidationError
from reentrant.results.analysis import (
    LOSS_MARGIN, MINIMUM_LEG_SECONDS, analyse_legs, form_of, leg_table,
    leg_times, losses_for, superman_seconds, total_lost,
)
from reentrant.results.classify import (
    Result, by_class, by_course, classify, counts, result_for, winner,
)
from reentrant.timing.validate import RunCheck


def result(entry, name, seconds=None, outcome="ok", class_code="W45", course="Blue", club="DPO"):
    return Result(entry=entry, name=name, club=club, class_code=class_code,
                  course=course, seconds=seconds, outcome=outcome)


class Classifying(unittest.TestCase):
    def setUp(self):
        self.rows = [
            result("E1", "Okonkwo, Ada", 1872),
            result("E2", "Bergstrom, Nils", 1755),
            result("E3", "Bo, Sam", 1872),
            result("E4", "Cai, Jo", None, "mispunch"),
            result("E5", "Dee, Kim", None, "dns"),
        ]

    def test_the_finishers_are_placed_in_time_order(self):
        placed = [row for row in classify(self.rows) if row.placed]
        self.assertEqual([row.name for row in placed],
                         ["Bergstrom, Nils", "Okonkwo, Ada", "Bo, Sam"])

    def test_ties_share_a_place_with_no_tie_break(self):
        placed = [row for row in classify(self.rows) if row.placed]
        self.assertEqual([row.place for row in placed], [1, 2, 2])

    def test_everybody_is_timed_against_the_winner(self):
        placed = [row for row in classify(self.rows) if row.placed]
        self.assertEqual(placed[0].behind_seconds, 0)
        self.assertEqual(placed[0].behind_text, "0:00")
        self.assertEqual(placed[1].behind_seconds, 117)
        self.assertEqual(placed[1].behind_text, "+1:57")

    def test_the_unplaced_are_listed_after_in_a_fixed_order(self):
        unplaced = [row for row in classify(self.rows) if not row.placed]
        self.assertEqual([row.outcome for row in unplaced], ["mispunch", "dns"])
        self.assertTrue(all(row.place is None for row in unplaced))
        self.assertEqual(unplaced[0].time_text, "-----")

    def test_classifying_does_not_disturb_what_it_was_given(self):
        classify(self.rows)
        self.assertTrue(all(row.place is None for row in self.rows))

    def test_a_class_where_nobody_finished(self):
        rows = [result("E1", "Cai, Jo", None, "mispunch")]
        self.assertIsNone(winner(rows))
        self.assertEqual(len(classify(rows)), 1)

    def test_the_winner_and_the_tally(self):
        self.assertEqual(winner(self.rows).name, "Bergstrom, Nils")
        self.assertEqual(counts(self.rows), {"dns": 1, "mispunch": 1, "ok": 3})

    def test_a_result_is_checked(self):
        self.assertRaises(ValidationError, result, "E1", "", 100)
        self.assertRaises(ValidationError, Result, entry="E1", name="A", club="", class_code="W45",
                          course="Blue", outcome="exploded")


class Blocks(unittest.TestCase):
    def setUp(self):
        self.rows = [
            result("E1", "Okonkwo, Ada", 1872, class_code="W45", course="Blue"),
            result("E2", "Bergstrom, Nils", 1755, class_code="M21", course="Blue"),
            result("E3", "Bo, Sam", 1600, class_code="W45", course="Green"),
        ]

    def test_one_block_per_class_each_placed_on_its_own(self):
        blocks = by_class(self.rows)
        self.assertEqual(sorted(blocks), ["M21", "W45"])
        self.assertEqual([row.place for row in blocks["W45"]], [1, 2])
        self.assertEqual(blocks["W45"][0].name, "Bo, Sam")

    def test_and_one_block_per_course(self):
        blocks = by_course(self.rows)
        self.assertEqual(sorted(blocks), ["Blue", "Green"])
        self.assertEqual([row.name for row in blocks["Blue"]],
                         ["Bergstrom, Nils", "Okonkwo, Ada"])
        self.assertEqual(blocks["Green"][0].place, 1)

    def test_the_same_run_can_be_placed_differently_in_each(self):
        # Ada is second on Blue but second in W45 behind somebody on Green.
        self.assertEqual(by_course(self.rows)["Blue"][1].place, 2)
        self.assertEqual(by_class(self.rows)["W45"][1].place, 2)


class FromEntries(unittest.TestCase):
    def entry(self, state="entered"):
        return Entry("ENT-0001", Competitor("Okonkwo", "Ada", "DPO", 1981, "W"),
                     "Blue", "W45", 205431, state=state)

    def test_a_clean_run_becomes_a_placed_result(self):
        row = result_for(self.entry(), RunCheck("ok"), 1872)
        self.assertEqual(row.outcome, "ok")
        self.assertEqual(row.seconds, 1872)
        self.assertEqual(row.name, "Okonkwo, Ada")

    def test_a_mispunch_keeps_its_time_but_is_not_placed(self):
        # The time is kept so that a reinstatement has something to reinstate.
        row = result_for(self.entry(), RunCheck("mispunch", missing=["102"]), 1872)
        self.assertEqual(row.outcome, "mispunch")
        self.assertEqual(row.seconds, 1872)
        self.assertFalse(row.placed)

    def test_the_entry_state_wins_over_the_card(self):
        row = result_for(self.entry("dnf"), RunCheck("ok"), 1872)
        self.assertEqual(row.outcome, "dnf")
        self.assertFalse(row.placed)

    def test_a_card_never_read_is_a_non_starter(self):
        self.assertEqual(result_for(self.entry(), None, None).outcome, "dns")


SPLITS = {
    "A": [{"number": 1, "code": "101", "leg_seconds": 200},
          {"number": 2, "code": "102", "leg_seconds": 300},
          {"number": 3, "code": "103", "leg_seconds": 150}],
    "B": [{"number": 1, "code": "101", "leg_seconds": 220},
          {"number": 2, "code": "102", "leg_seconds": 900},
          {"number": 3, "code": "103", "leg_seconds": 160}],
    "C": [{"number": 1, "code": "101", "leg_seconds": 240},
          {"number": 2, "code": "102", "leg_seconds": 330},
          {"number": 3, "code": "103", "leg_seconds": 200}],
}


class Analysis(unittest.TestCase):
    def setUp(self):
        self.legs = analyse_legs(SPLITS)

    def test_the_legs_come_back_in_course_order(self):
        self.assertEqual([leg.number for leg in self.legs], [1, 2, 3])
        self.assertEqual([leg.code for leg in self.legs], ["101", "102", "103"])

    def test_who_was_fastest_on_each_leg(self):
        self.assertEqual([leg.fastest_entry for leg in self.legs], ["A", "A", "A"])
        self.assertEqual([leg.fastest for leg in self.legs], [200, 300, 150])

    def test_leg_places(self):
        self.assertEqual(self.legs[0].place_of("A"), 1)
        self.assertEqual(self.legs[0].place_of("C"), 3)
        self.assertIsNone(self.legs[0].place_of("Z"))

    def test_the_superman_time_is_the_fastest_legs_added_up(self):
        self.assertEqual(superman_seconds(self.legs), 650)
        # A happened to win every leg here, so superman equals A's own time.
        self.assertEqual(superman_seconds(self.legs), sum(row["leg_seconds"] for row in SPLITS["A"]))
        self.assertIsNone(superman_seconds([]))

    def test_superman_beats_everybody_once_the_legs_are_shared_out(self):
        shared = {
            "A": [{"number": 1, "code": "101", "leg_seconds": 200},
                  {"number": 2, "code": "102", "leg_seconds": 400}],
            "B": [{"number": 1, "code": "101", "leg_seconds": 300},
                  {"number": 2, "code": "102", "leg_seconds": 300}],
        }
        legs = analyse_legs(shared)
        self.assertEqual(superman_seconds(legs), 500)
        self.assertLess(superman_seconds(legs), 600)

    def test_form_is_the_median_ratio_so_one_disaster_does_not_set_it(self):
        # B's ratios are 1.1, 3.0 and 1.067; the median ignores the disaster.
        self.assertAlmostEqual(form_of("B", self.legs), 1.1, places=3)
        self.assertEqual(form_of("A", self.legs), 1.0)
        self.assertIsNone(form_of("Z", self.legs))

    def test_the_leg_where_the_time_went(self):
        losses = losses_for("B", self.legs)
        self.assertEqual([row["number"] for row in losses], [2])
        self.assertEqual(losses[0]["lost_seconds"], 570)
        self.assertEqual(losses[0]["expected_seconds"], 330)
        self.assertEqual(total_lost("B", self.legs), 570)

    def test_a_runner_who_was_steadily_slower_lost_nothing_anywhere(self):
        self.assertEqual(losses_for("C", self.legs), [])
        self.assertEqual(total_lost("C", self.legs), 0)
        self.assertEqual(losses_for("A", self.legs), [])

    def test_a_looser_margin_finds_less(self):
        self.assertEqual(losses_for("B", self.legs, margin=5.0), [])
        self.assertRaises(ValidationError, losses_for, "B", self.legs, margin=0.5)
        self.assertEqual(LOSS_MARGIN, 1.25)

    def test_very_short_legs_are_not_analysed(self):
        splits = {
            "A": [{"number": 1, "code": "101", "leg_seconds": 10}],
            "B": [{"number": 1, "code": "101", "leg_seconds": 25}],
        }
        legs = analyse_legs(splits)
        self.assertIsNone(form_of("B", legs))
        self.assertEqual(losses_for("B", legs), [])
        self.assertEqual(MINIMUM_LEG_SECONDS, 30)

    def test_the_printed_table_for_one_runner(self):
        rows = leg_table(self.legs, "B")
        self.assertEqual([row["time"] for row in rows], ["3:40", "15:00", "2:40"])
        self.assertEqual([row["place"] for row in rows], [2, 3, 2])
        self.assertEqual(rows[1]["behind"], "10:00")

    def test_a_runner_missing_from_a_leg(self):
        rows = leg_table(self.legs, "Z")
        self.assertEqual([row["time"] for row in rows], ["-----"] * 3)
        self.assertEqual(len(leg_times(SPLITS)), 9)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
