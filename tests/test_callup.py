from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.entries.competitor import Competitor, Entry
from reentrant.errors import ValidationError
from reentrant.starts.callup import STAGES, call_up, missing_from
from reentrant.util.times import parse_time_of_day as at


def entry(reference, start, name="Runner"):
    return Entry(reference, Competitor(name, reference[-1]), "Blue", "M21",
                 200_000 + int(reference[-4:]), start_seconds=at(start))


class CallUp(unittest.TestCase):
    def setUp(self):
        self.entries = [
            entry("ENT-0001", "10:00:00", "First"),
            entry("ENT-0002", "10:02:00", "Second"),
            entry("ENT-0003", "10:04:00", "Third"),
            entry("ENT-0004", "10:30:00", "Later"),
        ]

    def test_who_should_be_where_at_ten_oclock(self):
        rows = call_up(self.entries, at("10:00:00"))
        self.assertEqual([row.name for row in rows],
                         ["First, 1", "Second, 2", "Third, 3"])
        self.assertEqual(rows[0].stage, "line")
        self.assertEqual(rows[1].stage, "map box")
        self.assertEqual(rows[2].stage, "queue")

    def test_somebody_half_an_hour_away_is_not_called_yet(self):
        rows = call_up(self.entries, at("10:00:00"))
        self.assertNotIn("Later, 4", [row.name for row in rows])
        self.assertEqual(STAGES[0], ("queue", 4))

    def test_somebody_whose_slot_has_passed_is_not_called(self):
        rows = call_up(self.entries, at("10:03:00"))
        self.assertNotIn("First, 1", [row.name for row in rows])

    def test_a_runner_with_no_slot_is_not_called(self):
        without = Entry("ENT-0009", Competitor("No", "Slot"), "Blue", "M21", 209999)
        self.assertEqual(call_up([without], at("10:00:00")), [])

    def test_the_course_can_be_resolved_from_the_class(self):
        rows = call_up(self.entries, at("10:00:00"), course_of=lambda entry: "Green")
        self.assertTrue(all(row.course == "Green" for row in rows))
        self.assertEqual(rows[0].to_dict()["start"], "10:00:00")

    def test_the_time_is_checked(self):
        self.assertRaises(ValidationError, call_up, self.entries, -1)

    def test_who_is_due_at_the_line_and_not_there(self):
        missing = missing_from(self.entries, at("10:00:00"), present=set())
        self.assertEqual([entry.reference for entry in missing], ["ENT-0001"])
        self.assertEqual(missing_from(self.entries, at("10:00:00"), {"ENT-0001"}), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
