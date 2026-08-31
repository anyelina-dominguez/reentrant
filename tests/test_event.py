from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.courses.control import Control, ControlSet
from reentrant.courses.course import Course, CourseSet
from reentrant.entries.competitor import Competitor, Entry, EntryList
from reentrant.errors import NotFoundError, RuleError, ValidationError
from reentrant.event.download import outstanding, process, process_all, results_from
from reentrant.event.event import Event, parse_zero, summary
from reentrant.geo.grid import parse as grid
from reentrant.timing.punch import read_from_pairs
from reentrant.util.times import parse_time_of_day

PLACES = {"S1": 12000, "101": 12300, "102": 12800, "103": 13400, "F1": 12100}


def build(*, class_courses=None, entries=None) -> Event:
    controls = ControlSet()
    for code, east in PLACES.items():
        controls.add(Control(code, grid(f"SK {east} 67000")))
    courses = CourseSet()
    courses.add(Course("Blue", ["S1", "101", "102", "F1"]))
    courses.add(Course("Green", ["S1", "101", "103", "F1"]))
    listed = EntryList()
    for entry in entries or []:
        listed.add(entry)
    return Event("Club fixture", "2026-05-09", controls, courses, listed,
                 class_courses if class_courses is not None else {"W45": "Blue", "M21": "Green"})


def entry(reference="ENT-0001", card=205431, class_code="W45", course="Blue",
          start="10:00:00", surname="Okonkwo", forename="Ada", birth_year=1981, sex="W"):
    return Entry(reference, Competitor(surname, forename, "DPO", birth_year, sex),
                 course, class_code, card,
                 start_seconds=None if start is None else parse_time_of_day(start))


class Events(unittest.TestCase):
    def test_the_basics(self):
        event = build()
        self.assertEqual(event.year, 2026)
        self.assertEqual(event.course_for_class("w45"), "Blue")
        self.assertEqual(event.classes_on("Blue"), ["W45"])
        self.assertRaises(NotFoundError, event.course_for_class, "M40")
        self.assertRaises(ValidationError, Event, "x", "9 May 2026")

    def test_classes_can_be_pointed_at_another_course(self):
        event = build()
        event.set_class_course("W50", "Blue")
        self.assertEqual(sorted(event.classes_on("Blue")), ["W45", "W50"])
        self.assertRaises(NotFoundError, event.set_class_course, "W55", "Red")

    def test_merging_classes_on_the_morning(self):
        event = build()
        event.set_class_course("W75", "Green")
        moved = event.merge_classes("W45", "W75")
        self.assertEqual(moved, ["W75"])
        self.assertEqual(event.course_for_class("W75"), "Blue")

    def test_a_ready_event_has_nothing_to_say(self):
        self.assertEqual(build(entries=[entry()]).check_ready(), [])
        build(entries=[entry()]).require_ready()

    def test_a_course_using_a_control_that_is_not_out(self):
        event = build()
        event.courses.put(Course("Red", ["S1", "199", "F1"]))
        problems = event.check_ready()
        self.assertTrue(any("not out" in line for line in problems))
        self.assertRaises(RuleError, event.require_ready)

    def test_a_class_pointed_at_a_course_that_does_not_exist(self):
        event = build(class_courses={"W45": "Red"})
        self.assertTrue(any("which does not exist" in line for line in event.check_ready()))

    def test_an_entry_in_a_class_that_is_not_running(self):
        event = build(entries=[entry(class_code="W60")])
        self.assertTrue(any("not running a course" in line for line in event.check_ready()))

    def test_an_entry_in_a_class_the_competitor_may_not_run(self):
        event = build(class_courses={"W50": "Blue"}, entries=[entry(class_code="W50")])
        self.assertTrue(any("may not run" in line for line in event.check_ready()))

    def test_controls_too_close_stop_the_event(self):
        event = build()
        event.controls.put(Control("104", grid("SK 12305 67000")))
        event.courses.put(Course("Red", ["S1", "104", "F1"]))
        self.assertTrue(any("m apart" in line for line in event.check_ready()))

    def test_summary_and_zero(self):
        event = build(entries=[entry(), entry("ENT-0002", 205999, "M21", "Green")])
        told = summary(event)
        self.assertEqual(told["entries"], 2)
        self.assertEqual(told["by_course"], [{"course": "Blue", "entries": 1},
                                             {"course": "Green", "entries": 1}])
        self.assertEqual(parse_zero("10:00:00"), 36000)

    def test_an_event_round_trips(self):
        event = build(entries=[entry()])
        back = Event.from_dict(event.to_dict())
        self.assertEqual(back.to_dict(), event.to_dict())
        self.assertEqual(back.course_for_class("W45"), "Blue")


