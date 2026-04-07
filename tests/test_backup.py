from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.courses.course import Course
from reentrant.errors import ConflictError, ValidationError
from reentrant.geo.grid import parse as grid
from reentrant.geo.route import Fix, Route, compare, extra_distance
from reentrant.timing.backup import (
    BackupLog, BackupMark, rescue, rescued_controls, would_rescue,
)
from reentrant.timing.punch import read_from_pairs

BLUE = Course("Blue", ["S1", "101", "102", "103", "F1"])


def read(pairs, start="10:00:00", finish="10:21:12"):
    return read_from_pairs(205431, pairs, start=start, finish=finish)


class Marks(unittest.TestCase):
    def test_a_mark_is_a_box_on_a_map(self):
        mark = BackupMark("ENT-0001", "102", 2, "organiser")
        self.assertEqual(mark.box, 2)
        self.assertEqual(mark.to_dict()["read_by"], "organiser")

    def test_a_box_number_that_is_not_on_the_map(self):
        self.assertRaises(ValidationError, BackupMark, "ENT-0001", "102", 0)
        self.assertRaises(ValidationError, BackupMark, "ENT-0001", "102", 99)
        self.assertRaises(ValidationError, BackupMark, "ENT-0001", "102", True)

    def test_one_box_cannot_hold_two_controls(self):
        log = BackupLog()
        log.add(BackupMark("ENT-0001", "102", 2))
        self.assertRaises(ConflictError, log.add, BackupMark("ENT-0001", "103", 2))
        log.add(BackupMark("ENT-0002", "103", 2), )
        self.assertEqual(len(log), 2)

    def test_the_marks_for_one_runner_come_back_in_box_order(self):
        log = BackupLog()
        log.add(BackupMark("ENT-0001", "103", 3))
        log.add(BackupMark("ENT-0001", "101", 1))
        self.assertEqual(log.codes_for("ENT-0001"), ["101", "103"])
        self.assertEqual(log.codes_for("ENT-0009"), [])

    def test_a_log_round_trips(self):
        log = BackupLog()
        log.add(BackupMark("ENT-0001", "102", 2, "organiser"))
        self.assertEqual(BackupLog.from_list(log.to_list()).to_list(), log.to_list())


class Rescue(unittest.TestCase):
    def test_without_backup_the_run_is_a_mispunch(self):
        check = rescue(BLUE, read([("101", "10:04:11"), ("103", "10:15:01")]), [])
        self.assertEqual(check.outcome, "mispunch")
        self.assertEqual(check.missing, ["102"])

    def test_a_pin_mark_rescues_the_run(self):
        card = read([("101", "10:04:11"), ("103", "10:15:01")])
        check = rescue(BLUE, card, ["102"])
        self.assertEqual(check.outcome, "ok")
        self.assertEqual(rescued_controls(check), ["102"])

    def test_a_rescued_control_has_no_time(self):
        card = read([("101", "10:04:11"), ("103", "10:15:01")])
        check = rescue(BLUE, card, ["102"])
        self.assertEqual([punch.code for punch in check.matched], ["101", "103"],
                         "the rescued control contributes no punch and so no split")

    def test_a_mark_for_the_wrong_control_does_not_help(self):
        card = read([("101", "10:04:11"), ("103", "10:15:01")])
        self.assertEqual(rescue(BLUE, card, ["199"]).outcome, "mispunch")
        self.assertFalse(would_rescue(BLUE, card, ["199"]))
        self.assertTrue(would_rescue(BLUE, card, ["102"]))

    def test_a_run_that_was_already_fine_is_not_rescued(self):
        card = read([("101", "10:04:11"), ("102", "10:09:00"), ("103", "10:15:01")])
        self.assertFalse(would_rescue(BLUE, card, ["102"]))
        self.assertEqual(rescue(BLUE, card, ["102"]).outcome, "ok")

    def test_two_missing_controls_need_two_marks(self):
        card = read([("101", "10:04:11")])
        self.assertEqual(rescue(BLUE, card, ["102"]).missing, ["103"])
        self.assertEqual(rescue(BLUE, card, ["102", "103"]).outcome, "ok")

    def test_backup_cannot_supply_a_finish(self):
        card = read([("101", "10:04:11"), ("103", "10:15:01")], finish=None)
        self.assertEqual(rescue(BLUE, card, ["102"]).outcome, "no-finish")

    def test_a_score_course_has_no_backup_rescue(self):
        scored = Course("Score", ["101", "102"], "score", time_limit_seconds=3600)
        self.assertRaises(ValidationError, rescue, scored, read([]), ["101"])


class Routes(unittest.TestCase):
    def trace(self):
        # Three hundred east, then four hundred north: 700 m for a 500 m leg.
        return Route("ENT-0001", [
            Fix(grid("SK 12000 67000"), 0),
            Fix(grid("SK 12300 67000"), 120),
            Fix(grid("SK 12300 67400"), 300),
        ])

    def test_how_far_they_actually_ran(self):
        route = self.trace()
        self.assertAlmostEqual(route.metres, 700.0)
        self.assertAlmostEqual(route.straight_metres(), 500.0)
        self.assertEqual(route.seconds, 300)

    def test_efficiency_is_the_straight_line_over_the_run(self):
        self.assertAlmostEqual(self.trace().efficiency(), 0.7143, places=4)
        self.assertEqual(extra_distance(self.trace(), 500.0), 0.4)

    def test_a_trace_that_went_nowhere(self):
        route = Route("ENT-0001", [Fix(grid("SK 12000 67000"), 0)])
        self.assertEqual(route.metres, 0.0)
        self.assertIsNone(route.efficiency())
        self.assertIsNone(route.pace)
        self.assertEqual(route.seconds, 0)

    def test_where_they_were_at_a_moment(self):
        route = self.trace()
        self.assertEqual(route.at(0), grid("SK 12000 67000"))
        self.assertEqual(route.at(150), grid("SK 12300 67000"))
        self.assertIsNone(route.at(-1))

    def test_cutting_a_trace_into_legs(self):
        legs = self.trace().legs([120, 300])
        self.assertEqual(len(legs), 2)
        self.assertAlmostEqual(legs[0].metres, 300.0)
        self.assertAlmostEqual(legs[1].metres, 400.0)

    def test_a_span_that_runs_backwards(self):
        self.assertRaises(ValidationError, self.trace().between, 300, 0)

    def test_fixes_are_sorted_by_time_however_they_arrive(self):
        route = Route("ENT-0001", [
            Fix(grid("SK 12300 67000"), 120),
            Fix(grid("SK 12000 67000"), 0),
        ])
        self.assertEqual(route.fixes[0].at_seconds, 0)
        self.assertRaises(ValidationError, Fix, "SK 12000 67000", 0)

    def test_two_traces_side_by_side(self):
        straight = Route("ENT-0002", [
            Fix(grid("SK 12000 67000"), 0), Fix(grid("SK 12300 67400"), 280),
        ])
        rows = compare([self.trace(), straight])
        self.assertEqual([row["entry"] for row in rows], ["ENT-0002", "ENT-0001"])
        self.assertEqual(rows[0]["efficiency"], 1.0)
        self.assertEqual(rows[1]["metres"], 700)

    def test_the_summary(self):
        told = self.trace().to_dict()
        self.assertEqual(told["metres"], 700)
        self.assertEqual(told["straight"], 500)
        self.assertEqual(told["time"], "5:00")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
