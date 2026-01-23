from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.errors import ValidationError
from reentrant.geo.distance import (
    Distance, bearing, between, climb, compass_point, descent, path_length,
)
from reentrant.geo.grid import LETTERS, Point, coarsest, parse, _square_origin


class GridSquares(unittest.TestCase):
    def test_the_squares_people_actually_use(self):
        self.assertEqual(_square_origin("SK"), (400_000, 300_000))
        self.assertEqual(_square_origin("SU"), (400_000, 100_000))
        self.assertEqual(_square_origin("TQ"), (500_000, 100_000))
        self.assertEqual(_square_origin("NN"), (200_000, 700_000))

    def test_every_square_on_the_grid_round_trips(self):
        checked = 0
        for first in LETTERS:
            for second in LETTERS:
                try:
                    easting, northing = _square_origin(first + second)
                except ValidationError:
                    continue
                if not (0 <= easting < 700_000 and 0 <= northing < 1_300_000):
                    continue
                checked += 1
                self.assertEqual(Point(easting + 500, northing + 500).square, first + second)
        self.assertEqual(checked, 91)

    def test_a_letter_that_is_not_a_square(self):
        self.assertRaises(ValidationError, _square_origin, "SI")
        self.assertRaises(ValidationError, parse, "ZZ 12 34")


class Parsing(unittest.TestCase):
    def test_each_precision_lands_in_the_right_place(self):
        self.assertEqual((parse("SK 12 34").easting, parse("SK 12 34").northing), (412_000, 334_000))
        self.assertEqual((parse("SK 123 456").easting, parse("SK 123 456").northing), (412_300, 345_600))
        self.assertEqual((parse("SK 1234 5678").easting, parse("SK 1234 5678").northing), (412_340, 356_780))
        self.assertEqual((parse("SU 12345 67890").easting, parse("SU 12345 67890").northing), (412_345, 167_890))

    def test_the_precision_is_kept(self):
        self.assertEqual(parse("SK 12 34").precision, 1000)
        self.assertEqual(parse("SK 123 456").precision, 100)
        self.assertEqual(parse("SK 1234 5678").precision, 10)
        self.assertEqual(parse("SK 12345 67890").precision, 1)

    def test_bare_eastings_and_northings(self):
        point = parse("433210,367890")
        self.assertEqual((point.easting, point.northing, point.precision), (433_210, 367_890, 1))
        self.assertEqual(parse("433210 367890").easting, 433_210)

    def test_spacing_and_case_do_not_matter(self):
        self.assertEqual(parse("sk123456"), parse("SK 123 456"))
        self.assertEqual(parse("  SK  123   456 "), parse("SK 123 456"))

    def test_the_things_that_are_not_references(self):
        for bad in ["SK 123 45", "SK 1 2", "SK 123456 123456", "somewhere", "SK", ""]:
            with self.subTest(bad=bad):
                self.assertRaises(ValidationError, parse, bad)
        self.assertRaises(ValidationError, parse, 12345)

    def test_printing_uses_the_precision_it_was_given(self):
        self.assertEqual(str(parse("SK 123 456")), "SK 123 456")
        self.assertEqual(str(parse("SK 12 34")), "SK 12 34")
        self.assertEqual(parse("SK 12345 67890").reference(3), "SK 123 678")
        self.assertRaises(ValidationError, parse("SK 123 456").reference, 6)

    def test_a_position_off_the_grid_cannot_be_lettered(self):
        with self.assertRaises(ValidationError):
            Point(900_000, 100_000).square
        self.assertRaises(ValidationError, Point, 1, 1, 3)


class Distances(unittest.TestCase):
    def test_a_straight_leg(self):
        start, finish = parse("SK 1200 3400"), parse("SK 1300 3400")
        self.assertAlmostEqual(between(start, finish).metres, 1000.0)
        self.assertEqual(between(start, finish).rounded(), 1000)

    def test_a_diagonal_leg(self):
        start, finish = parse("SK 1200 3400"), parse("SK 1300 3500")
        self.assertAlmostEqual(between(start, finish).metres, 1414.2, places=1)
        self.assertEqual(between(start, finish).rounded(100), 1400)

    def test_the_uncertainty_follows_the_coarser_input(self):
        precise = between(parse("SK 12345 67890"), parse("SK 12445 67890"))
        self.assertEqual(precise.uncertainty, 0.0)
        rough = between(parse("SK 12 34"), parse("SK 13 34"))
        self.assertGreater(rough.uncertainty, 1400)
        mixed = between(parse("SK 12345 67890"), parse("SK 124 678"))
        self.assertEqual(coarsest(parse("SK 12345 67890"), parse("SK 124 678")), 100)
        self.assertAlmostEqual(mixed.uncertainty, 141.4, places=1)

    def test_a_leg_to_nowhere_is_no_distance(self):
        here = parse("SK 1200 3400")
        self.assertEqual(between(here, here).metres, 0.0)
        self.assertEqual(bearing(here, here), 0.0)
        self.assertEqual(path_length([here]), Distance(0.0, 0.0))
        self.assertRaises(ValidationError, between(here, here).rounded, 0)

    def test_bearings_run_clockwise_from_grid_north(self):
        here = parse("SK 1200 3400")
        self.assertEqual(bearing(here, parse("SK 1200 3500")), 0.0)
        self.assertEqual(bearing(here, parse("SK 1300 3400")), 90.0)
        self.assertEqual(bearing(here, parse("SK 1200 3300")), 180.0)
        self.assertEqual(bearing(here, parse("SK 1100 3400")), 270.0)
        self.assertAlmostEqual(bearing(here, parse("SK 1300 3500")), 45.0)

    def test_compass_points(self):
        self.assertEqual(compass_point(0), "N")
        self.assertEqual(compass_point(90), "E")
        self.assertEqual(compass_point(225), "SW")
        self.assertEqual(compass_point(359), "N")
        self.assertEqual(compass_point(-90), "W")

    def test_a_path_adds_its_legs_and_its_errors_in_quadrature(self):
        points = [parse("SK 1200 3400"), parse("SK 1300 3400"), parse("SK 1300 3500")]
        path = path_length(points)
        self.assertAlmostEqual(path.metres, 2000.0)
        # Two legs each uncertain by 14.1 m give 20 m over the course, not 28.2.
        self.assertAlmostEqual(path.uncertainty, 20.0, places=1)


class Climb(unittest.TestCase):
    def test_climb_counts_only_the_rises(self):
        self.assertEqual(climb([100, 150, 120, 200]), 130.0)
        self.assertEqual(descent([100, 150, 120, 200]), 30.0)

    def test_a_course_that_only_goes_down_has_no_climb(self):
        self.assertEqual(climb([300, 200, 100]), 0.0)
        self.assertEqual(descent([300, 200, 100]), 200.0)

    def test_too_few_heights_to_have_climbed(self):
        self.assertEqual(climb([]), 0.0)
        self.assertEqual(climb([100]), 0.0)
        self.assertEqual(descent([100]), 0.0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
