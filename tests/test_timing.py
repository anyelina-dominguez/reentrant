from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.courses.course import Course
from reentrant.errors import ValidationError
from reentrant.timing.punch import CardRead, Punch, read_from_pairs, require_read
from reentrant.timing.validate import (
    OUTCOMES, check_order, check_run, missing_report, order_of_visit, splits,
)
from reentrant.util.times import format_time_of_day, parse_time_of_day

BLUE = Course("Blue", ["S1", "101", "102", "103", "F1"])
SCORE = Course("Score", ["101", "102", "103", "104"], "score",
               time_limit_seconds=3600, points_per_control=10, penalty_per_minute=10)


def read(pairs, start="10:00:00", finish="10:31:12", card=205431) -> CardRead:
    return read_from_pairs(card, pairs, start=start, finish=finish)


class Punches(unittest.TestCase):
    def test_a_punch_is_a_code_and_a_moment(self):
        punch = Punch("101", parse_time_of_day("10:04:11"))
        self.assertEqual(punch.code, "101")
        self.assertEqual(format_time_of_day(punch.at_seconds), "10:04:11")
        self.assertFalse(punch.is_start)
        self.assertTrue(Punch("S1", 0).is_start)
        self.assertTrue(Punch("F1", 0).is_finish)

    def test_a_punch_is_checked(self):
        self.assertRaises(ValidationError, Punch, "12", 100)
        self.assertRaises(ValidationError, Punch, "101", -1)
        self.assertRaises(ValidationError, Punch, "101", 86_400)

    def test_the_card_separates_controls_from_start_and_finish(self):
        card = read([("101", "10:04:11"), ("102", "10:09:02")])
        self.assertEqual(card.codes(), ["101", "102"])
        self.assertEqual(card.elapsed(), 1872)
        self.assertEqual(card.punch_at("102").at_seconds, parse_time_of_day("10:09:02"))
        self.assertIsNone(card.punch_at("199"))

    def test_the_first_punch_at_a_code_is_the_one_returned(self):
        card = read([("103", "10:09:02"), ("103", "10:15:01")])
        self.assertEqual(format_time_of_day(card.punch_at("103").at_seconds), "10:09:02")

    def test_punches_left_over_from_last_week_are_dropped(self):
        card = read([("104", "08:15:00"), ("101", "10:04:11")], start="10:00:00")
        self.assertEqual(card.codes(), ["101"])
        self.assertEqual(len(card.control_punches), 2, "they are still on the card")

    def test_without_a_start_nothing_can_be_dropped(self):
        card = read([("104", "08:15:00"), ("101", "10:04:11")], start=None)
        self.assertEqual(card.codes(), ["104", "101"])
        self.assertIsNone(card.elapsed())

    def test_a_read_round_trips(self):
        card = read([("101", "10:04:11"), ("102", "10:09:02")])
        self.assertEqual(CardRead.from_dict(card.to_dict()).to_dict(), card.to_dict())
        self.assertRaises(ValidationError, require_read, {})
        self.assertIs(require_read(card), card)


