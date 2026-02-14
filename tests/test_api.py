from __future__ import annotations

import json
import threading
import unittest
import urllib.request
from urllib.error import HTTPError

from . import context as _context  # noqa: F401

from reentrant.api.app import build_router, paths
from reentrant.api.context import Clock, Context
from reentrant.api.http import serve
from reentrant.api.router import Router
from reentrant.api.testapp import test_app
from reentrant.courses.control import Control, ControlSet
from reentrant.courses.course import Course, CourseSet
from reentrant.entries.competitor import Competitor, Entry, EntryList
from reentrant.errors import NotFoundError, ValidationError
from reentrant.event.event import Event
from reentrant.geo.grid import parse as grid

PLACES = {"S1": 12000, "101": 12300, "102": 12800, "103": 13400, "F1": 12100}


def build_event() -> Event:
    controls = ControlSet()
    for code, east in PLACES.items():
        controls.add(Control(code, grid(f"SK {east} 67000"), height=200.0))
    courses = CourseSet()
    courses.add(Course("Blue", ["S1", "101", "102", "F1"]))
    courses.add(Course("Green", ["S1", "101", "103", "F1"]))
    entries = EntryList()
    entries.add(Entry("ENT-0001", Competitor("Okonkwo", "Ada", "DPO", 1981, "W"),
                      "Blue", "W45", 205431, start_seconds=36000))
    entries.add(Entry("ENT-0002", Competitor("Bo", "Sam", "SYO", 1990, "M"),
                      "Green", "M21", 205999, start_seconds=36120))
    return Event("Club fixture", "2026-05-09", controls, courses, entries,
                 {"W45": "Blue", "M21": "Green"}, venue="Longshaw")


def app():
    return test_app(Context(event=build_event(), clock=Clock.stopped_at(36000)))


class Event_(unittest.TestCase):
    def test_health_and_summary(self):
        client = app()
        self.assertEqual(client.get("/health"), (200, {"ok": True}))
        status, body = client.get("/event")
        self.assertEqual(status, 200)
        self.assertEqual(body["name"], "Club fixture")
        self.assertEqual(body["entries"], 2)

    def test_the_check_reports_readiness_and_the_planner_notes(self):
        status, body = client_body = app().get("/event/check")
        self.assertEqual(status, 200)
        self.assertTrue(body["ready"])
        self.assertEqual(body["problems"], [])
        self.assertIn("note_counts", body)

    def test_controls_are_listed_and_added(self):
        client = app()
        self.assertEqual(client.get("/controls")[1]["count"], 5)
        status, body = client.post("/controls", {"code": "104", "position": "SK 14000 67000"})
        self.assertEqual(status, 201)
        self.assertEqual(body["code"], "104")
        self.assertEqual(client.get("/controls")[1]["count"], 6)
        self.assertEqual(client.get("/controls/104")[1]["position"], "SK 14000 67000")
        self.assertEqual(client.get("/controls/199")[0], 404)

    def test_a_control_too_close_to_another_is_still_added_but_the_check_complains(self):
        client = app()
        client.post("/controls", {"code": "105", "position": "SK 12305 67000"})
        self.assertFalse(client.get("/event/check")[1]["ready"])

    def test_courses_carry_their_length_and_classes(self):
        client = app()
        status, body = client.get("/courses")
        self.assertEqual(status, 200)
        blue = next(row for row in body["courses"] if row["name"] == "Blue")
        self.assertEqual(blue["controls"], 2)
        self.assertGreater(blue["metres"], 0)
        self.assertEqual(blue["classes"], ["W45"])

    def test_one_course_comes_with_its_legs_and_descriptions(self):
        status, body = app().get("/courses/Blue")
        self.assertEqual(status, 200)
        self.assertEqual(len(body["legs"]), 3)
        self.assertEqual(body["legs"][0]["from"], "S1")
        self.assertEqual(body["descriptions"][0], "  S  start")

    def test_a_course_using_a_control_that_is_not_out_is_refused(self):
        client = app()
        status, body = client.post("/courses", {"name": "Red", "codes": ["S1", "199", "F1"]})
        self.assertEqual(status, 409)
        self.assertEqual(body["error"], "RuleError")

    def test_classes_are_pointed_at_courses(self):
        client = app()
        self.assertEqual(client.put("/classes/W50", {"course": "Blue"})[0], 200)
        self.assertIn({"class": "W50", "course": "Blue"}, client.get("/classes")[1]["classes"])
        self.assertEqual(client.put("/classes/W55", {"course": "Red"})[0], 404)


