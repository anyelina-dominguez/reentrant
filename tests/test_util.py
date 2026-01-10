from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.errors import ValidationError
from reentrant.util.csv_io import map_columns, read_rows, write_rows
from reentrant.util.ids import (
    FINISH_CODE, LOWEST_CONTROL_CODE, START_CODE, Sequence, is_reference,
    next_free_code, reference, require_control_code, require_reference,
)
from reentrant.util.text import columns, heading, plural, table, truncate, wrap


class Ids(unittest.TestCase):
    def test_references_come_off_a_counter(self):
        seq = Sequence()
        self.assertEqual(reference("ENT", seq.take()), "ENT-0001")
        self.assertEqual(reference("ENT", seq.take()), "ENT-0002")
        seq.observe(40)
        self.assertEqual(reference("ENT", seq.take()), "ENT-0041")
        seq.observe(3)
        self.assertEqual(seq.peek(), 42)

    def test_what_is_and_is_not_a_reference(self):
        self.assertTrue(is_reference("CRS-0003"))
        self.assertFalse(is_reference("crs-3"))
        self.assertFalse(is_reference(3))
        self.assertRaises(ValidationError, require_reference, "nope", "ref")
        self.assertEqual(require_reference("ENT-00042", "ref"), "ENT-00042")

    def test_control_codes_start_at_thirty_one(self):
        # Below 31 a code could be read as the control's number on the map.
        self.assertEqual(require_control_code("101"), "101")
        self.assertEqual(require_control_code(" 31 "), "31")
        self.assertRaises(ValidationError, require_control_code, "12")
        self.assertRaises(ValidationError, require_control_code, "7")
        self.assertRaises(ValidationError, require_control_code, "1001")
        self.assertRaises(ValidationError, require_control_code, "abc")
        self.assertEqual(LOWEST_CONTROL_CODE, 31)

    def test_start_and_finish_are_codes_too(self):
        self.assertEqual(require_control_code(START_CODE), "S1")
        self.assertEqual(require_control_code(FINISH_CODE), "F1")

    def test_the_next_free_code_skips_what_is_in_use(self):
        self.assertEqual(next_free_code([]), "31")
        self.assertEqual(next_free_code(["31", "32", "34"]), "33")
        self.assertEqual(next_free_code(["31"], start=100), "100")


class Text(unittest.TestCase):
    def test_a_table_lines_up_and_truncates(self):
        rendered = table(
            [{"key": "name", "title": "name"}, {"key": "time", "title": "time", "align": "right", "width": 6}],
            [{"name": "Ada Okonkwo", "time": "32:11"}, {"name": "Bo", "time": "9:02"}],
        )
        self.assertEqual(rendered.split("\n"), [
            "name           time",
            "-----------  ------",
            "Ada Okonkwo   32:11",
            "Bo             9:02",
        ])

    def test_truncation_marks_itself(self):
        self.assertEqual(truncate("Okonkwo", 4), "Oko.")
        self.assertEqual(truncate("Ada", 10), "Ada")
        self.assertEqual(truncate("Ada", 1), "A")

    def test_headings_wrapping_and_plurals(self):
        self.assertTrue(heading("results", 20).startswith("results ="))
        self.assertEqual(len(heading("results", 20)), 20)
        self.assertEqual(wrap("one two three", 7), ["one two", "three"])
        self.assertEqual(plural(1, "runner"), "1 runner")
        self.assertEqual(plural(0, "runner"), "0 runners")
        self.assertEqual(plural(2, "entry", "entries"), "2 entries")

    def test_a_start_list_in_columns(self):
        laid_out = columns(["10:00 Ada", "10:02 Bo", "10:04 Cai", "10:06 Dee", "10:08 Eve"], per_row=2, width=12)
        self.assertEqual(len(laid_out), 3)
        self.assertTrue(laid_out[0].startswith("10:00 Ada"))


class Csv(unittest.TestCase):
    def test_rows_come_back_with_a_normalised_header(self):
        rows = read_rows("First Name,Card Number\nAda,205431\n")
        self.assertEqual(rows, [{"first_name": "Ada", "card_number": "205431"}])

    def test_quoting_and_blank_lines_survive(self):
        rows = read_rows('name,club\n"Okonkwo, Ada",DPO\n\nBo,"South ""Yorks"""\n')
        self.assertEqual(rows[0]["name"], "Okonkwo, Ada")
        self.assertEqual(rows[1]["club"], 'South "Yorks"')
        self.assertEqual(len(rows), 2)

    def test_a_short_row_gets_empty_strings_rather_than_an_error(self):
        rows = read_rows("name,club,card\nAda,DPO\n")
        self.assertEqual(rows[0], {"name": "Ada", "club": "DPO", "card": ""})
        self.assertEqual(read_rows(""), [])

    def test_columns_are_mapped_from_the_spellings_seen_in_the_wild(self):
        aliases = {"name": ["name", "full name", "competitor"], "card": ["card", "si", "si card"]}
        mapping = map_columns(["Full Name", "SI Card"], aliases, required=["name", "card"])
        self.assertEqual(mapping, {"name": "full_name", "card": "si_card"})

    def test_a_missing_required_column_says_which(self):
        with self.assertRaises(ValidationError) as caught:
            map_columns(["name"], {"name": ["name"], "card": ["card"]}, required=["name", "card"])
        self.assertEqual(caught.exception.details["missing"], ["card"])

    def test_writing_round_trips(self):
        rows = [{"name": "Okonkwo, Ada", "time": "32:11"}, {"name": "Bo", "time": None}]
        text = write_rows([{"key": "name", "title": "name"}, {"key": "time", "title": "time"}], rows)
        self.assertEqual(read_rows(text), [
            {"name": "Okonkwo, Ada", "time": "32:11"},
            {"name": "Bo", "time": ""},
        ])
        self.assertRaises(ValidationError, write_rows, [], [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
