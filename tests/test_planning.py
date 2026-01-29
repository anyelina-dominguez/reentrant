from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.courses.control import Control, ControlSet
from reentrant.courses.course import Course, CourseSet
from reentrant.courses.descriptions import parse_description
from reentrant.courses.planning import (
    DOG_LEG_DEGREES, SHORT_LEG_METRES, _turn, bunching, check_course, check_event,
    dog_legs, shared_numbers, short_legs, summary, unbalanced_legs,
)
from reentrant.geo.grid import parse as grid


def controls(places: dict[str, tuple[int, int]]) -> ControlSet:
    found = ControlSet()
    for code, (east, north) in places.items():
        found.add(Control(
            code=code,
            position=grid(f"SK {east} {north}"),
            description=None if code in ("S1", "F1") else parse_description("knoll"),
        ))
    return found


class Turning(unittest.TestCase):
    def test_what_a_turn_measures(self):
        self.assertEqual(_turn(90, 270), 0, "straight back the way you came")
        self.assertEqual(_turn(90, 90), 180, "straight on")
        self.assertEqual(_turn(90, 180), 90, "a right angle")
        self.assertEqual(_turn(0, 180), 0)
        # 350 in, 10 out is a twenty degree bend, so 160 rather than a clean 180.
        self.assertEqual(_turn(350, 10), 160, "nearly straight on, across north")
        self.assertEqual(_turn(10, 350), 160)


class DogLegs(unittest.TestCase):
    def test_a_control_left_on_the_way_it_was_entered(self):
        # North to 101, then straight back south to 102.
        set_ = controls({"S1": (12000, 67000), "101": (12000, 67500),
                         "102": (12000, 67100), "F1": (12000, 67000)})
        course = Course("Blue", ["S1", "101", "102", "F1"])
        notes = dog_legs(course, set_)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].where, "101")
        self.assertEqual(notes[0].kind, "dog-leg")

    def test_a_course_that_keeps_turning_has_none(self):
        set_ = controls({"S1": (12000, 67000), "101": (12000, 67500),
                         "102": (12500, 67500), "F1": (12500, 67000)})
        self.assertEqual(dog_legs(Course("Blue", ["S1", "101", "102", "F1"]), set_), [])
        self.assertEqual(DOG_LEG_DEGREES, 30.0)


class LegLengths(unittest.TestCase):
    def test_a_leg_shorter_than_the_limit(self):
        set_ = controls({"S1": (12000, 67000), "101": (12000, 67500),
                         "102": (12000, 67550), "F1": (12000, 68000)})
        notes = short_legs(Course("Blue", ["S1", "101", "102", "F1"]), set_)
        self.assertEqual(len(notes), 1)
        self.assertEqual(notes[0].where, "101-102")
        self.assertIn("50 m", notes[0].message)
        self.assertEqual(SHORT_LEG_METRES, 100.0)

    def test_a_leg_that_is_most_of_a_short_course(self):
        set_ = controls({"S1": (12000, 67000), "101": (12000, 67200),
                         "102": (12000, 68000), "F1": (12000, 68100)})
        notes = unbalanced_legs(Course("Green", ["S1", "101", "102", "F1"]), set_)
        self.assertEqual([note.where for note in notes], ["101-102"])
        self.assertIn("%", notes[0].message)

    def test_a_long_course_is_allowed_a_long_leg(self):
        set_ = controls({"S1": (12000, 67000), "101": (12000, 69000),
                         "102": (12000, 72000), "F1": (12000, 72500)})
        self.assertEqual(unbalanced_legs(Course("Brown", ["S1", "101", "102", "F1"]), set_), [])

    def test_a_course_with_no_length_is_not_unbalanced(self):
        set_ = controls({"S1": (12000, 67000), "F1": (12000, 67000)})
        self.assertEqual(unbalanced_legs(Course("Nothing", ["S1", "F1"]), set_), [])


class WholeCourse(unittest.TestCase):
    def test_the_notes_come_back_worst_first(self):
        set_ = controls({"S1": (12000, 67000), "101": (12000, 67500),
                         "102": (12000, 67450), "F1": (12000, 67000)})
        notes = check_course(Course("Blue", ["S1", "101", "102", "F1"]), set_)
        self.assertEqual(notes[0].kind, "dog-leg")
        self.assertTrue(any(note.kind == "short-leg" for note in notes))
        self.assertEqual(notes[0].to_dict()["course"], "Blue")


class WholeEvent(unittest.TestCase):
    def setUp(self):
        self.controls = controls({
            "S1": (12000, 67000), "101": (12300, 67400), "102": (12800, 67900),
            "103": (12200, 68200), "F1": (12100, 67100),
        })
        self.courses = CourseSet()
        self.courses.add(Course("Blue", ["S1", "101", "102", "F1"]))
        self.courses.add(Course("Green", ["S1", "101", "103", "F1"]))

    def test_a_control_with_the_same_number_on_two_courses(self):
        notes = shared_numbers(self.courses)
        self.assertEqual([note.where for note in notes], ["101"])
        self.assertIn("number 1", notes[0].message)
        self.assertEqual(notes[0].course, "Blue, Green")

    def test_courses_that_start_to_the_same_control(self):
        notes = bunching(self.courses)
        self.assertEqual([note.where for note in notes], ["101"])
        self.assertIn("2 courses", notes[0].message)

    def test_courses_that_split_at_once_do_not_bunch(self):
        courses = CourseSet()
        courses.add(Course("Blue", ["S1", "101", "F1"]))
        courses.add(Course("Green", ["S1", "102", "F1"]))
        self.assertEqual(bunching(courses), [])
        self.assertEqual(shared_numbers(courses), [])

    def test_a_score_course_does_not_bunch(self):
        courses = CourseSet()
        courses.add(Course("Score", ["101", "102"], "score", time_limit_seconds=3600))
        courses.add(Course("Blue", ["S1", "101", "F1"]))
        self.assertEqual(bunching(courses), [])

    def test_the_whole_event_and_its_summary(self):
        notes = check_event(self.courses, self.controls)
        counts = summary(notes)
        self.assertEqual(counts.get("shared-number"), 1)
        self.assertEqual(counts.get("bunching"), 1)
        self.assertEqual(sum(counts.values()), len(notes))
        self.assertEqual(summary([]), {})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
