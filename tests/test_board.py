from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.courses.control import Control, ControlSet
from reentrant.courses.course import Course, CourseSet
from reentrant.courses.descriptions import parse_description
from reentrant.courses.sheets import (
    all_sheets, collection_list, control_card, description_sheet,
)
from reentrant.event.event import Event
from reentrant.geo.grid import parse as grid
from reentrant.reports.board import SHOWN, board, leaders, state, still_out_by_course
from reentrant.results.classify import Result
from reentrant.util.times import parse_time_of_day as at


def controls() -> ControlSet:
    found = ControlSet()
    found.add(Control("S1", grid("SK 12000 67000"), height=200.0))
    found.add(Control("101", grid("SK 12300 67200"), parse_description("northern:knoll/foot"), 210.0))
    found.add(Control("102", grid("SK 12800 67600"), parse_description("boulder"), 240.0))
    found.add(Control("103", grid("SK 13400 68000"), parse_description("path/junction"), 225.0))
    found.add(Control("F1", grid("SK 12100 67100"), height=205.0))
    return found


def event() -> Event:
    courses = CourseSet()
    courses.add(Course("Blue", ["S1", "101", "102", "F1"]))
    courses.add(Course("Green", ["S1", "101", "103", "F1"]))
    return Event("Club fixture", "2026-05-09", controls(), courses,
                 class_courses={"M21": "Blue", "W45": "Green"})


def rows(still_out=1):
    made = [Result(f"E{index}", f"Runner {index}", "DPO", "M21", "Blue", 1700 + index * 10)
            for index in range(1, 8)]
    for index in range(still_out):
        made.append(Result(f"X{index}", f"Waiting {index}", "SYO", "M21", "Blue", None, "dns"))
    return made


class Board(unittest.TestCase):
    def test_a_board_with_people_still_out_is_provisional(self):
        told = state(event(), rows(2), at("12:30:00"))
        self.assertTrue(told.provisional)
        self.assertEqual(told.still_out, 2)
        self.assertEqual(told.to_dict()["at"], "12:30:00")

    def test_a_board_with_everybody_in_is_final(self):
        self.assertFalse(state(event(), rows(0), at("14:00:00")).provisional)

    def test_the_sheet_says_which_it_is_and_when(self):
        text = board(event(), rows(2), at("12:30:00"))
        self.assertIn("PROVISIONAL", text)
        self.assertIn("printed 12:30:00", text)
        self.assertIn("2 still out", text)
        self.assertIn("FINAL", board(event(), rows(0), at("14:00:00")))

    def test_only_the_first_few_are_shown(self):
        text = board(event(), rows(0), at("14:00:00"))
        self.assertIn("Runner 1", text)
        self.assertNotIn("Runner 7", text)
        self.assertIn("and 2 others", text)
        self.assertEqual(SHOWN, 5)

    def test_a_shorter_board(self):
        text = board(event(), rows(0), at("14:00:00"), shown=2)
        self.assertIn("and 5 others", text)

    def test_who_is_still_out_by_course(self):
        counted = still_out_by_course(event(), rows(2))
        blue = next(row for row in counted if row["course"] == "Blue")
        self.assertEqual(blue["still_out"], 2)
        self.assertEqual(next(row for row in counted if row["course"] == "Green")["still_out"], 0)

    def test_a_class_where_nobody_has_finished_is_left_off(self):
        text = board(event(), [Result("X1", "Waiting", "SYO", "W45", "Green", None, "dns")],
                     at("11:00:00"))
        self.assertNotIn("W45", text.split("still out")[0])

    def test_the_leaders(self):
        current = leaders(rows(1))
        self.assertEqual(current[0]["name"], "M21")
        self.assertEqual(current[0]["leader"], "Runner 1")
        self.assertEqual(current[0]["finishers"], 7)
        by_course = leaders(rows(1), by="course")
        self.assertEqual(by_course[0]["name"], "Blue")


class Sheets(unittest.TestCase):
    def test_a_description_sheet_has_a_header_and_a_row_per_control(self):
        text = description_sheet(Course("Blue", ["S1", "101", "102", "F1"]), controls())
        lines = text.split("\n")
        self.assertIn("Blue", lines[0])
        self.assertIn("km", lines[0])
        self.assertIn("climb", lines[0])
        self.assertIn("  S  start", text)
        self.assertIn("northern knoll, foot", text)
        self.assertIn("finish", lines[-1])

    def test_the_controls_are_numbered_in_course_order(self):
        text = description_sheet(Course("Blue", ["S1", "101", "102", "F1"]), controls())
        self.assertIn("  1   101", text)
        self.assertIn("  2   102", text)

    def test_a_score_course_sheet_has_no_numbers(self):
        scored = Course("Score", ["101", "102", "103"], "score", time_limit_seconds=3600)
        text = description_sheet(scored, controls())
        self.assertIn("score, 60 minutes", text)
        self.assertNotIn("  1 ", text)

    def test_a_control_with_no_description(self):
        found = controls()
        found.put(Control("104", grid("SK 14000 68000")))
        text = description_sheet(Course("Red", ["S1", "104", "F1"]), found)
        self.assertIn("104", text)

    def test_every_course_at_once(self):
        courses = CourseSet()
        courses.add(Course("Blue", ["S1", "101", "102", "F1"]))
        courses.add(Course("Green", ["S1", "101", "103", "F1"]))
        text = all_sheets(courses, controls())
        self.assertIn("Blue", text)
        self.assertIn("Green", text)

    def test_the_collectors_list_is_by_code_not_by_course(self):
        text = control_card(controls())
        self.assertIn("101", text)
        self.assertIn("SK 12300 67200", text)
        self.assertNotIn("start", text, "the start is not collected like a control")

    def test_a_control_no_course_used_is_still_collected(self):
        found = controls()
        found.put(Control("199", grid("SK 15000 69000")))
        courses = CourseSet()
        courses.add(Course("Blue", ["S1", "101", "102", "F1"]))
        rows = collection_list(courses, found)
        orphan = next(row for row in rows if row["code"] == "199")
        self.assertEqual(orphan["courses"], [])
        self.assertEqual(len(rows), 4)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
