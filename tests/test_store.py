from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from . import context  # noqa: F401

from reentrant.courses.control import Control, ControlSet
from reentrant.courses.course import Course, CourseSet
from reentrant.entries.competitor import Competitor, Entry, EntryList
from reentrant.errors import SchemaError
from reentrant.event.event import Event
from reentrant.geo.grid import parse as grid
from reentrant.results.classify import Result
from reentrant.store.jsonstore import EventFile, load, require, save
from reentrant.store.migrations import CURRENT_VERSION, migrate
from reentrant.timing.punch import read_from_pairs


def event() -> Event:
    controls = ControlSet()
    for code, east in {"S1": 12000, "101": 12300, "F1": 12100}.items():
        controls.add(Control(code, grid(f"SK {east} 67000")))
    courses = CourseSet()
    courses.add(Course("Blue", ["S1", "101", "F1"]))
    entries = EntryList()
    entries.add(Entry("ENT-0001", Competitor("Okonkwo", "Ada", "DPO", 1981, "W"),
                      "Blue", "W45", 205431))
    return Event("Club fixture", "2026-05-09", controls, courses, entries, {"W45": "Blue"})


def held() -> EventFile:
    return EventFile(
        event=event(),
        downloads=[read_from_pairs(205431, [("101", "10:04:11")], start="10:00:00", finish="10:21:12")],
        results=[Result("ENT-0001", "Okonkwo, Ada", "DPO", "W45", "Blue", 1272, "ok", 1, 0)],
    )


class Files(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())
        self.path = self.directory / "event.json"

    def test_an_event_round_trips_through_the_file(self):
        save(self.path, held())
        back = load(self.path)
        self.assertEqual(back.event.name, "Club fixture")
        self.assertEqual(len(back.event.entries), 1)
        self.assertEqual(len(back.downloads), 1)
        self.assertEqual(back.downloads[0].card, 205431)
        self.assertEqual(back.results[0].place, 1)
        self.assertEqual(back.to_dict(), held().to_dict())

    def test_the_file_is_readable_and_versioned(self):
        save(self.path, held())
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(raw["version"], CURRENT_VERSION)
        self.assertIn("event", raw)
        self.assertTrue(self.path.read_text(encoding="utf-8").endswith("\n"))

    def test_a_missing_file_is_not_an_error_until_it_has_to_be(self):
        self.assertIsNone(load(self.path))
        self.assertRaises(SchemaError, require, self.path)

    def test_a_broken_file_says_so_rather_than_throwing_a_parse_error(self):
        self.path.write_text("{ not json", encoding="utf-8")
        self.assertRaises(SchemaError, load, self.path)

    def test_saving_twice_leaves_no_working_file(self):
        save(self.path, held())
        save(self.path, held())
        self.assertFalse(self.path.with_suffix(".json.writing").exists())

    def test_the_directory_is_made_if_it_is_not_there(self):
        deeper = self.directory / "results" / "2026" / "event.json"
        save(deeper, held())
        self.assertTrue(deeper.exists())

    def test_a_corrected_result_survives_reopening(self):
        # The reason results are saved rather than recomputed: a mispunch
        # reinstated by the organiser cannot be worked out from the punches.
        file = held()
        file.results[0] = Result("ENT-0001", "Okonkwo, Ada", "DPO", "W45", "Blue",
                                 1272, "ok", 1, 0)
        save(self.path, file)
        self.assertEqual(load(self.path).results[0].outcome, "ok")


class Migrations(unittest.TestCase):
    def test_the_earliest_files_were_a_bare_event(self):
        upgraded = migrate({"name": "old fixture", "date": "2026-01-01"})
        self.assertEqual(upgraded["version"], CURRENT_VERSION)
        self.assertEqual(upgraded["event"]["name"], "old fixture")
        self.assertEqual(upgraded["downloads"], [])
        self.assertEqual(upgraded["results"], [])

    def test_a_version_one_file_gains_the_results(self):
        upgraded = migrate({"version": 1, "event": {"name": "x"}, "downloads": []})
        self.assertEqual(upgraded["version"], CURRENT_VERSION)
        self.assertEqual(upgraded["results"], [])
        self.assertEqual(upgraded["event"], {"name": "x"})

    def test_a_file_from_the_future_is_refused(self):
        self.assertRaises(SchemaError, migrate, {"version": CURRENT_VERSION + 1})
        self.assertRaises(SchemaError, migrate, {"version": "two"})
        self.assertRaises(SchemaError, migrate, {"version": True})
        self.assertRaises(SchemaError, migrate, [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class Paperwork(unittest.TestCase):
    """Version 3: the decisions live in the file, not only in the server."""

    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "event.json"

    def test_corrections_survive_the_file(self):
        from reentrant.timing.repair import Correction, CorrectionLog

        file = held()
        file.corrections = CorrectionLog()
        file.corrections.add(Correction("ENT-0001", "reinstate", "control was down", "organiser"))
        save(self.path, file)
        back = load(self.path)
        self.assertEqual(len(back.corrections), 1)
        self.assertEqual(back.corrections.corrections[0].by, "organiser")

    def test_complaints_survive_the_file(self):
        file = held()
        file.complaints = [{"reference": "CMP-0001", "entry": "ENT-0001", "about": "control 102"}]
        save(self.path, file)
        self.assertEqual(load(self.path).complaints[0]["reference"], "CMP-0001")

    def test_a_version_two_file_gains_them_empty(self):
        upgraded = migrate({"version": 2, "event": {"name": "x"}, "downloads": [], "results": []})
        self.assertEqual(upgraded["version"], CURRENT_VERSION)
        self.assertEqual(upgraded["corrections"], [])
        self.assertEqual(upgraded["complaints"], [])

    def test_the_older_files_still_open(self):
        self.assertEqual(migrate({"name": "very old"})["version"], CURRENT_VERSION)
        self.assertEqual(migrate({"version": 1, "event": {}})["complaints"], [])
