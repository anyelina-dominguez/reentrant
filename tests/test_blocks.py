from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.entries.competitor import Competitor, Entry
from reentrant.errors import ConflictError, RuleError, ValidationError
from reentrant.starts.blocks import (
    GRACE_SECONDS, Block, LateStart, StartPlan, assign_block_times, late_runners,
)
from reentrant.util.times import parse_time_of_day as at


def entry(reference, class_code="M21", start=None):
    return Entry(reference, Competitor(f"N{reference}", "F"), "", class_code,
                 200_000 + int(reference[-4:]),
                 start_seconds=None if start is None else at(start))


class Blocks(unittest.TestCase):
    def test_a_block_is_a_window_and_a_set_of_classes(self):
        block = Block("juniors", at("10:00:00"), at("10:30:00"), ["m14", "W14"], 120)
        self.assertEqual(block.classes, ["M14", "W14"])
        self.assertEqual(block.slots, 16)
        self.assertTrue(block.holds("M14"))
        self.assertFalse(block.holds("M21"))
        self.assertTrue(block.contains(at("10:15:00")))
        self.assertFalse(block.contains(at("10:31:00")))

    def test_a_block_cannot_end_before_it_starts(self):
        self.assertRaises(ValidationError, Block, "x", at("10:30:00"), at("10:00:00"))

    def test_the_plan_kinds(self):
        self.assertEqual(StartPlan("timed").kind, "timed")
        self.assertRaises(ValidationError, StartPlan, "blocks")
        self.assertRaises(ValidationError, StartPlan, "punching")
        self.assertEqual(StartPlan("punching", window_first=at("10:00:00"),
                                   window_last=at("12:00:00")).kind, "punching")
        self.assertRaises(ValidationError, StartPlan, "shotgun")

    def test_a_full_block_is_reported(self):
        plan = StartPlan("blocks", [Block("small", at("10:00:00"), at("10:02:00"), ["M21"], 60)])
        entries = [entry(f"ENT-000{index}") for index in range(1, 6)]
        problems = plan.check(entries)
        self.assertEqual(len(problems), 1)
        self.assertIn("holds 3", problems[0])

    def test_a_class_in_no_block_and_a_class_in_two(self):
        plan = StartPlan("blocks", [
            Block("a", at("10:00:00"), at("11:00:00"), ["M21"]),
            Block("b", at("11:00:00"), at("12:00:00"), ["M21", "W21"]),
        ])
        problems = plan.check([entry("ENT-0001", "M35")])
        self.assertTrue(any("not in any block" in line for line in problems))
        self.assertTrue(any("more than one block" in line for line in problems))

    def test_slots_are_handed_out_inside_each_block(self):
        plan = StartPlan("blocks", [
            Block("juniors", at("10:00:00"), at("10:30:00"), ["M14"], 120),
            Block("open", at("10:30:00"), at("11:30:00"), ["M21"], 60),
        ])
        entries = [entry("ENT-0001", "M14"), entry("ENT-0002", "M14"),
                   entry("ENT-0003", "M21"), entry("ENT-0004", "M21")]
        times = assign_block_times(plan, entries)
        self.assertEqual(times["ENT-0001"], at("10:00:00"))
        self.assertEqual(times["ENT-0002"], at("10:02:00"))
        self.assertEqual(times["ENT-0003"], at("10:30:00"))
        self.assertEqual(times["ENT-0004"], at("10:31:00"))

    def test_assigning_from_a_plan_that_has_no_blocks(self):
        self.assertRaises(RuleError, assign_block_times, StartPlan("timed"), [])

    def test_a_class_with_nowhere_to_start_and_a_block_that_overflows(self):
        plan = StartPlan("blocks", [Block("open", at("10:00:00"), at("10:01:00"), ["M21"], 60)])
        self.assertRaises(ConflictError, assign_block_times, plan, [entry("ENT-0001", "M35")])
        self.assertRaises(ConflictError, assign_block_times, plan,
                          [entry("ENT-0001"), entry("ENT-0002"), entry("ENT-0003")])


class Lateness(unittest.TestCase):
    def test_inside_the_grace_is_not_late(self):
        entries = [entry("ENT-0001", start="10:00:00")]
        self.assertEqual(late_runners(entries, {"ENT-0001": at("10:01:00")}), [])
        self.assertEqual(GRACE_SECONDS, 120)

    def test_past_the_grace_is_late_and_by_how_much(self):
        entries = [entry("ENT-0001", start="10:00:00"), entry("ENT-0002", start="10:02:00")]
        rows = late_runners(entries, {"ENT-0001": at("10:09:00"), "ENT-0002": at("10:05:00")})
        self.assertEqual([row["entry"] for row in rows], ["ENT-0001", "ENT-0002"])
        self.assertEqual(rows[0]["late_by"], 540)

    def test_a_runner_who_never_went_is_not_late(self):
        entries = [entry("ENT-0001", start="10:00:00")]
        self.assertEqual(late_runners(entries, {}), [])
        self.assertEqual(late_runners([entry("ENT-0002")], {"ENT-0002": at("10:00:00")}), [])

    def test_what_was_decided_about_a_late_runner(self):
        own = LateStart("ENT-0001", at("10:00:00"), at("10:09:00"))
        self.assertEqual(own.decision, "own-time")
        self.assertEqual(own.start_seconds, at("10:00:00"))
        self.assertEqual(own.late_by, 540)

        again = LateStart("ENT-0001", at("10:00:00"), at("10:09:00"),
                          "reinstated", at("10:12:00"))
        self.assertEqual(again.start_seconds, at("10:12:00"))
        self.assertIsNone(LateStart("ENT-0001", at("10:00:00"), at("10:09:00"), "refused").start_seconds)
        self.assertEqual(again.to_dict()["start"], "10:12:00")

    def test_a_reinstated_runner_needs_a_new_time(self):
        self.assertRaises(ValidationError, LateStart, "ENT-0001",
                          at("10:00:00"), at("10:09:00"), "reinstated")
        self.assertRaises(ValidationError, LateStart, "ENT-0001",
                          at("10:00:00"), at("10:09:00"), "sent-home")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