class Ordering(unittest.TestCase):
    def test_a_clean_run(self):
        punches = [Punch("101", 100), Punch("102", 200), Punch("103", 300)]
        matched, missing, extras = check_order(["101", "102", "103"], punches)
        self.assertEqual([punch.code for punch in matched], ["101", "102", "103"])
        self.assertEqual(missing, [])
        self.assertEqual(extras, [])

    def test_an_extra_punch_is_ignored_not_penalised(self):
        punches = [Punch("101", 100), Punch("199", 150), Punch("102", 200)]
        matched, missing, extras = check_order(["101", "102"], punches)
        self.assertEqual(missing, [])
        self.assertEqual([punch.code for punch in extras], ["199"])

    def test_an_overshoot_and_a_return_is_a_valid_run(self):
        # 101, 103, 102, 103: the runner overshot to 103, came back for 102,
        # then went on to 103 again. The second 103 is the one that counts.
        punches = [Punch("101", 100), Punch("103", 200), Punch("102", 300), Punch("103", 400)]
        matched, missing, extras = check_order(["101", "102", "103"], punches)
        self.assertEqual(missing, [])
        self.assertEqual([punch.at_seconds for punch in matched], [100, 300, 400])
        self.assertEqual([punch.at_seconds for punch in extras], [200])

    def test_out_of_order_is_a_mispunch(self):
        punches = [Punch("102", 100), Punch("101", 200)]
        matched, missing, extras = check_order(["101", "102"], punches)
        self.assertEqual(missing, ["102"])
        self.assertEqual([punch.code for punch in matched], ["101"])

    def test_a_control_never_punched(self):
        punches = [Punch("101", 100), Punch("103", 200)]
        _, missing, _ = check_order(["101", "102", "103"], punches)
        self.assertEqual(missing, ["102"])

    def test_several_missing_controls_are_all_reported(self):
        _, missing, _ = check_order(["101", "102", "103"], [Punch("102", 100)])
        self.assertEqual(missing, ["101", "103"])

    def test_an_empty_card(self):
        matched, missing, extras = check_order(["101"], [])
        self.assertEqual((matched, missing, extras), ([], ["101"], []))

    def test_a_course_with_nothing_to_find(self):
        matched, missing, extras = check_order([], [Punch("101", 100)])
        self.assertEqual(missing, [])
        self.assertEqual(len(extras), 1)


class Runs(unittest.TestCase):
    def test_a_clean_run_is_ok(self):
        check = check_run(BLUE, read([("101", "10:04:11"), ("102", "10:12:44"), ("103", "10:15:01")]))
        self.assertEqual(check.outcome, "ok")
        self.assertTrue(check.ok)
        self.assertTrue(check.counts)
        self.assertEqual(missing_report(check, BLUE), "clear")

    def test_the_overshoot_run_end_to_end(self):
        card = read([("101", "10:04:11"), ("103", "10:09:02"),
                     ("102", "10:12:44"), ("103", "10:15:01")])
        check = check_run(BLUE, card)
        self.assertEqual(check.outcome, "ok")
        self.assertEqual([punch.code for punch in check.extras], ["103"])
        self.assertEqual(format_time_of_day(check.matched[-1].at_seconds), "10:15:01")

    def test_a_mispunch_names_the_control_by_number_and_code(self):
        check = check_run(BLUE, read([("101", "10:04:11"), ("103", "10:15:01")]))
        self.assertEqual(check.outcome, "mispunch")
        self.assertEqual(check.missing, ["102"])
        self.assertFalse(check.counts)
        self.assertEqual(missing_report(check, BLUE), "missing control 2 (102)")

    def test_a_missing_finish_is_not_a_mispunch(self):
        card = read([("101", "10:04:11"), ("102", "10:12:44"), ("103", "10:15:01")], finish=None)
        check = check_run(BLUE, card)
        self.assertEqual(check.outcome, "no-finish")
        self.assertEqual(check.missing, [])
        self.assertEqual(missing_report(check, BLUE), "no finish punch")

    def test_a_missing_start_says_so_separately(self):
        card = read([("101", "10:04:11"), ("102", "10:12:44"), ("103", "10:15:01")], start=None)
        check = check_run(BLUE, card)
        self.assertEqual(check.outcome, "no-start")
        self.assertEqual(missing_report(check, BLUE), "no start time")

    def test_a_timed_start_is_supplied_from_outside_the_card(self):
        card = read([("101", "10:04:11"), ("102", "10:12:44"), ("103", "10:15:01")], start=None)
        check = check_run(BLUE, card, start_seconds=parse_time_of_day("10:00:00"))
        self.assertEqual(check.outcome, "ok")

    def test_a_mispunch_is_reported_before_a_missing_finish(self):
        card = read([("101", "10:04:11")], finish=None)
        self.assertEqual(check_run(BLUE, card).outcome, "mispunch")

    def test_the_outcomes_that_exist(self):
        self.assertEqual(OUTCOMES, ["ok", "mispunch", "no-finish", "no-start", "over-time"])