class Entries(unittest.TestCase):
    def test_listing_and_filtering(self):
        client = app()
        self.assertEqual(client.get("/entries")[1]["count"], 2)
        self.assertEqual(client.get("/entries?course=Blue")[1]["count"], 1)
        self.assertEqual(client.get("/entries?class=m21")[1]["count"], 1)
        self.assertEqual(client.get("/entries?club=DPO")[1]["count"], 1)

    def test_an_entry_is_added_with_a_minted_reference(self):
        client = app()
        status, body = client.post("/entries", {
            "surname": "Cai", "forename": "Jo", "club": "HALO",
            "class": "M21", "card": 300111, "birth_year": 2000, "sex": "M",
        })
        self.assertEqual(status, 201)
        self.assertEqual(body["reference"], "ENT-0003")
        self.assertEqual(body["running"], "Green", "the course comes from the class")

    def test_one_card_one_run_over_http(self):
        client = app()
        status, body = client.post("/entries", {
            "surname": "Cai", "forename": "Jo", "class": "M21", "card": 205431})
        self.assertEqual(status, 409)
        self.assertEqual(body["error"], "ConflictError")

    def test_lookup_by_reference_and_by_card(self):
        client = app()
        self.assertEqual(client.get("/entries/ENT-0001")[1]["name"], "Okonkwo, Ada")
        self.assertEqual(client.get("/cards/205999")[1]["reference"], "ENT-0002")
        self.assertEqual(client.get("/cards/999999")[0], 404)

    def test_changing_and_removing_an_entry(self):
        client = app()
        status, body = client.patch("/entries/ENT-0001", {"card": 300222})
        self.assertEqual(status, 200)
        self.assertEqual(body["card"], 300222)
        self.assertEqual(client.get("/cards/300222")[1]["reference"], "ENT-0001")
        self.assertEqual(client.delete("/entries/ENT-0001")[1], {"removed": "ENT-0001"})
        self.assertEqual(client.get("/entries")[1]["count"], 1)


class Starts(unittest.TestCase):
    def test_the_draw_gives_everybody_a_time(self):
        client = app()
        status, body = client.post("/starts/draw", {"first": "10:30:00", "interval": 120})
        self.assertEqual(status, 201)
        self.assertEqual(len(body["starts"]), 2)
        self.assertEqual(body["starts"][0]["time"], "10:30:00")
        listed = client.get("/starts")[1]
        self.assertEqual(listed["count"], 2)

    def test_a_draw_with_nobody_to_draw(self):
        empty = test_app(Context(event=Event("Empty", "2026-05-09")))
        self.assertEqual(empty.post("/starts/draw", {})[0], 400)


