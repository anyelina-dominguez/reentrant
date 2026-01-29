from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.courses.control import Control, ControlSet
from reentrant.courses.course import COURSE_KINDS, Course, CourseSet
from reentrant.courses.descriptions import parse_description
from reentrant.errors import NotFoundError, RuleError, ValidationError
from reentrant.geo.grid import parse as grid

PLACES = {
    "S1": (12000, 67000, 200.0),
    "101": (12300, 67200, 210.0),
    "102": (12800, 67600, 240.0),
    "103": (12500, 68100, 225.0),
    "104": (13400, 68000, 260.0),
    "F1": (12100, 67100, 205.0),
}


def controls(*, heights: bool = True) -> ControlSet:
    found = ControlSet()
    for code, (east, north, height) in PLACES.items():
        found.add(Control(
            code=code,
            position=grid(f"SK {east} {north}"),
            description=None if code in ("S1", "F1") else parse_description("knoll"),
            height=height if heights else None,
        ))
    return found


class Shape(unittest.TestCase):
    def setUp(self):
        self.controls = controls()
        self.course = Course("Blue", ["S1", "101", "102", "103", "F1"])

    def test_the_start_and_finish_are_not_controls(self):
        self.assertEqual(self.course.control_codes, ["101", "102", "103"])
        self.assertEqual(self.course.size, 3)

    def test_controls_are_numbered_in_order(self):
        self.assertEqual(self.course.numbering(), {"101": 1, "102": 2, "103": 3})

    def test_the_legs_run_start_to_finish(self):
        legs = self.course.legs(self.controls)
        self.assertEqual([leg.label for leg in legs], ["S1-101", "101-102", "102-103", "103-F1"])
        self.assertEqual([leg.number for leg in legs], [1, 2, 3, 4])
        self.assertAlmostEqual(legs[1].metres, 640.3, places=1)

    def test_the_length_is_the_straight_legs_added_up(self):
        self.assertEqual(self.course.length_metres(self.controls), 2660)

    def test_climb_counts_the_rises_only(self):
        # 200 -> 210 -> 240 -> 225 -> 205 is forty metres of climb, not five.
        self.assertEqual(self.course.climb_metres(self.controls), 40)

    def test_climb_is_unknown_rather_than_nought_when_a_height_is_missing(self):
        self.assertIsNone(self.course.climb_metres(controls(heights=False)))

    def test_the_description_sheet(self):
        lines = self.course.describe(self.controls)
        self.assertEqual(lines[0], "  S  start")
        self.assertEqual(lines[-1], "  F  finish")
        self.assertEqual(lines[1], "  1  101  knoll")


class Kinds(unittest.TestCase):
    def test_a_score_course_needs_a_time_limit(self):
        self.assertRaises(ValidationError, Course, "Score", ["101", "102"], "score")
        scored = Course("Score", ["101", "102"], "score", time_limit_seconds=3600,
                        points_per_control=10, penalty_per_minute=10)
        self.assertTrue(scored.is_scored)
        self.assertEqual(scored.numbering(), {}, "a score course has no order to number")
        self.assertEqual(scored.legs(controls()), [])
        self.assertEqual(scored.length_metres(controls()), 0)

    def test_only_a_score_course_carries_points(self):
        self.assertRaises(ValidationError, Course, "Blue", ["S1", "101", "F1"],
                          points_per_control=10)

    def test_the_kinds_that_exist(self):
        self.assertEqual(COURSE_KINDS, ["point-to-point", "score", "line"])
        self.assertRaises(ValidationError, Course, "Blue", ["S1", "F1"], "relay")
        self.assertEqual(Course("String", ["S1", "101", "F1"], "line").kind, "line")


class Checking(unittest.TestCase):
    def test_a_course_using_a_control_that_is_not_out(self):
        course = Course("Blue", ["S1", "101", "199", "F1"])
        self.assertEqual(course.missing_controls(controls()), ["199"])
        with self.assertRaises(RuleError) as caught:
            course.check(controls())
        self.assertEqual(caught.exception.details["missing"], ["199"])

    def test_a_course_may_not_visit_a_control_twice(self):
        course = Course("Blue", ["S1", "101", "102", "101", "F1"])
        self.assertEqual(course.repeated_controls(), ["101"])
        self.assertRaises(RuleError, course.check, controls())

    def test_a_course_starts_at_the_start_and_ends_at_the_finish(self):
        self.assertRaises(RuleError, Course("Blue", ["101", "102", "F1"]).check, controls())
        self.assertRaises(RuleError, Course("Blue", ["S1", "101", "102"]).check, controls())
        Course("Blue", ["S1", "101", "F1"]).check(controls())

    def test_a_score_course_is_not_held_to_the_start_and_finish_rule(self):
        scored = Course("Score", ["101", "102"], "score", time_limit_seconds=3600)
        scored.check(controls())

    def test_a_course_needs_at_least_one_control(self):
        self.assertRaises(ValidationError, Course, "Blue", [])
        self.assertRaises(ValidationError, Course, "", ["S1", "F1"])


class Sets(unittest.TestCase):
    def setUp(self):
        self.courses = CourseSet()
        self.courses.add(Course("Blue", ["S1", "101", "102", "F1"]))
        self.courses.add(Course("Green", ["S1", "101", "103", "F1"]))

    def test_courses_are_named_uniquely_and_sorted(self):
        self.assertEqual(self.courses.names(), ["Blue", "Green"])
        self.assertRaises(ValidationError, self.courses.add, Course("Blue", ["S1", "F1"]))
        self.assertEqual(len(self.courses), 2)

    def test_lookup(self):
        self.assertEqual(self.courses.require("Blue").size, 2)
        self.assertIsNone(self.courses.get("Red"))
        self.assertRaises(NotFoundError, self.courses.require, "Red")

    def test_which_courses_use_a_control(self):
        # The question a planner asks before moving a kite.
        self.assertEqual(self.courses.using("101"), ["Blue", "Green"])
        self.assertEqual(self.courses.using("102"), ["Blue"])
        self.assertEqual(self.courses.using("199"), [])

    def test_a_set_round_trips(self):
        back = CourseSet.from_list(self.courses.to_list())
        self.assertEqual(back.names(), self.courses.names())
        self.assertEqual(back.require("Blue").codes, ["S1", "101", "102", "F1"])
        self.assertRaises(ValidationError, Course.from_dict, [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
