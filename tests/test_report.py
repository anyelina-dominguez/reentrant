from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.entries.competitor import Competitor, Entry, EntryList
from reentrant.event.event import Event
from reentrant.event.report import build_report, render_report
from reentrant.results.classify import Result
from reentrant.results.protest import Complaint, ComplaintBook
from reentrant.util.times import parse_time_of_day as at


def event() -> Event:
    entries = EntryList()
    for index in range(1, 6):
        entries.add(Entry(f"ENT-{index:04d}", Competitor(f"N{index}", "F", "DPO", 1990, "M"),
                          "Blue", "M21", 200_000 + index))
    return Event("Club fixture", "2026-05-09", entries=entries, class_courses={"M21": "Blue"})


def results(mispunched=1, absent=0):
    rows = [Result(f"E{index}", f"Runner {index}", "DPO", "M21", "Blue", 2100 + index * 120)
            for index in range(4)]
    for index in range(mispunched):
        rows.append(Result(f"M{index}", f"Lost {index}", "DPO", "M21", "Blue", 2400, "mispunch"))
    for index in range(absent):
        rows.append(Result(f"A{index}", f"Absent {index}", "DPO", "M21", "Blue", None, "dns"))
    return rows


class Reports(unittest.TestCase):
    def test_the_three_numbers(self):
        report = build_report(event(), results())
        self.assertEqual(report.entries, 5)
        self.assertEqual(report.starters, 5)
        self.assertEqual(report.finishers, 4)
        self.assertEqual(report.completion, 0.8)

    def test_non_starters_are_not_counted_as_starters(self):
        report = build_report(event(), results(absent=2))
        self.assertEqual(report.starters, 5)
        self.assertEqual(report.outcomes["dns"], 2)

    def test_the_mispunch_rate(self):
        self.assertEqual(build_report(event(), results(mispunched=1)).mispunch_rate, 0.2)
        self.assertEqual(build_report(event(), results(mispunched=0)).mispunch_rate, 0.0)

    def test_an_event_where_nobody_started(self):
        report = build_report(event(), [])
        self.assertEqual(report.starters, 0)
        self.assertEqual(report.completion, 0.0)
        self.assertEqual(report.mispunch_rate, 0.0)

    def test_the_courses_carry_their_verdicts(self):
        report = build_report(event(), results())
        self.assertEqual(len(report.courses), 1)
        self.assertEqual(report.courses[0].course, "Blue")
        self.assertEqual(report.courses[0].verdict, "about right")

    def test_complaints_are_counted(self):
        book = ComplaintBook()
        one = Complaint("CMP-0001", "E1", "control 102", at("13:05:00"), at("13:00:00"))
        one.answer_it("checked", at("13:20:00"))
        one.escalate(at("13:25:00"))
        one.decide("upheld", "it was down", ["A", "B", "C"])
        book.add(one)
        book.add(Complaint("CMP-0002", "E2", "another", at("13:06:00"), at("13:00:00")))
        report = build_report(event(), results(), complaints=book)
        self.assertEqual(report.complaints, 2)
        self.assertEqual(report.upheld, 1)

    def test_the_rendered_report(self):
        report = build_report(event(), results(),
                              notes=["the download queue reached eleven people at 13:10"])
        text = render_report(report)
        self.assertIn("Club fixture -- 2026-05-09", text)
        self.assertIn("5 started, 4 finished", text)
        self.assertIn("mispunch rate 20%", text)
        self.assertIn("about right", text)
        self.assertIn("download queue", text)

    def test_a_report_with_nothing_to_say_still_renders(self):
        text = render_report(build_report(event(), []))
        self.assertIn("Club fixture", text)
        self.assertNotIn("notes", text)

    def test_the_report_serialises(self):
        told = build_report(event(), results()).to_dict()
        self.assertEqual(told["finishers"], 4)
        self.assertEqual(told["courses"][0]["course"], "Blue")
        self.assertEqual(told["outcomes"]["ok"], 4)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
