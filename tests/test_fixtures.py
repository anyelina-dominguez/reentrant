from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.errors import ConflictError, NotFoundError, RuleError, ValidationError
from reentrant.event.fixtures import STATES, Fixture, Season


def fixture(name="Longshaw", date="2026-11-15", **kwargs):
    return Fixture(name=name, date=date, venue="Longshaw",
                   opens=kwargs.pop("opens", "2026-10-01"),
                   closes=kwargs.pop("closes", "2026-11-10"), **kwargs)


class Fixtures(unittest.TestCase):
    def test_the_dates_have_to_be_in_order(self):
        self.assertRaises(ValidationError, fixture, opens="2026-11-01", closes="2026-10-01")
        self.assertRaises(ValidationError, fixture, closes="2026-11-20")
        self.assertRaises(ValidationError, fixture, date="the fifteenth")
        self.assertRaises(ValidationError, fixture, date="2026-02-30")

    def test_what_a_fixture_is_doing_on_a_given_day(self):
        one = fixture()
        self.assertEqual(one.state_on("2026-09-01"), "announced")
        self.assertEqual(one.state_on("2026-10-01"), "open")
        self.assertEqual(one.state_on("2026-11-01"), "open")
        self.assertEqual(one.state_on("2026-11-11"), "closed")
        self.assertEqual(one.state_on("2026-11-15"), "closed", "the day itself")
        self.assertEqual(one.state_on("2026-11-16"), "run")
        self.assertIn("cancelled", STATES)

    def test_a_cancelled_fixture_is_cancelled_whatever_the_date(self):
        one = fixture(cancelled=True)
        self.assertEqual(one.state_on("2026-10-15"), "cancelled")
        self.assertFalse(one.accepts("2026-10-15"))

    def test_a_fixture_with_no_entry_window_never_opens(self):
        one = Fixture("Informal", "2026-11-15")
        self.assertEqual(one.state_on("2026-11-01"), "announced")
        self.assertFalse(one.accepts("2026-11-01"))

    def test_entries_are_taken_while_it_is_open(self):
        one = fixture(capacity=3)
        self.assertTrue(one.accepts("2026-10-15"))
        self.assertEqual(one.take_entry("2026-10-15"), 1)
        self.assertEqual(one.room, 2)
        self.assertEqual(one.take_entry("2026-10-15", count=2), 3)
        self.assertTrue(one.full)

    def test_a_full_fixture_refuses_with_the_count(self):
        one = fixture(capacity=2)
        one.take_entry("2026-10-15", count=2)
        with self.assertRaises(ConflictError) as caught:
            one.take_entry("2026-10-15")
        self.assertEqual(caught.exception.details["capacity"], 2)
        self.assertFalse(one.accepts("2026-10-15"))

    def test_a_part_full_fixture_refuses_a_group_that_does_not_fit(self):
        one = fixture(capacity=3)
        one.take_entry("2026-10-15")
        self.assertRaises(ConflictError, one.take_entry, "2026-10-15", count=3)
        self.assertEqual(one.entered, 1, "nothing was taken")

    def test_entries_outside_the_window_are_refused_with_the_state(self):
        one = fixture()
        with self.assertRaises(RuleError) as caught:
            one.take_entry("2026-09-01")
        self.assertEqual(caught.exception.details["state"], "announced")
        self.assertRaises(RuleError, one.take_entry, "2026-11-12")

    def test_a_fixture_with_no_capacity_never_fills(self):
        one = fixture()
        one.take_entry("2026-10-15", count=500)
        self.assertFalse(one.full)
        self.assertIsNone(one.room)


class Seasons(unittest.TestCase):
    def season(self) -> Season:
        made = Season("Winter 2026")
        made.add(fixture("Longshaw", "2026-11-15", capacity=3))
        made.add(fixture("Burbage", "2026-12-06", opens="2026-11-01", closes="2026-12-01"))
        made.add(fixture("Stanage", "2027-01-10", opens="2026-12-01", closes="2027-01-05"))
        return made

    def test_the_list_is_in_date_order(self):
        self.assertEqual([row.name for row in self.season().all()],
                         ["Longshaw", "Burbage", "Stanage"])
        self.assertEqual(len(self.season()), 3)

    def test_one_name_once(self):
        made = self.season()
        self.assertRaises(ConflictError, made.add, fixture("Longshaw", "2027-02-01"))
        self.assertRaises(NotFoundError, made.require, "Padley")
        self.assertEqual(made.require("Burbage").venue, "Longshaw")

    def test_the_calendar_says_what_each_one_is_doing(self):
        rows = self.season().calendar("2026-11-05")
        self.assertEqual([row["state"] for row in rows], ["open", "open", "announced"])

    def test_the_fixtures_in_one_state(self):
        made = self.season()
        self.assertEqual([row.name for row in made.on("open", "2026-10-15")], ["Longshaw"])
        self.assertEqual([row.name for row in made.on("run", "2026-12-10")],
                         ["Longshaw", "Burbage"])

    def test_the_next_one_coming_up(self):
        made = self.season()
        self.assertEqual(made.next_after("2026-10-01").name, "Longshaw")
        self.assertEqual(made.next_after("2026-11-20").name, "Burbage")
        self.assertIsNone(made.next_after("2027-02-01"))

    def test_a_cancelled_fixture_is_not_the_next_one(self):
        made = self.season()
        made.require("Longshaw").cancelled = True
        self.assertEqual(made.next_after("2026-10-01").name, "Burbage")

    def test_the_season_serialises(self):
        rows = self.season().to_list()
        self.assertEqual(len(rows), 3)
        self.assertEqual(rows[0]["name"], "Longshaw")
        self.assertEqual(rows[0]["capacity"], 3)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