class Downloads(unittest.TestCase):
    def card(self, punches, card=205431, start="10:00:00", finish="10:21:12"):
        return {"card": card, "start": start, "finish": finish,
                "punches": [{"code": code, "at": at} for code, at in punches]}

    def test_a_clean_run_comes_back_with_its_splits_and_slip(self):
        client = app()
        status, body = client.post("/download", self.card(
            [("101", "10:04:11"), ("102", "10:12:44")]))
        self.assertEqual(status, 201)
        self.assertTrue(body["ok"])
        self.assertEqual(body["time"], "21:12")
        self.assertEqual(len(body["splits"]), 3)
        self.assertIn("Okonkwo, Ada", body["slip"])

    def test_a_mispunch_says_which_control(self):
        client = app()
        status, body = client.post("/download", self.card([("101", "10:04:11")]))
        self.assertEqual(status, 201)
        self.assertFalse(body["ok"])
        self.assertEqual(body["problem"], "missing control 2 (102)")

    def test_a_card_nobody_entered(self):
        client = app()
        status, body = client.post("/download", self.card([], card=999999))
        self.assertFalse(body["ok"])
        self.assertEqual(body["problem"], "that card is not entered")

    def test_a_body_that_is_not_a_card(self):
        client = app()
        self.assertEqual(client.post("/download", {"card": 0})[0], 400)
        self.assertEqual(client.post("/download", {"card": 205431,
                                                   "punches": [{"code": "101", "at": "half ten"}]})[0], 400)

    def test_the_log_and_who_is_still_out(self):
        client = app()
        client.post("/download", self.card([("101", "10:04:11"), ("102", "10:12:44")]))
        self.assertEqual(client.get("/downloads")[1]["count"], 1)
        still_out = client.get("/outstanding")[1]
        self.assertEqual(still_out["count"], 1)
        self.assertEqual(still_out["entries"][0]["entry"], "ENT-0002")

    def test_the_results_appear_as_cards_are_read(self):
        client = app()
        client.post("/download", self.card([("101", "10:04:11"), ("102", "10:12:44")]))
        status, body = client.get("/results")
        self.assertEqual(status, 200)
        self.assertEqual(body["by"], "class")
        w45 = next(block for block in body["blocks"] if block["name"] == "W45")
        self.assertEqual(w45["results"][0]["place"], 1)
        self.assertEqual(body["counts"], {"dns": 1, "ok": 1})

    def test_results_by_course_and_by_class(self):
        client = app()
        client.post("/download", self.card([("101", "10:04:11"), ("102", "10:12:44")]))
        self.assertEqual([block["name"] for block in client.get("/results?by=course")[1]["blocks"]],
                         ["Blue", "Green"])
        self.assertEqual(client.get("/results/classes/w45")[1]["results"][0]["place"], 1)
        self.assertEqual(client.get("/results/classes/M60")[1]["results"], [])

    def test_the_splits_for_a_course(self):
        client = app()
        client.post("/download", self.card([("101", "10:04:11"), ("102", "10:12:44")]))
        status, body = client.get("/splits/Blue")
        self.assertEqual(status, 200)
        self.assertEqual(body["course"], "Blue")
        self.assertEqual(len(body["runners"]), 1)
        self.assertEqual(body["runners"][0]["name"], "Okonkwo, Ada")
        self.assertEqual(client.get("/splits/Red")[0], 404)


class OverASocket(unittest.TestCase):
    def test_the_same_handlers_answer_on_a_real_port(self):
        server = serve(build_router(), Context(event=build_event()), port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            port = server.server_address[1]
            base = f"http://127.0.0.1:{port}"

            with urllib.request.urlopen(f"{base}/health") as response:
                self.assertEqual(response.status, 200)
                self.assertEqual(json.load(response), {"ok": True})

            with urllib.request.urlopen(f"{base}/entries?course=Blue") as response:
                self.assertEqual(json.load(response)["count"], 1)

            posted = urllib.request.Request(
                f"{base}/entries",
                data=json.dumps({"surname": "Cai", "forename": "Jo",
                                 "class": "M21", "card": 300111}).encode(),
                headers={"content-type": "application/json"}, method="POST")
            with urllib.request.urlopen(posted) as response:
                self.assertEqual(response.status, 201)

            with self.assertRaises(HTTPError) as caught:
                urllib.request.urlopen(f"{base}/nothing")
            self.assertEqual(caught.exception.code, 404)

            broken = urllib.request.Request(f"{base}/entries", data=b"{ not json",
                                            headers={"content-type": "application/json"},
                                            method="POST")
            with self.assertRaises(HTTPError) as caught:
                urllib.request.urlopen(broken)
            self.assertEqual(caught.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