class Score(unittest.TestCase):
    def test_points_for_what_was_visited_in_any_order(self):
        card = read([("103", "10:05:00"), ("101", "10:20:00")], finish="10:50:00")
        check = check_run(SCORE, card)
        self.assertEqual(check.outcome, "ok")
        self.assertEqual(check.points, 20)
        self.assertEqual(check.penalty, 0)

    def test_a_control_punched_twice_scores_once(self):
        card = read([("101", "10:05:00"), ("101", "10:20:00")], finish="10:50:00")
        check = check_run(SCORE, card)
        self.assertEqual(check.points, 10)
        self.assertEqual([punch.code for punch in check.extras], ["101"])

    def test_a_control_not_on_the_course_scores_nothing(self):
        card = read([("101", "10:05:00"), ("199", "10:20:00")], finish="10:50:00")
        self.assertEqual(check_run(SCORE, card).points, 10)

    def test_coming_back_late_costs_a_whole_minute_a_minute(self):
        # Ten seconds over is a whole minute of penalty.
        card = read([("101", "10:05:00"), ("102", "10:20:00")], finish="11:00:10")
        check = check_run(SCORE, card)
        self.assertEqual(check.outcome, "over-time")
        self.assertEqual(check.penalty, 10)
        self.assertEqual(check.points, 20 - 10)

    def test_exactly_on_the_limit_is_not_late(self):
        card = read([("101", "10:05:00")], finish="11:00:00")
        check = check_run(SCORE, card)
        self.assertEqual(check.outcome, "ok")
        self.assertEqual(check.penalty, 0)

    def test_a_score_run_can_go_negative(self):
        card = read([("101", "10:05:00")], finish="11:10:00")
        check = check_run(SCORE, card)
        self.assertEqual(check.penalty, 100)
        self.assertEqual(check.points, 10 - 100)


class Splits(unittest.TestCase):
    def test_the_legs_add_up_to_the_run(self):
        card = read([("101", "10:04:11"), ("102", "10:12:44"), ("103", "10:15:01")])
        check = check_run(BLUE, card)
        rows = splits(check.matched, card.start_seconds, card.finish_seconds)
        self.assertEqual([row["code"] for row in rows], ["101", "102", "103", "F1"])
        self.assertEqual(sum(row["leg_seconds"] for row in rows), card.elapsed())
        self.assertEqual(rows[-1]["elapsed_seconds"], card.elapsed())

    def test_without_a_finish_the_last_leg_is_absent(self):
        card = read([("101", "10:04:11")], finish=None)
        rows = splits([Punch("101", parse_time_of_day("10:04:11"))], card.start_seconds)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["leg_seconds"], 251)

    def test_the_order_of_visit_is_by_time(self):
        card = read([("103", "10:15:01"), ("101", "10:04:11"), ("102", "10:12:44")])
        self.assertEqual(order_of_visit(card), ["101", "102", "103"])
        self.assertRaises(ValidationError, splits, [], -1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class AdminBoxes(unittest.TestCase):
    """Clear and check: on the card, never on a course."""

    def test_they_are_not_control_punches(self):
        card = read([("C1", "09:55:00"), ("K1", "09:56:00"),
                     ("101", "10:04:11"), ("102", "10:12:44")])
        self.assertEqual(card.codes(), ["101", "102"])
        self.assertEqual(len(card.punches), 4)

    def test_the_card_says_whether_it_was_cleared_and_checked(self):
        card = read([("C1", "09:55:00"), ("K1", "09:56:00"), ("101", "10:04:11")])
        self.assertTrue(card.cleared)
        self.assertTrue(card.checked)
        self.assertFalse(read([("101", "10:04:11")]).cleared)

    def test_a_run_is_unaffected_by_them(self):
        card = read([("C1", "09:55:00"), ("101", "10:04:11"),
                     ("102", "10:12:44"), ("103", "10:15:01")])
        self.assertEqual(check_run(BLUE, card).outcome, "ok")

    def test_the_codes_are_accepted_where_a_control_code_is_wanted(self):
        self.assertEqual(Punch("C1", 100).code, "C1")
        self.assertTrue(Punch("K1", 100).is_admin)
        self.assertFalse(Punch("101", 100).is_admin)
