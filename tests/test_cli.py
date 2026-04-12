from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from . import context  # noqa: F401

from reentrant.cli.main import USAGE, run
from reentrant.cli.options import parse_args
from reentrant.errors import ValidationError
from reentrant.store.jsonstore import load, save
from reentrant.courses.control import Control
from reentrant.courses.course import Course
from reentrant.geo.grid import parse as grid

ENTRIES_CSV = "\n".join([
    "Surname,First Name,Club,Class,SI Card,Year of Birth,Gender",
    "Okonkwo,Ada,DPO,W45,205431,1981,W",
    "Bergstrom,Nils,SYO,M21,205999,1990,M",
    "Cai,Jo,HALO,M21,300111,2000,M",
    "Broken,Row,DPO,ZZ99,300222,2000,M",
    "",
])


def cards(path: Path) -> Path:
    log = [
        {"card": 205431, "start": "10:00:00", "finish": "10:21:12",
         "punches": [{"code": "101", "at": "10:04:11"}, {"code": "102", "at": "10:12:44"}]},
        {"card": 205999, "start": "10:02:00", "finish": "10:28:00",
         "punches": [{"code": "101", "at": "10:07:00"}, {"code": "103", "at": "10:18:00"}]},
        {"card": 300111, "start": "10:04:00", "finish": "10:30:00",
         "punches": [{"code": "101", "at": "10:09:00"}]},
    ]
    path.write_text(json.dumps(log), encoding="utf-8")
    return path


class Options(unittest.TestCase):
    def test_the_whole_grammar(self):
        parsed = parse_args(["results", "--by", "course", "--csv", "--first=10:00:00"],
                            flags=["csv"])
        self.assertEqual(parsed.positional, ["results"])
        self.assertEqual(parsed.value("by"), "course")
        self.assertTrue(parsed.flag("csv"))
        self.assertEqual(parsed.value("first"), "10:00:00")

    def test_an_option_with_no_value_is_a_flag(self):
        self.assertTrue(parse_args(["--quiet"]).flag("quiet"))
        self.assertTrue(parse_args(["--quiet", "--other"]).flag("quiet"))
        self.assertEqual(parse_args(["--", "--not-an-option"]).positional, ["--not-an-option"])

    def test_required_and_numeric_values(self):
        parsed = parse_args(["--interval", "120"])
        self.assertEqual(parsed.number("interval"), 120)
        self.assertEqual(parsed.number("missing", 60), 60)
        self.assertEqual(parsed.require("interval"), "120")
        self.assertRaises(ValidationError, parsed.require, "nothing")
        self.assertRaises(ValidationError, parse_args(["--interval", "soon"]).number, "interval")