class Downloads(unittest.TestCase):
    def setUp(self):
        self.event = build(entries=[entry(), entry("ENT-0002", 205999, "M21", "Green", "10:02:00",
                                                  "Bo", "Sam", 1990, "M")])

    def test_a_clean_run(self):
        read = read_from_pairs(205431, [("101", "10:04:11"), ("102", "10:12:44")], finish="10:21:12")
        download = process(self.event, read)
        self.assertTrue(download.ok)
        self.assertEqual(download.seconds, 1272)
        self.assertEqual(download.course, "Blue")
        self.assertEqual(len(download.splits), 3)
        self.assertIn("Okonkwo, Ada", download.slip())
        self.assertEqual(download.to_result().outcome, "ok")

    def test_a_card_nobody_entered(self):
        download = process(self.event, read_from_pairs(999999, []))
        self.assertFalse(download.ok)
        self.assertEqual(download.problem, "that card is not entered")
        self.assertIsNone(download.to_result())
        self.assertIn("999999", download.slip())

    def test_a_mispunch_says_which_control(self):
        read = read_from_pairs(205431, [("101", "10:04:11")], finish="10:21:12")
        download = process(self.event, read)
        self.assertFalse(download.ok)
        self.assertEqual(download.problem, "missing control 2 (102)")
        # The time is still worked out -- the results list decides whether to
        # show it, and a reinstatement needs it to exist.
        self.assertEqual(download.seconds, 1272)
        self.assertFalse(download.to_result().placed)
        self.assertEqual(download.to_result().outcome, "mispunch")

    def test_the_drawn_start_is_used_when_the_card_has_none(self):
        read = read_from_pairs(205431, [("101", "10:04:11"), ("102", "10:12:44")],
                               start=None, finish="10:21:12")
        download = process(self.event, read)
        self.assertTrue(download.ok)
        self.assertEqual(download.start_seconds, parse_time_of_day("10:00:00"))

    def test_a_start_punch_beats_the_drawn_time(self):
        read = read_from_pairs(205431, [("101", "10:06:11"), ("102", "10:12:44")],
                               start="10:03:00", finish="10:21:12")
        download = process(self.event, read)
        self.assertEqual(download.start_seconds, parse_time_of_day("10:03:00"))
        self.assertEqual(download.seconds, 1092)

    def test_a_runner_with_no_start_at_all(self):
        event = build(entries=[entry(start=None)])
        read = read_from_pairs(205431, [("101", "10:04:11"), ("102", "10:12:44")],
                               start=None, finish="10:21:12")
        download = process(event, read)
        self.assertFalse(download.ok)
        self.assertEqual(download.problem, "no start time")
        self.assertEqual(download.splits, [])

    def test_an_entry_whose_class_runs_nothing(self):
        event = build(class_courses={}, entries=[Entry("ENT-0001",
                      Competitor("Okonkwo", "Ada", "DPO", 1981, "W"), "", "W45", 205431)])
        download = process(event, read_from_pairs(205431, []))
        self.assertIn("not running a course", download.problem)

    def test_the_whole_log_and_who_is_still_out(self):
        reads = [read_from_pairs(205431, [("101", "10:04:11"), ("102", "10:12:44")], finish="10:21:12")]
        downloads = process_all(self.event, reads)
        self.assertEqual(len(downloads), 1)
        self.assertEqual([e.reference for e in outstanding(self.event, downloads)], ["ENT-0002"])
        rows = results_from(self.event, downloads)
        self.assertEqual({row.entry: row.outcome for row in rows},
                         {"ENT-0001": "ok", "ENT-0002": "dns"})


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class Summary(unittest.TestCase):
    def test_entries_that_name_only_a_class_are_counted_on_their_course(self):
        listed = EntryList()
        listed.add(Entry("ENT-0001", Competitor("Okonkwo", "Ada", "DPO", 1981, "W"),
                         "", "W45", 205431))
        listed.add(Entry("ENT-0002", Competitor("Bo", "Sam", "SYO", 1990, "M"),
                         "", "M21", 205999))
        event = build()
        event.entries = listed
        told = summary(event)
        self.assertEqual(told["by_course"],
                         [{"course": "Blue", "entries": 1}, {"course": "Green", "entries": 1}])

    def test_an_entry_whose_class_runs_nothing_falls_back_to_its_own_course(self):
        listed = EntryList()
        listed.add(Entry("ENT-0001", Competitor("Okonkwo", "Ada", "DPO", 1981, "W"),
                         "Blue", "W80", 205431))
        event = build()
        event.entries = listed
        self.assertEqual(summary(event)["by_course"],
                         [{"course": "Blue", "entries": 1}, {"course": "Green", "entries": 0}])


class Outstanding(unittest.TestCase):
    def test_who_is_still_out_on_one_course(self):
        event = build(entries=[
            entry("ENT-0001", 205431, "W45", "Blue"),
            entry("ENT-0002", 205999, "M21", "Green", "10:02:00", "Bo", "Sam", 1990, "M"),
        ])
        self.assertEqual([e.reference for e in outstanding(event, [])], ["ENT-0001", "ENT-0002"])
        self.assertEqual([e.reference for e in outstanding(event, [], course="Blue")],
                         ["ENT-0001"])
        self.assertEqual(outstanding(event, [], course="Yellow"), [])
