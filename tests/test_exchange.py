from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.courses.exchange import (
    read_controls, read_courses, read_pair, write_controls, write_courses,
)
from reentrant.errors import ValidationError
from reentrant.geo.grid import parse as grid
from reentrant.geo.mapscale import (
    CIRCLE_MM, PAPER, SCALES, Scale, extent, fits, largest_fitting, standard,
)

CONTROLS = """; the control file
101 SK 12345 67890 210 boulder
102 SK 12800 67900 240 northern:knoll/foot
103 SK 13400 68000
S1 SK 12000 67000
F1 SK 12100 67000
"""

COURSES = """; the course file
Blue: S1 101 102 F1
Green: S1 101 103 F1
Score,3600,10,10: 101 102 103
"""


class Scales(unittest.TestCase):
    def test_a_millimetre_is_the_scale_in_metres(self):
        self.assertEqual(Scale(10000).to_millimetres(100), 10.0)
        self.assertEqual(Scale(10000).to_metres(10), 100.0)
        self.assertEqual(Scale(15000).to_millimetres(150), 10.0)
        self.assertEqual(Scale(10000).name, "1:10000")

    def test_the_round_trip(self):
        for denominator in SCALES:
            scale = Scale(denominator)
            self.assertAlmostEqual(scale.to_metres(scale.to_millimetres(437)), 437)

    def test_circles_collide_when_controls_are_close(self):
        # A circle is 6 mm across, so at 1:10000 two controls under 60 m apart collide.
        self.assertTrue(Scale(10000).circles_overlap(40))
        self.assertFalse(Scale(10000).circles_overlap(80))
        self.assertFalse(Scale(4000).circles_overlap(40), "more detail, more room")
        self.assertEqual(CIRCLE_MM, 6.0)

    def test_only_the_scales_a_map_is_printed_at(self):
        self.assertEqual(standard(10000).denominator, 10000)
        self.assertRaises(ValidationError, standard, 12345)
        self.assertRaises(ValidationError, Scale, 10)

    def test_whether_the_ground_fits_the_paper(self):
        # 1.5 km by 1 km at 1:10000 is 150 mm by 100 mm, which fits A4.
        self.assertTrue(fits(1500, 1000, Scale(10000)))
        self.assertFalse(fits(1500, 1000, Scale(4000)))
        self.assertTrue(fits(1000, 1500, Scale(10000)), "either way up")
        self.assertRaises(ValidationError, fits, 100, 100, Scale(10000), "A0")
        self.assertIn("A3", PAPER)

    def test_the_most_detailed_scale_that_still_fits(self):
        # 1500 x 1000 m at 1:7500 is 200 x 133 mm, which fits A4 landscape.
        self.assertEqual(largest_fitting(1500, 1000).denominator, 7500)
        self.assertEqual(largest_fitting(400, 300).denominator, 4000)
        self.assertIsNone(largest_fitting(50_000, 50_000))

    def test_the_ground_a_set_of_controls_covers(self):
        points = [grid("SK 12000 67000"), grid("SK 13000 67500"), grid("SK 12500 68000")]
        self.assertEqual(extent(points), (1000.0, 1000.0))
        self.assertEqual(extent([]), (0.0, 0.0))


class ControlFiles(unittest.TestCase):
    def test_reading_a_control_file(self):
        controls, rejected = read_controls(CONTROLS)
        self.assertEqual(controls.codes(), ["101", "102", "103", "F1", "S1"])
        self.assertEqual(rejected, [])
        self.assertEqual(controls.require("101").height, 210)
        self.assertEqual(controls.require("102").description.text(), "northern knoll, foot")
        self.assertIsNone(controls.require("103").description)

    def test_comments_and_blank_lines_are_skipped(self):
        controls, rejected = read_controls("; nothing\n\n   \n101 SK 12000 67000\n")
        self.assertEqual(controls.codes(), ["101"])
        self.assertEqual(rejected, [])

    def test_one_bad_line_does_not_lose_the_file(self):
        controls, rejected = read_controls(CONTROLS + "nonsense here\n104 SK 14000 68000\n")
        self.assertEqual(len(controls), 6)
        self.assertEqual(len(rejected), 1)
        self.assertEqual(rejected[0]["reason"], "no grid reference")

    def test_a_description_that_is_not_one(self):
        _, rejected = read_controls("101 SK 12000 67000 210 wormhole\n")
        self.assertEqual(len(rejected), 1)
        self.assertIn("feature must be one of", rejected[0]["reason"])

    def test_a_control_code_that_is_not_allowed(self):
        _, rejected = read_controls("12 SK 12000 67000\n")
        self.assertEqual(len(rejected), 1)
        self.assertIn("31", rejected[0]["reason"])

    def test_a_control_file_round_trips(self):
        controls, _ = read_controls(CONTROLS)
        again, rejected = read_controls(write_controls(controls))
        self.assertEqual(rejected, [])
        self.assertEqual(again.to_list(), controls.to_list())


class CourseFiles(unittest.TestCase):
    def test_reading_a_course_file(self):
        courses, rejected = read_courses(COURSES)
        self.assertEqual(courses.names(), ["Blue", "Green", "Score"])
        self.assertEqual(rejected, [])
        self.assertEqual(courses.require("Blue").codes, ["S1", "101", "102", "F1"])

    def test_a_score_course_carries_its_scoring(self):
        courses, _ = read_courses(COURSES)
        scored = courses.require("Score")
        self.assertTrue(scored.is_scored)
        self.assertEqual(scored.time_limit_seconds, 3600)
        self.assertEqual(scored.points_per_control, 10)
        self.assertEqual(scored.penalty_per_minute, 10)

    def test_the_lines_that_are_not_courses(self):
        _, rejected = read_courses("broken\nEmpty:\n")
        self.assertEqual([row["reason"] for row in rejected], ["no colon", "no controls"])

    def test_a_course_that_will_not_build(self):
        _, rejected = read_courses("Blue,notanumber: S1 101 F1\n")
        self.assertEqual(len(rejected), 1)

    def test_a_course_file_round_trips(self):
        courses, _ = read_courses(COURSES)
        again, rejected = read_courses(write_courses(courses))
        self.assertEqual(rejected, [])
        self.assertEqual(again.to_list(), courses.to_list())


class Pairs(unittest.TestCase):
    def test_reading_both_and_saying_what_is_missing(self):
        result = read_pair(CONTROLS, COURSES)
        self.assertEqual(result["missing"], [])
        self.assertEqual(len(result["controls"]), 5)
        self.assertEqual(result["rejected"], [])

    def test_a_course_naming_a_control_that_is_not_in_the_file(self):
        result = read_pair(CONTROLS, "Red: S1 199 F1\n")
        self.assertEqual(result["missing"], ["199"])

    def test_two_empty_files(self):
        result = read_pair("", "")
        self.assertEqual(len(result["controls"]), 0)
        self.assertEqual(result["missing"], [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
