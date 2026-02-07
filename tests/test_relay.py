from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.errors import ValidationError
from reentrant.results.handicap import (
    FACTORS, factor_for, handicap_table, handicapped_seconds, points_for,
)
from reentrant.results.relay import RelayLeg, RelayTeam, classify_relay, leg_positions


def team(name, club="DPO", legs=((1, 1800), (2, 1700), (3, 1900)), expected=3, outcomes=None):
    outcomes = outcomes or {}
    return RelayTeam(
        name=name, club=club, expected_legs=expected,
        legs=[RelayLeg(number=number, entry=f"{name}-{number}", name=f"{name} leg {number}",
                       seconds=seconds, outcome=outcomes.get(number, "ok"))
              for number, seconds in legs],
    )


class Teams(unittest.TestCase):
    def test_a_complete_team_adds_up_its_legs(self):
        one = team("Alpha")
        self.assertEqual(one.outcome, "ok")
        self.assertEqual(one.seconds, 5400)
        self.assertEqual(one.time_text, "1:30:00")
        self.assertEqual(one.missing_legs, [])

    def test_one_mispunch_takes_out_the_whole_team(self):
        one = team("Alpha", outcomes={2: "mispunch"})
        self.assertEqual(one.outcome, "mispunch")
        self.assertIsNone(one.seconds)

    def test_a_short_team_has_no_time_but_is_not_disqualified(self):
        one = team("Alpha", legs=((1, 1800), (2, 1700)))
        self.assertEqual(one.missing_legs, [3])
        self.assertEqual(one.outcome, "short")
        self.assertIsNone(one.seconds)

    def test_two_runners_on_one_leg_is_refused(self):
        self.assertRaises(ValidationError, RelayTeam, name="Alpha", club="DPO", legs=[
            RelayLeg(1, "a", "A"), RelayLeg(1, "b", "B")])

    def test_the_changeover_board(self):
        rows = team("Alpha").cumulative()
        self.assertEqual([row["elapsed"] for row in rows], ["30:00", "58:20", "1:30:00"])

    def test_the_board_stops_totalling_after_a_failure(self):
        rows = team("Alpha", outcomes={2: "mispunch"}).cumulative()
        self.assertEqual(rows[0]["elapsed"], "30:00")
        self.assertEqual(rows[1]["elapsed"], "-----")
        self.assertEqual(rows[2]["elapsed"], "-----")


class Classifying(unittest.TestCase):
    def setUp(self):
        self.teams = [
            team("Alpha", legs=((1, 1800), (2, 1700), (3, 1900))),
            team("Bravo", legs=((1, 1750), (2, 1750), (3, 1800))),
            team("Charlie", outcomes={3: "mispunch"}),
            team("Delta", legs=((1, 1800), (2, 1700))),
        ]

    def test_complete_teams_are_placed_and_the_rest_follow(self):
        rows = classify_relay(self.teams)
        self.assertEqual([row["name"] for row in rows][:2], ["Bravo", "Alpha"])
        self.assertEqual([row["place"] for row in rows][:2], [1, 2])
        self.assertTrue(all(row["place"] is None for row in rows[2:]))

    def test_the_changeover_at_one_leg(self):
        rows = leg_positions(self.teams, 2)
        # Alpha and Bravo are dead level at the second changeover, 3500 seconds
        # each, so they share first place.
        self.assertEqual([row["team"] for row in rows[:2]], ["Alpha", "Bravo"])
        self.assertEqual([row["place"] for row in rows[:2]], [1, 1])
        self.assertEqual(rows[0]["time"], "58:20")
        self.assertEqual(len(rows), 4, "everybody has reached leg two")

    def test_a_team_that_has_not_reached_the_leg_is_left_out(self):
        rows = leg_positions(self.teams, 3)
        self.assertEqual([row["team"] for row in rows if row["place"] is not None],
                         ["Bravo", "Alpha"])
        self.assertNotIn("Delta", [row["team"] for row in rows])

    def test_a_team_out_of_the_running_still_appears_at_the_changeover(self):
        rows = leg_positions(self.teams, 3)
        charlie = next(row for row in rows if row["team"] == "Charlie")
        self.assertIsNone(charlie["place"])
        self.assertEqual(charlie["time"], "-----")


class Handicaps(unittest.TestCase):
    def test_the_open_classes_are_level(self):
        self.assertEqual(factor_for(21, "M"), 1.0)
        self.assertEqual(factor_for(21, "W"), 1.0)
        self.assertEqual(handicapped_seconds(1800, 21, "M"), 1800)

    def test_the_factor_is_interpolated_between_the_class_ages(self):
        # Not stepped: a runner is not six per cent faster on one birthday.
        self.assertEqual(factor_for(55, "M"), 1.20)
        self.assertEqual(factor_for(60, "M"), 1.27)
        between = factor_for(57, "M")
        self.assertGreater(between, 1.20)
        self.assertLess(between, 1.27)

    def test_beyond_the_table_the_factor_is_held_flat(self):
        self.assertEqual(factor_for(5, "W"), FACTORS["W"][10])
        self.assertEqual(factor_for(99, "W"), FACTORS["W"][85])

    def test_the_handicap_divides_so_the_veteran_gains(self):
        # An M60 running thirty minutes beats an M21 running twenty-five.
        self.assertLess(handicapped_seconds(1800, 60, "M"), handicapped_seconds(1500, 21, "M"))

    def test_a_table_is_ordered_by_the_handicapped_time(self):
        rows = handicap_table([
            {"name": "A", "seconds": 1500, "age": 21, "sex": "M"},
            {"name": "B", "seconds": 1800, "age": 60, "sex": "M"},
            {"name": "C", "seconds": None, "age": 45, "sex": "W"},
        ])
        self.assertEqual([row["name"] for row in rows], ["B", "A", "C"])
        self.assertIsNone(rows[-1]["handicapped"])

    def test_the_arguments_are_checked(self):
        self.assertRaises(ValidationError, factor_for, 21, "X")
        self.assertRaises(ValidationError, factor_for, -1, "M")
        self.assertRaises(ValidationError, handicapped_seconds, -1, 21, "M")

    def test_league_points_fall_by_place_and_stop_at_the_floor(self):
        self.assertEqual(points_for(1), 100)
        self.assertEqual(points_for(2), 98)
        self.assertEqual(points_for(100), 20)
        self.assertRaises(ValidationError, points_for, 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
