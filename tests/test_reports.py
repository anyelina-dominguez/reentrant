from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.courses.control import Control, ControlSet
from reentrant.courses.course import Course, CourseSet
from reentrant.entries.competitor import Competitor, Entry
from reentrant.event.download import Download
from reentrant.event.event import Event
from reentrant.geo.grid import parse as grid
from reentrant.reports.exports import entries_csv, results_csv, splits_csv
from reentrant.reports.sheets import (
    course_results_sheet, download_log_sheet, results_sheet, splits_sheet, start_list_sheet,
)
from reentrant.results.analysis import analyse_legs
from reentrant.results.classify import Result, classify
from reentrant.timing.validate import RunCheck
from reentrant.util.csv_io import read_rows


def event() -> Event:
    controls = ControlSet()
    for code, east, height in (("S1", 12000, 200.0), ("101", 12300, 210.0), ("F1", 12100, 205.0)):
        controls.add(Control(code, grid(f"SK {east} 67000"), height=height))
    courses = CourseSet()
    courses.add(Course("Blue", ["S1", "101", "F1"]))
    return Event("Club fixture", "2026-05-09", controls, courses,
                 class_courses={"W45": "Blue"}, venue="Longshaw")


ROWS = [
    Result("E1", "Okonkwo, Ada", "DPO", "W45", "Blue", 1872),
    Result("E2", "Bo, Sam", "SYO", "W45", "Blue", 1755),
    Result("E3", "Cai, Jo", "", "W45", "Blue", None, "mispunch"),
]


class Sheets(unittest.TestCase):
    def test_the_results_sheet_names_the_event_and_places_the_field(self):
        text = results_sheet(event(), ROWS)
        self.assertIn("Club fixture -- 2026-05-09", text)
        self.assertIn("Longshaw", text)
        self.assertIn("W45  (Blue)", text)
        self.assertIn("Bo, Sam", text)
        self.assertIn("mispunch", text)

    def test_the_winner_is_first_and_the_mispunch_is_last(self):
        lines = results_sheet(event(), ROWS).split("\n")
        names = [line for line in lines if "," in line and "--" not in line]
        self.assertLess(names.index(next(l for l in names if "Bo, Sam" in l)),
                        names.index(next(l for l in names if "Cai, Jo" in l)))

    def test_nothing_is_wider_than_the_page(self):
        for text in (results_sheet(event(), ROWS), course_results_sheet(event(), ROWS)):
            for line in text.split("\n"):
                self.assertLessEqual(len(line), 80, line)

    def test_the_course_sheet_carries_the_length_and_climb(self):
        text = course_results_sheet(event(), ROWS)
        self.assertIn("Blue", text)
        self.assertIn("km", text)
        self.assertIn("climb", text)

    def test_the_tally_is_at_the_bottom(self):
        self.assertIn("mispunch: 1 ok: 2", results_sheet(event(), ROWS))

    def test_the_start_list(self):
        rows = [{"time": "10:00:00", "course": "Blue", "name": "Okonkwo, Ada", "club": "DPO",
                 "seconds": 36000, "entry": "E1"}]
        text = start_list_sheet(event(), rows)
        self.assertIn("start list", text)
        self.assertIn("10:00:00", text)
        self.assertIn("1 starter", text)

    def test_the_splits_sheet_skips_runners_with_no_legs(self):
        legs = analyse_legs({
            "E1": [{"number": 1, "code": "101", "leg_seconds": 250}],
            "E2": [{"number": 1, "code": "101", "leg_seconds": 200}],
        })
        text = splits_sheet(legs, {"E1": "Okonkwo, Ada", "E2": "Bo, Sam", "E9": "Nobody, At All"})
        self.assertIn("Okonkwo, Ada", text)
        self.assertNotIn("Nobody, At All", text)

    def test_the_download_log(self):
        entry = Entry("E1", Competitor("Okonkwo", "Ada", "DPO"), "Blue", "W45", 205431)
        text = download_log_sheet([
            Download(card=205431, entry=entry, course="Blue", seconds=1272,
                     start_seconds=36000, check=RunCheck("ok")),
            Download(card=999999, problem="that card is not entered"),
        ])
        self.assertIn("205431", text)
        self.assertIn("Okonkwo, Ada", text)
        self.assertIn("21:12", text)
        self.assertNotIn("not classified", text, "a clean run has no note")
        # The note column is narrow, so the reason is truncated with an ellipsis.
        self.assertIn("that card is no", text)
        self.assertIn("2 cards read", text)


class Exports(unittest.TestCase):
    def test_the_results_csv_places_the_field_itself(self):
        rows = read_rows(results_csv(ROWS))
        self.assertEqual([row["place"] for row in rows], ["1", "2", ""])
        self.assertEqual(rows[0]["name"], "Bo, Sam")
        self.assertEqual(rows[2]["outcome"], "mispunch")
        self.assertEqual(rows[0]["seconds"], "1755")

    def test_a_name_with_a_comma_survives_the_round_trip(self):
        rows = read_rows(results_csv(ROWS))
        self.assertEqual(rows[0]["name"], "Bo, Sam")

    def test_rows_that_are_already_placed_are_left_alone(self):
        rows = read_rows(results_csv(classify(ROWS), place=False))
        self.assertEqual([row["place"] for row in rows], ["1", "2", ""])

    def test_the_splits_csv_is_one_row_a_leg(self):
        splits = {"E1": [{"number": 1, "code": "101", "leg_seconds": 250, "elapsed_seconds": 250},
                         {"number": 2, "code": "F1", "leg_seconds": 300, "elapsed_seconds": 550}]}
        rows = read_rows(splits_csv(splits, {"E1": "Okonkwo, Ada"}))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["leg"], "4:10")
        self.assertEqual(rows[1]["elapsed"], "9:10")
        self.assertEqual(rows[1]["name"], "Okonkwo, Ada")

    def test_the_entries_go_back_out_again(self):
        entries = [Entry("E1", Competitor("Okonkwo", "Ada", "DPO", 1981, "W"),
                         "Blue", "W45", 205431, hired=True)]
        rows = read_rows(entries_csv(entries))
        self.assertEqual(rows[0]["surname"], "Okonkwo")
        self.assertEqual(rows[0]["class"], "W45")
        self.assertEqual(rows[0]["hired"], "y")
        self.assertEqual(rows[0]["birth_year"], "1981")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
