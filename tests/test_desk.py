from __future__ import annotations

import unittest

from . import context as _context  # noqa: F401

from reentrant.api.context import Clock, Context
from reentrant.api.testapp import test_app
from reentrant.courses.control import Control, ControlSet
from reentrant.courses.course import Course, CourseSet
from reentrant.entries.competitor import Competitor, Entry, EntryList
from reentrant.event.event import Event
from reentrant.geo.grid import parse as grid


def build() -> Event:
    controls = ControlSet()
    for code, east in {"S1": 12000, "101": 12300, "102": 12800, "F1": 12100}.items():
        controls.add(Control(code, grid(f"SK {east} 67000")))
    courses = CourseSet()
    courses.add(Course("Blue", ["S1", "101", "102", "F1"]))
    entries = EntryList()
    entries.add(Entry("ENT-0001", Competitor("Okonkwo", "Ada", "DPO", 1981, "W"),
                      "Blue", "W45", 205431, start_seconds=36000))
    entries.add(Entry("ENT-0002", Competitor("Bo", "Sam", "SYO", 1990, "M"),
                      "Blue", "W45", 205999, start_seconds=36120))
    return Event("Club fixture", "2026-05-09", controls, courses, entries, {"W45": "Blue"})


def app():
    return test_app(Context(event=build(), clock=Clock.stopped_at(45000)))


class Hire(unittest.TestCase):
    def test_stocking_the_box_and_lending_from_it(self):
        client = app()
        self.assertEqual(client.post("/hire/stock", {"cards": [300111, 300222]})[1]["owned"],
                         [300111, 300222])
        status, body = client.post("/hire", {"entry": "ENT-0001", "card": 300111,
                                             "at": "10:00:00", "deposit": "keys"})
        self.assertEqual(status, 201)
        self.assertEqual(body["name"], "Okonkwo, Ada")
        self.assertEqual(body["out"], "10:00:00")
        told = client.get("/hire")[1]
        self.assertEqual(told["available"], [300222])
        self.assertEqual(told["summary"]["out"], 1)

    def test_the_time_defaults_to_the_clock(self):
        client = app()
        client.post("/hire/stock", {"cards": [300111]})
        self.assertEqual(client.post("/hire", {"entry": "ENT-0001", "card": 300111})[1]["out"],
                         "12:30:00")

    def test_a_card_that_is_not_ours_or_already_out(self):
        client = app()
        client.post("/hire/stock", {"cards": [300111]})
        self.assertEqual(client.post("/hire", {"entry": "ENT-0001", "card": 999999})[0], 404)
        client.post("/hire", {"entry": "ENT-0001", "card": 300111})
        self.assertEqual(client.post("/hire", {"entry": "ENT-0002", "card": 300111})[0], 409)

    def test_lending_to_somebody_who_is_not_entered(self):
        client = app()
        client.post("/hire/stock", {"cards": [300111]})
        self.assertEqual(client.post("/hire", {"entry": "ENT-0009", "card": 300111})[0], 404)

    def test_taking_a_card_back(self):
        client = app()
        client.post("/hire/stock", {"cards": [300111]})
        client.post("/hire", {"entry": "ENT-0001", "card": 300111, "at": "10:00:00"})
        status, body = client.delete("/hire/300111", {"at": "13:00:00"})
        self.assertEqual(status, 200)
        self.assertTrue(body["returned"])
        self.assertEqual(client.get("/hire")[1]["available"], [300111])
        self.assertEqual(client.delete("/hire/300111")[0], 404)


class Corrections(unittest.TestCase):
    def test_a_correction_is_recorded(self):
        client = app()
        status, body = client.post("/corrections", {
            "entry": "ENT-0001", "decision": "reinstate", "reason": "control was down",
            "by": "organiser"})
        self.assertEqual(status, 201)
        self.assertEqual(body["decision"], "reinstate")
        self.assertEqual(len(client.get("/corrections")[1]["corrections"]), 1)

    def test_a_correction_about_somebody_who_is_not_entered(self):
        self.assertEqual(app().post("/corrections", {
            "entry": "ENT-0009", "decision": "reinstate", "reason": "x"})[0], 404)

    def test_a_decision_that_does_not_exist(self):
        self.assertEqual(app().post("/corrections", {
            "entry": "ENT-0001", "decision": "pardon", "reason": "x"})[0], 400)

    def test_the_same_decision_twice(self):
        client = app()
        body = {"entry": "ENT-0001", "decision": "reinstate", "reason": "control was down"}
        client.post("/corrections", body)
        self.assertEqual(client.post("/corrections", body)[0], 409)


class Complaints(unittest.TestCase):
    def test_a_complaint_is_made_and_answered(self):
        client = app()
        status, body = client.post("/complaints", {
            "entry": "ENT-0001", "about": "control 102 was not where the map said",
            "made": "13:05:00", "results": "13:00:00"})
        self.assertEqual(status, 201)
        self.assertTrue(body["in_time"])
        self.assertEqual(body["reference"], "CMP-0001")

        answered = client.post(f"/complaints/{body['reference']}/answer",
                               {"answer": "checked and correct", "at": "13:20:00"})
        self.assertEqual(answered[0], 200)
        self.assertEqual(answered[1]["answered"], "13:20:00")

    def test_a_late_complaint_is_recorded_as_late(self):
        client = app()
        body = client.post("/complaints", {
            "entry": "ENT-0001", "about": "too late", "made": "13:40:00",
            "results": "13:00:00"})[1]
        self.assertFalse(body["in_time"])
        self.assertEqual(body["late_by"], 1500)

    def test_answering_a_complaint_that_is_not_there(self):
        self.assertEqual(app().post("/complaints/CMP-9999/answer", {"answer": "x"})[0], 400)

    def test_the_open_list(self):
        client = app()
        client.post("/complaints", {"entry": "ENT-0001", "about": "x", "results": "13:00:00"})
        self.assertEqual(client.get("/complaints")[1]["open"], ["CMP-0001"])