class Walkthrough(unittest.TestCase):
    """A whole event, through the command line and nothing else."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())
        self.path = self.directory / "event.json"
        self.event = ["--event", str(self.path)]

    def build(self):
        self.assertEqual(run(["new", "Club fixture", "2026-05-09"] + self.event).status, 0)
        held = load(self.path)
        for code, east in {"S1": 12000, "101": 12300, "102": 12800, "103": 13400, "F1": 12100}.items():
            held.event.controls.add(Control(code, grid(f"SK {east} 67000"), height=200.0))
        held.event.courses.add(Course("Blue", ["S1", "101", "102", "F1"]))
        held.event.courses.add(Course("Green", ["S1", "101", "103", "F1"]))
        held.event.class_courses.update({"W45": "Blue", "M21": "Green"})
        save(self.path, held)

    def test_a_new_event_is_created_once(self):
        self.assertEqual(run(["new", "Club fixture", "2026-05-09"] + self.event).status, 0)
        again = run(["new", "Another", "2026-05-10"] + self.event)
        self.assertEqual(again.status, 1)
        self.assertIn("already an event", again.lines[0])

    def test_new_needs_a_name_and_a_date(self):
        self.assertEqual(run(["new"] + self.event).status, 1)

    def test_a_command_before_there_is_a_file(self):
        outcome = run(["show"] + self.event)
        self.assertEqual(outcome.status, 1)
        self.assertIn("no event file", outcome.lines[0])

    def test_the_whole_way_through(self):
        self.build()

        source = self.directory / "entries.csv"
        source.write_text(ENTRIES_CSV, encoding="utf-8")
        imported = run(["import", "--file", str(source)] + self.event)
        self.assertEqual(imported.status, 1, "one row is broken")
        self.assertIn("added 3, rejected 1", "\n".join(imported.lines))

        shown = run(["show"] + self.event)
        self.assertIn("3 entries", "\n".join(shown.lines))

        checked = run(["check"] + self.event)
        self.assertEqual(checked.status, 0, "\n".join(checked.lines))

        drawn = run(["draw", "--first", "10:00:00", "--interval", "120"] + self.event)
        self.assertEqual(drawn.status, 0)
        self.assertIn("start list", "\n".join(drawn.lines))

        listed = run(["starts"] + self.event)
        self.assertEqual(listed.status, 0)
        self.assertIn("3 starters", "\n".join(listed.lines))

        log = cards(self.directory / "cards.json")
        read = run(["download", "--file", str(log)] + self.event)
        self.assertEqual(read.status, 0)
        self.assertIn("3 cards read", "\n".join(read.lines))

        printed = run(["results"] + self.event)
        self.assertEqual(printed.status, 0)
        text = "\n".join(printed.lines)
        self.assertIn("Okonkwo, Ada", text)
        self.assertIn("mispunch", text, "Cai, Jo never punched 103")

        by_course = run(["results", "--by", "course"] + self.event)
        self.assertIn("Blue", "\n".join(by_course.lines))

        as_csv = run(["results", "--csv"] + self.event)
        self.assertEqual(as_csv.lines[0], "place,name,club,class,course,time,seconds,outcome")

        split = run(["splits", "--course", "Green"] + self.event)
        self.assertEqual(split.status, 0)
        self.assertIn("Bergstrom, Nils", "\n".join(split.lines))

        back_out = run(["export-entries"] + self.event)
        self.assertEqual(back_out.lines[0].split(",")[0], "reference")
        self.assertEqual(len(back_out.lines), 4)

    def test_results_before_anything_is_downloaded(self):
        self.build()
        self.assertEqual(run(["results"] + self.event).status, 1)
        self.assertEqual(run(["starts"] + self.event).status, 1)
        self.assertEqual(run(["draw"] + self.event).status, 1)

    def test_splits_for_a_course_nobody_ran(self):
        self.build()
        outcome = run(["splits", "--course", "Blue"] + self.event)
        self.assertEqual(outcome.status, 1)
        self.assertIn("nobody has completed", outcome.lines[0])
        self.assertEqual(run(["splits", "--course", "Red"] + self.event).status, 1)

    def test_a_check_that_finds_something(self):
        self.build()
        held = load(self.path)
        held.event.courses.put(Course("Red", ["S1", "199", "F1"]))
        save(self.path, held)
        outcome = run(["check"] + self.event)
        self.assertEqual(outcome.status, 1)
        self.assertIn("not out", "\n".join(outcome.lines))

    def test_an_import_file_that_is_not_there(self):
        self.build()
        outcome = run(["import", "--file", str(self.directory / "nope.csv")] + self.event)
        self.assertEqual(outcome.status, 2)
        self.assertIn("FileNotFoundError", outcome.lines[0])

    def test_an_import_with_no_name_column(self):
        self.build()
        source = self.directory / "bad.csv"
        source.write_text("club,card\nDPO,205431\n", encoding="utf-8")
        outcome = run(["import", "--file", str(source)] + self.event)
        self.assertEqual(outcome.status, 1)
        self.assertIn("no column for", outcome.lines[0])


class Usage(unittest.TestCase):
    def test_no_command_prints_the_usage_and_fails(self):
        outcome = run([])
        self.assertEqual(outcome.status, 1)
        self.assertEqual(outcome.lines, USAGE)

    def test_help_prints_the_usage_and_succeeds(self):
        self.assertEqual(run(["show", "--help"]).status, 0)

    def test_an_unknown_command(self):
        outcome = run(["fly"])
        self.assertEqual(outcome.status, 1)
        self.assertIn("no such command: fly", outcome.lines[0])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()


class MoreCommands(unittest.TestCase):
    """The commands added once the day had been run a few times."""

    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())
        self.path = self.directory / "event.json"
        self.event = ["--event", str(self.path)]
        run(["new", "Club fixture", "2026-05-09"] + self.event)
        held = load(self.path)
        for code, east in {"S1": 12000, "101": 12300, "102": 12800, "F1": 12100}.items():
            held.event.controls.add(Control(code, grid(f"SK {east} 67000"), height=200.0))
        held.event.courses.add(Course("Blue", ["S1", "101", "102", "F1"]))
        held.event.class_courses["M21"] = "Blue"
        save(self.path, held)

    def test_the_description_sheets(self):
        outcome = run(["describe"] + self.event)
        self.assertEqual(outcome.status, 0)
        text = "\n".join(outcome.lines)
        self.assertIn("Blue", text)
        self.assertIn("start", text)
        self.assertIn("finish", text)

    def test_one_course_at_a_time(self):
        self.assertEqual(run(["describe", "--course", "Blue"] + self.event).status, 0)
        self.assertEqual(run(["describe", "--course", "Red"] + self.event).status, 1)

    def test_the_collectors_list(self):
        outcome = run(["collect"] + self.event)
        self.assertEqual(outcome.status, 0)
        text = "\n".join(outcome.lines)
        self.assertIn("101", text)
        self.assertIn("2 controls to collect", text)
        self.assertNotIn("S1", text, "the start is not collected like a control")

    def test_the_board_needs_results(self):
        outcome = run(["board"] + self.event)
        self.assertEqual(outcome.status, 1)
        self.assertIn("nothing has been downloaded", outcome.lines[0])

    def test_the_board_once_somebody_has_run(self):
        source = self.directory / "entries.csv"
        source.write_text("surname,first name,class,si card\nOkonkwo,Ada,M21,205431\n",
                          encoding="utf-8")
        run(["import", "--file", str(source)] + self.event)
        run(["draw", "--first", "10:00:00"] + self.event)
        log = self.directory / "cards.json"
        log.write_text(json.dumps([{
            "card": 205431, "start": "10:00:00", "finish": "10:21:12",
            "punches": [{"code": "101", "at": "10:04:11"}, {"code": "102", "at": "10:12:44"}],
        }]), encoding="utf-8")
        run(["download", "--file", str(log)] + self.event)

        outcome = run(["board", "--at", "13:30:00"] + self.event)
        self.assertEqual(outcome.status, 0)
        text = "\n".join(outcome.lines)
        self.assertIn("printed 13:30:00", text)
        self.assertIn("Okonkwo, Ada", text)
        self.assertIn("FINAL", text)

    def test_serve_binds_a_port_and_answers(self):
        outcome = run(["serve", "--port", "0"] + self.event)
        self.assertEqual(outcome.status, 0)
        self.assertIn("listening on http://", outcome.lines[0])
        server = outcome.server
        try:
            import threading
            import urllib.request

            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            port = server.server_address[1]
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/event") as response:
                self.assertEqual(json.load(response)["name"], "Club fixture")
        finally:
            server.shutdown()
            server.server_close()
