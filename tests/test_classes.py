from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.entries.classes import (
    JUNIOR_AGES, OPEN_AGE, VETERAN_AGES, AgeClass, age_at_year_end, all_classes,
    class_for, eligible_classes, may_enter, parse_class,
)
from reentrant.errors import ValidationError


class Age(unittest.TestCase):
    def test_age_is_taken_at_the_end_of_the_year(self):
        # Somebody born in 1981 is 45 for the whole of 2026, birthday or not.
        self.assertEqual(age_at_year_end(1981, 2026), 45)
        self.assertEqual(age_at_year_end(2026, 2026), 0)

    def test_the_unborn_and_the_impossible(self):
        self.assertRaises(ValidationError, age_at_year_end, 2027, 2026)
        self.assertRaises(ValidationError, age_at_year_end, 1800, 2026)


class Classes(unittest.TestCase):
    def test_juniors_land_on_the_ceiling_above_them(self):
        self.assertEqual(class_for(2016, 2026, "M").code, "M10")
        self.assertEqual(class_for(2015, 2026, "M").code, "M12")
        self.assertEqual(class_for(2012, 2026, "W").code, "W14")
        self.assertEqual(class_for(2006, 2026, "M").code, "M20")

    def test_twenty_one_is_everything_in_between(self):
        self.assertEqual(class_for(2005, 2026, "M").code, "M21")
        self.assertEqual(class_for(1992, 2026, "M").code, "M21")
        self.assertTrue(class_for(2005, 2026, "M").is_open)

    def test_veterans_land_on_the_floor_below_them(self):
        self.assertEqual(class_for(1991, 2026, "M").code, "M35")
        self.assertEqual(class_for(1981, 2026, "M").code, "M45")
        self.assertEqual(class_for(1955, 2026, "W").code, "W70")
        self.assertTrue(class_for(1955, 2026, "W").is_veteran)

    def test_the_boundary_years_either_side_of_a_class(self):
        self.assertEqual(class_for(1992, 2026, "M").code, "M21", "34 is still open")
        self.assertEqual(class_for(1991, 2026, "M").code, "M35", "35 on the nose")
        self.assertEqual(class_for(2006, 2026, "M").code, "M20", "20 on the nose")
        self.assertEqual(class_for(2005, 2026, "M").code, "M21", "21 is open")

    def test_a_class_admits_by_age(self):
        self.assertTrue(AgeClass("M", 14).admits(12))
        self.assertTrue(AgeClass("M", 14).admits(14))
        self.assertFalse(AgeClass("M", 14).admits(15))
        self.assertTrue(AgeClass("M", 45).admits(50))
        self.assertFalse(AgeClass("M", 45).admits(44))
        self.assertTrue(AgeClass("M", 21).admits(8))

    def test_parsing_and_printing(self):
        self.assertEqual(parse_class("m45").code, "M45")
        self.assertEqual(str(parse_class("W21")), "W21")
        for bad in ["M46", "X21", "M4", "M045", "", "Mxx"]:
            with self.subTest(bad=bad):
                self.assertRaises(ValidationError, parse_class, bad)
        self.assertRaises(ValidationError, AgeClass, "M", 46)
        self.assertRaises(ValidationError, AgeClass, "X", 21)

    def test_the_whole_list_for_one_sex(self):
        codes = [entry.code for entry in all_classes("M")]
        self.assertEqual(codes[0], "M10")
        self.assertEqual(codes[len(JUNIOR_AGES)], f"M{OPEN_AGE}")
        self.assertEqual(codes[-1], f"M{VETERAN_AGES[-1]}")
        self.assertEqual(len(codes), len(JUNIOR_AGES) + 1 + len(VETERAN_AGES))


class Eligibility(unittest.TestCase):
    def test_a_junior_may_run_up_but_not_down(self):
        codes = [entry.code for entry in eligible_classes(2012, 2026, "M")]
        self.assertEqual(codes, ["M14", "M16", "M18", "M20", "M21"])
        self.assertTrue(may_enter(2012, 2026, "M", "M16"))
        self.assertFalse(may_enter(2012, 2026, "M", "M12"))
        self.assertFalse(may_enter(2012, 2026, "M", "M35"))

    def test_an_open_runner_has_only_the_open_class(self):
        self.assertEqual([entry.code for entry in eligible_classes(2000, 2026, "W")], ["W21"])

    def test_a_veteran_may_run_down_to_open_but_not_older(self):
        codes = [entry.code for entry in eligible_classes(1981, 2026, "M")]
        self.assertEqual(codes, ["M35", "M40", "M45", "M21"])
        self.assertTrue(may_enter(1981, 2026, "M", "M40"))
        self.assertTrue(may_enter(1981, 2026, "M", "M21"))
        self.assertFalse(may_enter(1981, 2026, "M", "M50"))
        self.assertFalse(may_enter(1981, 2026, "M", "M18"))

    def test_the_sexes_do_not_mix(self):
        self.assertFalse(may_enter(1981, 2026, "M", "W45"))
        self.assertTrue(may_enter(1981, 2026, "W", "W45"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
