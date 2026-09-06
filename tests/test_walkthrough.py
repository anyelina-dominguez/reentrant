from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from . import context as _context  # noqa: F401

from reentrant.api.context import Clock, Context
from reentrant.api.testapp import make_app
from reentrant.courses.control import Control
from reentrant.courses.course import Course
from reentrant.geo.grid import parse as grid
from reentrant.store.jsonstore import EventFile, load, save
from reentrant.event.event import Event


class Walkthrough(unittest.TestCase):
    """One event from the entry list to the write-up, over http and nothing else.

    This is the test that catches what the unit tests cannot: a reference
    minted in one place and not recognised in another, a state that cannot be
    reached in the order a Sunday actually happens in, a file that will not
    reopen halfway through.
    """

    def setUp(self):
        self.path = Path(tempfile.mkdtemp()) / "event.json"
        event = Event("Longshaw club fixture", "2026-05-09", venue="Longshaw")
        for code, east, north in [("S1", 12000, 67000), ("101", 12300, 67400),
                                  ("102", 12900, 67800), ("103", 13400, 67200),
                                  ("F1", 12100, 67050)]:
            event.controls.add(Control(code, grid(f"SK {east} {north}"), height=200.0))
        event.courses.add(Course("Blue", ["S1", "101", "102", "F1"]))
        event.courses.add(Course("Green", ["S1", "101", "103", "F1"]))
        event.class_courses.update({"W45": "Blue", "M21": "Green"})
        save(self.path, EventFile(event=event))
        self.client = make_app(Context.from_file(load(self.path), self.path))

    def card(self, card, start, finish, punches):
        return {"card": card, "start": start, "finish": finish,
                "punches": [{"code": code, "at": at} for code, at in punches]}

    def test_a_whole_sunday(self):
        client = self.client

        # The week before: is it ready?
        self.assertTrue(client.get("/event/check")[1]["ready"])

        # Entries.
        for surname, forename, club, class_code, card, year, sex in [
            ("Okonkwo", "Ada", "DPO", "W45", 205431, 1981, "W"),
            ("Bergstrom", "Nils", "SYO", "M21", 205999, 1990, "M"),
            ("Cai", "Jo", "HALO", "M21", 300111, 2000, "M"),
        ]:
            status, body = client.post("/entries", {
                "surname": surname, "forename": forename, "club": club,
                "class": class_code, "card": card, "birth_year": year, "sex": sex})
            self.assertEqual(status, 201, body)
        self.assertEqual(client.get("/entries")[1]["count"], 3)

        # The draw.
        drawn = client.post("/starts/draw", {"first": "10:00:00", "interval": 120})
        self.assertEqual(drawn[0], 201)
        self.assertEqual(len(drawn[1]["starts"]), 3)
        self.assertEqual(client.get("/starts")[1]["count"], 3)

        # The day. One clean run, one clean run, one mispunch.
        for card, start, finish, punches in [
            (205431, "10:00:00", "10:31:12", [("101", "10:04:11"), ("102", "10:18:44")]),
            (205999, "10:02:00", "10:33:10", [("101", "10:07:00"), ("103", "10:21:00")]),
            (300111, "10:04:00", "10:41:00", [("101", "10:12:00")]),
        ]:
            status, body = client.post("/download", self.card(card, start, finish, punches))
            self.assertEqual(status, 201, body)

        self.assertEqual(client.get("/downloads")[1]["count"], 3)
        self.assertEqual(client.get("/outstanding")[1]["count"], 0)

        # The board, now that everybody is in.
        board = client.get("/board")[1]
        self.assertFalse(board["state"]["provisional"])
        self.assertIn("FINAL", board["text"])

        # Results: two placed, one mispunch.
        results = client.get("/results")[1]
        self.assertEqual(results["counts"], {"mispunch": 1, "ok": 2})

        # The organiser reinstates the mispunch: the control was down.
        self.assertEqual(client.post("/corrections", {
            "entry": "ENT-0003", "decision": "reinstate",
            "reason": "103 was found in the bracken", "by": "organiser"})[0], 201)
        self.assertIn("Cai, Jo", client.get("/board")[1]["text"])

        # And it survives the laptop being restarted.
        reopened = make_app(Context.from_file(load(self.path), self.path))
        self.assertEqual(len(reopened.context.corrections), 1)

        # Splits and the write-up.
        splits = client.get("/splits/Blue")[1]
        self.assertEqual(len(splits["runners"]), 1)
        report = client.get("/report")[1]
        self.assertEqual(report["starters"], 3)
        self.assertEqual(report["finishers"], 2)
        self.assertEqual(len(report["courses"]), 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
