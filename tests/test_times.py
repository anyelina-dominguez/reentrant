from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.errors import ValidationError
from reentrant.util.times import (
    NO_TIME, behind, difference, format_behind, format_clock, format_time_of_day,
    parse_clock, parse_time_of_day, per_kilometre, total,
)


class Parsing(unittest.TestCase):
    def test_both_forms_of_the_same_time(self):
        self.assertEqual(parse_clock("63:12"), 3792)
        self.assertEqual(parse_clock("1:03:12"), 3792)
        self.assertEqual(parse_clock("  0:59  "), 59)

    def test_minutes_may_run_past_sixty_only_without_an_hours_field(self):
        self.assertEqual(parse_clock("125:00"), 7500)
        self.assertRaises(ValidationError, parse_clock, "1:73:12")

    def test_the_things_that_are_not_times(self):
        for bad in ["nonsense", "12:60", "1:2:3:4", "12", "", "-1:00"]:
            with self.subTest(bad=bad):
                self.assertRaises(ValidationError, parse_clock, bad)
        self.assertRaises(ValidationError, parse_clock, 90)


class Formatting(unittest.TestCase):
    def test_under_the_hour_and_over_it(self):
        self.assertEqual(format_clock(59), "0:59")
        self.assertEqual(format_clock(600), "10:00")
        self.assertEqual(format_clock(3792), "1:03:12")
        self.assertEqual(format_clock(3792, always_hours=True), "1:03:12")
        self.assertEqual(format_clock(600, always_hours=True), "0:10:00")

    def test_no_time_at_all(self):
        self.assertEqual(format_clock(None), NO_TIME)
        self.assertEqual(format_behind(None), NO_TIME)

    def test_a_negative_time_keeps_its_sign(self):
        self.assertEqual(format_clock(-90), "-1:30")

    def test_the_round_trip(self):
        for seconds in [0, 59, 60, 599, 3599, 3600, 7325]:
            with self.subTest(seconds=seconds):
                self.assertEqual(parse_clock(format_clock(seconds)), seconds)


class TimeOfDay(unittest.TestCase):
    def test_a_start_time_is_seconds_since_midnight(self):
        self.assertEqual(parse_time_of_day("10:30:00"), 37800)
        self.assertEqual(format_time_of_day(37800), "10:30:00")
        self.assertEqual(format_time_of_day(0), "00:00:00")

    def test_past_midnight_is_refused_on_the_way_in_and_wrapped_on_the_way_out(self):
        self.assertRaises(ValidationError, parse_time_of_day, "24:00:00")
        self.assertEqual(format_time_of_day(24 * 3600 + 60), "00:01:00")

    def test_an_elapsed_time_survives_midnight(self):
        start = parse_time_of_day("23:50:00")
        finish = parse_time_of_day("00:12:00")
        self.assertEqual(difference(start, finish), 22 * 60)
        self.assertEqual(difference(parse_time_of_day("10:00:00"), parse_time_of_day("10:45:30")), 2730)
        self.assertEqual(difference(100, 100), 0)


class Arithmetic(unittest.TestCase):
    def test_splits_sum_exactly(self):
        splits = [312, 245, 189, 401]
        self.assertEqual(total(splits), 1147)
        self.assertEqual(sum(splits), total(splits), "no float anywhere in the addition")

    def test_one_missing_split_makes_the_total_missing(self):
        self.assertIsNone(total([312, None, 189]))
        self.assertEqual(total([]), 0)

    def test_behind_the_leader(self):
        self.assertEqual(behind(1800, 1883), 83)
        self.assertEqual(behind(1800, 1800), 0)
        self.assertIsNone(behind(None, 1883))
        self.assertIsNone(behind(1800, None))
        self.assertEqual(format_behind(83), "+1:23")
        self.assertEqual(format_behind(0), "0:00")
        self.assertEqual(format_behind(-5), "-0:05")

    def test_pace_per_kilometre(self):
        self.assertEqual(per_kilometre(3600, 7200), 500)
        self.assertEqual(format_clock(per_kilometre(3600, 7200)), "8:20")
        self.assertIsNone(per_kilometre(None, 7200))
        self.assertIsNone(per_kilometre(3600, 0))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
