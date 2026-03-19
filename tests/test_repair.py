from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.errors import ConflictError, ValidationError
from reentrant.results.classify import Result, classify
from reentrant.timing.repair import (
    DECISIONS, Correction, CorrectionLog, apply_corrections, voided_course_codes,
)


def rows():
    return [
        Result("E1", "Okonkwo, Ada", "DPO", "W45", "Blue", 1872, "mispunch"),
        Result("E2", "Bergstrom, Nils", "SYO", "W45", "Blue", 1755),
        Result("E3", "Cai, Jo", "", "W45", "Blue", None, "no-finish"),
    ]


class Corrections(unittest.TestCase):
    def test_a_decision_records_who_and_why(self):
        one = Correction("E1", "reinstate", "control 102 found in the bracken", "organiser")
        self.assertEqual(one.decision, "reinstate")
        self.assertEqual(one.by, "organiser")
        self.assertIn("reinstate", DECISIONS)

    def test_the_decisions_that_need_more_than_a_reason(self):
        self.assertRaises(ValidationError, Correction, "E1", "set-time", "card failed")
        self.assertRaises(ValidationError, Correction, "E1", "void-control", "knocked over")
        self.assertRaises(ValidationError, Correction, "E1", "reinstate", "")
        self.assertRaises(ValidationError, Correction, "E1", "pardon", "why not")

    def test_a_correction_round_trips(self):
        one = Correction("E3", "set-time", "timed by hand", "organiser", seconds=1900)
        self.assertEqual(Correction.from_dict(one.to_dict()), one)
        self.assertEqual(Correction.from_dict({"entry": "E3", "decision": "set-time",
                                               "reason": "x", "time": "31:40"}).seconds, 1900)

    def test_the_same_decision_twice_is_refused(self):
        log = CorrectionLog()
        log.add(Correction("E1", "reinstate", "found in the bracken"))
        self.assertRaises(ConflictError, log.add, Correction("E1", "reinstate", "again"))
        log.add(Correction("E1", "disqualify", "changed our minds"))
        self.assertEqual(len(log), 2)
        self.assertEqual(len(log.about("E1")), 2)

    def test_a_log_round_trips(self):
        log = CorrectionLog()
        log.add(Correction("E1", "reinstate", "found in the bracken"))
        back = CorrectionLog.from_list(log.to_list())
        self.assertEqual(back.to_list(), log.to_list())


class Applying(unittest.TestCase):
    def test_a_reinstated_run_keeps_its_time(self):
        log = CorrectionLog()
        log.add(Correction("E1", "reinstate", "control was down"))
        fixed = apply_corrections(rows(), log)
        self.assertEqual(fixed[0].outcome, "ok")
        self.assertEqual(fixed[0].seconds, 1872)

    def test_a_time_set_by_hand(self):
        log = CorrectionLog()
        log.add(Correction("E3", "set-time", "card failed", seconds=1900))
        fixed = apply_corrections(rows(), log)
        self.assertEqual(fixed[2].outcome, "ok")
        self.assertEqual(fixed[2].seconds, 1900)

    def test_retiring_and_disqualifying_lose_the_time(self):
        log = CorrectionLog()
        log.add(Correction("E2", "disqualify", "cut the course"))
        fixed = apply_corrections(rows(), log)
        self.assertEqual(fixed[1].outcome, "disqualified")
        self.assertIsNone(fixed[1].seconds)

    def test_disqualification_wins_however_it_was_typed(self):
        log = CorrectionLog()
        log.add(Correction("E1", "disqualify", "cut the course"))
        log.add(Correction("E1", "reinstate", "control was down"))
        self.assertEqual(apply_corrections(rows(), log)[0].outcome, "disqualified")

    def test_a_correction_about_somebody_who_is_not_there(self):
        log = CorrectionLog()
        log.add(Correction("E9", "reinstate", "not in this event"))
        self.assertEqual([row.outcome for row in apply_corrections(rows(), log)],
                         ["mispunch", "ok", "no-finish"])

    def test_the_corrected_list_still_classifies(self):
        log = CorrectionLog()
        log.add(Correction("E1", "reinstate", "control was down"))
        placed = classify(apply_corrections(rows(), log))
        self.assertEqual([row.place for row in placed][:2], [1, 2])
        self.assertEqual(placed[0].name, "Bergstrom, Nils")

    def test_the_punches_are_never_edited(self):
        original = rows()
        log = CorrectionLog()
        log.add(Correction("E1", "reinstate", "control was down"))
        apply_corrections(original, log)
        self.assertEqual(original[0].outcome, "mispunch", "the input is untouched")


class Voiding(unittest.TestCase):
    def test_a_voided_control_comes_out_of_the_course(self):
        log = CorrectionLog()
        log.add(Correction("E1", "void-control", "knocked over", code="102"))
        self.assertEqual(log.voided(), ["102"])
        self.assertEqual(voided_course_codes(["S1", "101", "102", "103", "F1"], log),
                         ["S1", "101", "103", "F1"])

    def test_nothing_voided_leaves_the_course_alone(self):
        codes = ["S1", "101", "F1"]
        self.assertEqual(voided_course_codes(codes, CorrectionLog()), codes)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
