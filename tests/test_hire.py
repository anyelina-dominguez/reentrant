from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.entries.competitor import EntryList
from reentrant.entries.hire import Hire, HireBox
from reentrant.entries.importer import ALIASES, ImportReport, import_into, parse_entries
from reentrant.errors import ConflictError, NotFoundError, ValidationError

CSV = "\n".join([
    "Surname,First Name,Club,Class,SI Card,YOB,Gender,Hire,Course",
    "Okonkwo,Ada,DPO,W45,205431,1981,W,,Blue",
    "Bergstrom,Nils,SYO,M21,,90,M,y,",
    "Cai,Jo,HALO,m21,300111,2000,M,no,Green",
    "Broken,Row,DPO,ZZ99,300222,2000,M,,",
    "",
])


class Importing(unittest.TestCase):
    def test_the_column_spellings_seen_in_the_wild(self):
        report = parse_entries(CSV)
        self.assertEqual(report.read, 4)
        self.assertEqual(len(report.added), 3)
        self.assertEqual(report.added[0].competitor.listed_name, "Okonkwo, Ada")
        self.assertEqual(report.added[0].class_code, "W45")
        self.assertEqual(report.added[0].course, "Blue")
        self.assertIn("si card", ALIASES["card"])

    def test_one_bad_row_does_not_lose_the_file(self):
        report = parse_entries(CSV)
        self.assertFalse(report.ok)
        self.assertEqual(len(report.rejected), 1)
        self.assertEqual(report.rejected[0]["line"], 5)
        self.assertEqual(report.rejected[0]["name"], "Row Broken")
        self.assertIn("age class", report.rejected[0]["reason"])

    def test_a_two_digit_year_is_last_century_or_this_one(self):
        report = parse_entries(CSV)
        self.assertEqual(report.added[1].competitor.birth_year, 1990)
        self.assertEqual(parse_entries(
            "surname,first name,class,yob\nA,B,M21,05\n").added[0].competitor.birth_year, 2005)

    def test_hire_is_read_from_the_words_people_write(self):
        report = parse_entries(CSV)
        self.assertTrue(report.added[1].hired)
        self.assertFalse(report.added[2].hired)

    def test_a_class_written_in_lower_case(self):
        self.assertEqual(parse_entries(CSV).added[2].class_code, "M21")

    def test_a_file_with_no_name_column(self):
        self.assertRaises(ValidationError, parse_entries, "club,card\nDPO,205431\n")

    def test_an_empty_file(self):
        report = parse_entries("")
        self.assertEqual(report.read, 0)
        self.assertTrue(report.ok)
        self.assertEqual(report.to_dict()["added"], [])

    def test_importing_into_a_list_that_already_has_entries(self):
        entries = EntryList()
        parse_entries("surname,first name,class\nHeld,One,M21\n", entries=entries)
        report = import_into(entries, CSV)
        self.assertEqual([entry.reference for entry in report.added],
                         ["ENT-0002", "ENT-0003", "ENT-0004"])
        self.assertEqual(len(entries), 4)

    def test_a_card_already_entered_is_rejected_not_swallowed(self):
        entries = EntryList()
        parse_entries(CSV, entries=entries)
        again = import_into(entries, "surname,first name,class,si card\nTwice,Same,M21,205431\n")
        self.assertEqual(len(again.added), 0)
        self.assertIn("already entered", again.rejected[0]["reason"])

    def test_the_report_shape(self):
        self.assertEqual(ImportReport().to_dict(), {"read": 0, "added": [], "rejected": []})


class Hires(unittest.TestCase):
    def setUp(self):
        self.box = HireBox(owned=[300111, 300222, 300333])

    def test_lending_takes_a_card_out_of_the_box(self):
        hire = self.box.lend(300111, "ENT-0001", "Okonkwo, Ada", 36000, deposit="keys")
        self.assertEqual(hire.card, 300111)
        self.assertFalse(hire.returned)
        self.assertEqual(self.box.available(), [300222, 300333])
        self.assertEqual(hire.to_dict()["out"], "10:00:00")
        self.assertEqual(hire.deposit, "keys")

    def test_a_card_that_is_not_ours(self):
        self.assertRaises(NotFoundError, self.box.lend, 999999, "ENT-0001", "A", 36000)

    def test_a_card_cannot_be_lent_twice(self):
        self.box.lend(300111, "ENT-0001", "Okonkwo, Ada", 36000)
        with self.assertRaises(ConflictError) as caught:
            self.box.lend(300111, "ENT-0002", "Bo, Sam", 39600)
        self.assertEqual(caught.exception.details["held_by"], "ENT-0001")

    def test_a_card_stays_out_even_if_the_runner_never_downloaded(self):
        # The failure this rule exists for: the desk lends it again at eleven.
        self.box.lend(300111, "ENT-0001", "Okonkwo, Ada", 36000)
        self.assertNotIn(300111, self.box.available())

    def test_taking_a_card_back(self):
        self.box.lend(300111, "ENT-0001", "Okonkwo, Ada", 36000)
        back = self.box.take_back(300111, 43200)
        self.assertTrue(back.returned)
        self.assertEqual(self.box.available(), [300111, 300222, 300333])
        self.assertEqual(self.box.still_out(), [])
        self.assertRaises(NotFoundError, self.box.take_back, 300111, 43200)

    def test_a_card_may_be_lent_again_once_it_is_back(self):
        self.box.lend(300111, "ENT-0001", "A", 36000)
        self.box.take_back(300111, 39600)
        self.box.lend(300111, "ENT-0002", "B", 39700)
        self.assertEqual(self.box.summary()["lent_today"], 2)

    def test_what_is_still_out_at_the_end_of_the_day(self):
        self.box.lend(300111, "ENT-0001", "Okonkwo, Ada", 36000)
        self.box.lend(300222, "ENT-0002", "Bergstrom, Nils", 36600)
        self.box.take_back(300111, 43200)
        self.assertEqual([hire.name for hire in self.box.still_out()], ["Bergstrom, Nils"])
        self.assertEqual(self.box.summary(), {"owned": 3, "out": 1, "available": 2, "lent_today": 2})

    def test_the_box_serialises(self):
        self.box.lend(300111, "ENT-0001", "Okonkwo, Ada", 36000)
        told = self.box.to_dict()
        self.assertEqual(told["owned"], [300111, 300222, 300333])
        self.assertEqual(len(told["hires"]), 1)
        self.assertRaises(ValidationError, Hire, card=0, entry="E", name="N", out_seconds=0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
