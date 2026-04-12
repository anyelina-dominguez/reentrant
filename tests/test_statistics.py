from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.courses.statistics import (
    TARGET_MINUTES, TOLERANCE, course_statistics, event_statistics, implied_pace,
    length_for, report_lines, target_seconds,
)
from reentrant.errors import ValidationError
from reentrant.results.classify import Result
from reentrant.util.num_stats import median_of, percentile_of


def field(times, course="Blue", class_code="M21", mispunched=0):
    rows = [Result(f"E{index}", f"Runner {index}", "DPO", class_code, course, seconds)
            for index, seconds in enumerate(times, start=1)]
    for index in range(mispunched):
        rows.append(Result(f"X{index}", f"Lost {index}", "DPO", class_code, course,
                           None, "mispunch"))
    return rows


class Targets(unittest.TestCase):
    def test_the_target_for_a_class(self):
        self.assertEqual(target_seconds(21), 35 * 60)
        self.assertEqual(target_seconds(10), 20 * 60)
        self.assertEqual(target_seconds(75), 26 * 60)
        self.assertIn(21, TARGET_MINUTES)

    def test_a_class_that_is_not_in_the_table_takes_the_nearest(self):
        self.assertEqual(target_seconds(22), target_seconds(21))
        self.assertRaises(ValidationError, target_seconds, 0)


class Statistics(unittest.TestCase):
    def test_a_course_that_came_out_right(self):
        told = course_statistics(field([2100, 2280, 2460, 2640]), target=2100)
        self.assertEqual(told.winning_seconds, 2100)
        self.assertEqual(told.against_target, 1.0)
        self.assertEqual(told.verdict, "about right")
        self.assertEqual(told.finishers, 4)
        self.assertEqual(told.completion, 1.0)

    def test_a_course_that_was_too_long(self):
        told = course_statistics(field([3000, 3300, 3600]), target=2100)
        self.assertGreater(told.against_target, 1 + TOLERANCE)
        self.assertEqual(told.verdict, "too long")

    def test_a_course_that_was_too_short(self):
        told = course_statistics(field([1200, 1400, 1600]), target=2100)
        self.assertEqual(told.verdict, "too short")

    def test_inside_the_tolerance_is_about_right(self):
        self.assertEqual(course_statistics(field([2400]), target=2100).verdict, "about right")
        self.assertEqual(course_statistics(field([1800]), target=2100).verdict, "about right")

    def test_without_a_target_there_is_no_verdict(self):
        told = course_statistics(field([2100, 2400]))
        self.assertIsNone(told.against_target)
        self.assertEqual(told.verdict, "unknown")

    def test_the_spread_of_the_field(self):
        told = course_statistics(field([2100, 2400, 4200]), target=2100)
        self.assertEqual(told.median_seconds, 2400)
        self.assertGreater(told.spread, 1.1)
        self.assertEqual(told.slowest_seconds, 4200)

    def test_mispunches_count_as_starters_but_not_finishers(self):
        told = course_statistics(field([2100, 2400], mispunched=2), target=2100)
        self.assertEqual(told.starters, 4)
        self.assertEqual(told.finishers, 2)
        self.assertEqual(told.completion, 0.5)

    def test_a_course_nobody_finished(self):
        told = course_statistics(field([], mispunched=3), target=2100)
        self.assertIsNone(told.winning_seconds)
        self.assertIsNone(told.spread)
        self.assertEqual(told.verdict, "unknown")
        self.assertEqual(told.completion, 0.0)

    def test_an_empty_course(self):
        told = course_statistics([])
        self.assertEqual(told.starters, 0)
        self.assertEqual(told.completion, 0.0)

    def test_the_whole_event_takes_its_targets_from_the_classes(self):
        rows = field([2100, 2400]) + field([1500, 1600], course="Yellow", class_code="M12")
        told = event_statistics(rows, {"M21": "Blue", "M12": "Yellow"})
        self.assertEqual([row.course for row in told], ["Blue", "Yellow"])
        self.assertEqual(told[0].target_seconds, 35 * 60)
        self.assertEqual(told[1].target_seconds, 25 * 60)

    def test_an_explicit_target_wins(self):
        rows = field([2100])
        told = event_statistics(rows, {"M21": "Blue"}, targets={"Blue": 1800})
        self.assertEqual(told[0].target_seconds, 1800)

    def test_a_course_no_class_runs_has_no_target(self):
        told = event_statistics(field([2100]), {})
        self.assertIsNone(told[0].target_seconds)

    def test_the_report_lines(self):
        lines = report_lines([course_statistics(field([2100, 2400], mispunched=1), target=2100)])
        self.assertIn("won in 35:00", lines[0])
        self.assertIn("about right", lines[0])
        self.assertIn("2 of 3 finished", lines[0])


class Planning(unittest.TestCase):
    def test_the_length_a_target_implies(self):
        self.assertEqual(length_for(2100, 420), 5000)
        self.assertEqual(length_for(2100, 600), 3500)
        self.assertRaises(ValidationError, length_for, 10, 420)
        self.assertRaises(ValidationError, length_for, 2100, 60)

    def test_the_pace_the_winner_actually_ran(self):
        self.assertEqual(implied_pace(5000, 2100), 420.0)
        self.assertIsNone(implied_pace(0, 2100))


class OrderStatistics(unittest.TestCase):
    def test_the_median(self):
        self.assertEqual(median_of([1, 2, 3]), 2)
        self.assertEqual(median_of([1, 2, 3, 4]), 3, "rounded, because seconds are whole")
        self.assertIsNone(median_of([]))

    def test_the_percentile(self):
        self.assertEqual(percentile_of([10, 20, 30, 40], 0.5), 25)
        self.assertEqual(percentile_of([10], 0.9), 10)
        self.assertEqual(percentile_of([10, 20], 0), 10)
        self.assertEqual(percentile_of([10, 20], 1), 20)
        self.assertIsNone(percentile_of([], 0.5))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