class Board(unittest.TestCase):
    def card(self, punches, card=205431, start="10:00:00", finish="10:21:12"):
        return {"card": card, "start": start, "finish": finish,
                "punches": [{"code": code, "at": at} for code, at in punches]}

    def test_the_board_is_provisional_while_anybody_is_out(self):
        client = app()
        client.post("/download", self.card([("101", "10:04:11"), ("102", "10:12:44")]))
        status, body = client.get("/board")
        self.assertEqual(status, 200)
        self.assertTrue(body["state"]["provisional"])
        self.assertEqual(body["state"]["still_out"], 1)
        self.assertIn("PROVISIONAL", body["text"])

    def test_the_board_is_final_once_everybody_is_in(self):
        client = app()
        client.post("/download", self.card([("101", "10:04:11"), ("102", "10:12:44")]))
        client.post("/download", self.card([("101", "10:06:00"), ("102", "10:14:00")],
                                           card=205999, start="10:02:00", finish="10:24:00"))
        body = client.get("/board")[1]
        self.assertFalse(body["state"]["provisional"])
        self.assertIn("FINAL", body["text"])
        self.assertEqual(body["leaders"][0]["leader"], "Okonkwo, Ada")

    def test_a_correction_shows_on_the_board(self):
        client = app()
        client.post("/download", self.card([("101", "10:04:11")]))
        self.assertNotIn("Okonkwo", client.get("/board")[1]["text"].split("still out")[0])
        client.post("/corrections", {"entry": "ENT-0001", "decision": "reinstate",
                                     "reason": "control was down"})
        self.assertIn("Okonkwo", client.get("/board")[1]["text"])

    def test_how_many_are_out_on_each_course(self):
        body = app().get("/board")[1]
        blue = next(row for row in body["still_out"] if row["course"] == "Blue")
        self.assertEqual(blue["still_out"], 2)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class Fixtures(unittest.TestCase):
    def test_a_season_that_was_never_set_up_answers_an_empty_calendar(self):
        status, body = app().get("/fixtures")
        self.assertEqual(status, 200)
        self.assertEqual(body["fixtures"], [])
        self.assertIsNone(body["next"])

    def test_a_fixture_is_added_and_read_back(self):
        client = app()
        status, body = client.post("/fixtures", {
            "name": "Longshaw", "date": "2026-11-15", "venue": "Longshaw",
            "opens": "2026-10-01", "closes": "2026-11-10", "capacity": 3})
        self.assertEqual(status, 201)
        self.assertEqual(body["room"], 3)
        self.assertEqual(client.get("/fixtures/Longshaw")[1]["venue"], "Longshaw")
        self.assertEqual(client.get("/fixtures/Padley")[0], 404)

    def test_the_calendar_says_what_each_fixture_is_doing(self):
        client = app()
        client.post("/fixtures", {"name": "Longshaw", "date": "2026-11-15",
                                  "opens": "2026-10-01", "closes": "2026-11-10"})
        body = client.get("/fixtures?on=2026-10-15")[1]
        self.assertEqual(body["fixtures"][0]["state"], "open")
        self.assertEqual(body["next"], "Longshaw")

    def test_entries_are_taken_and_refused(self):
        client = app()
        client.post("/fixtures", {"name": "Longshaw", "date": "2026-11-15",
                                  "opens": "2026-10-01", "closes": "2026-11-10", "capacity": 2})
        self.assertEqual(client.post("/fixtures/Longshaw/entries",
                                     {"on": "2026-10-15", "count": 2})[1]["entered"], 2)
        self.assertEqual(client.post("/fixtures/Longshaw/entries", {"on": "2026-10-15"})[0], 409)
        self.assertEqual(client.post("/fixtures/Longshaw/entries", {"on": "2026-09-01"})[0], 409)

    def test_cancelling_a_fixture(self):
        client = app()
        client.post("/fixtures", {"name": "Longshaw", "date": "2026-11-15",
                                  "opens": "2026-10-01", "closes": "2026-11-10"})
        body = client.delete("/fixtures/Longshaw", {"reason": "snow"})[1]
        self.assertTrue(body["cancelled"])
        self.assertEqual(body["note"], "snow")
        self.assertIsNone(client.get("/fixtures?on=2026-10-15")[1]["next"])


class Persistence(unittest.TestCase):
    def test_a_correction_reaches_the_file(self):
        import tempfile
        from pathlib import Path

        from reentrant.store.jsonstore import EventFile, load, save

        path = Path(tempfile.mkdtemp()) / "event.json"
        save(path, EventFile(event=build()))
        context = Context.from_file(load(path), path)
        client = test_app(context)

        client.post("/corrections", {"entry": "ENT-0001", "decision": "reinstate",
                                     "reason": "control was down", "by": "organiser"})
        reopened = load(path)
        self.assertEqual(len(reopened.corrections), 1)
        self.assertEqual(reopened.corrections.corrections[0].entry, "ENT-0001")
