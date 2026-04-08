from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.errors import ConflictError, RuleError, ValidationError
from reentrant.results.protest import (
    COMPLAINT_MINUTES, PROTEST_MINUTES, Complaint, ComplaintBook,
)
from reentrant.util.times import parse_time_of_day as at


def complaint(made="13:05:00", results="13:00:00", reference="CMP-0001", entry="ENT-0001"):
    return Complaint(reference, entry, "control 102 was not where the map said",
                     at(made), at(results))


class Timing(unittest.TestCase):
    def test_inside_the_window_is_in_time(self):
        one = complaint()
        self.assertTrue(one.in_time)
        self.assertEqual(one.late_by, 0)
        self.assertEqual(COMPLAINT_MINUTES, 15)

    def test_on_the_last_minute_is_still_in_time(self):
        self.assertTrue(complaint(made="13:15:00").in_time)

    def test_past_the_window_is_late_and_by_how_much(self):
        late = complaint(made="13:40:00")
        self.assertFalse(late.in_time)
        self.assertEqual(late.late_by, 1500)

    def test_a_complaint_is_recorded_whether_it_is_in_time_or_not(self):
        # Being late is a fact about the complaint, not a reason to refuse it.
        book = ComplaintBook()
        book.add(complaint(made="13:40:00"))
        self.assertEqual(len(book), 1)
        self.assertFalse(book.complaints[0].in_time)


class Stages(unittest.TestCase):
    def test_the_organiser_answers_first(self):
        one = complaint()
        one.answer_it("the control was checked and was correct", at("13:20:00"))
        self.assertEqual(one.stage, "complaint")
        self.assertEqual(one.answered_seconds, at("13:20:00"))
        self.assertRaises(ValidationError, one.answer_it, "", at("13:21:00"))

    def test_a_protest_needs_an_answer_to_protest_about(self):
        self.assertRaises(ConflictError, complaint().escalate, at("13:30:00"))

    def test_a_protest_inside_its_window(self):
        one = complaint()
        one.answer_it("checked and correct", at("13:20:00"))
        one.escalate(at("13:30:00"))
        self.assertEqual(one.stage, "protest")
        self.assertEqual(PROTEST_MINUTES, 15)

    def test_a_protest_out_of_time_is_refused(self):
        one = complaint()
        one.answer_it("checked and correct", at("13:20:00"))
        with self.assertRaises(RuleError) as caught:
            one.escalate(at("13:50:00"))
        self.assertEqual(caught.exception.details["late_by"], 900)

    def test_a_protest_cannot_be_lodged_twice(self):
        one = complaint()
        one.answer_it("checked and correct", at("13:20:00"))
        one.escalate(at("13:25:00"))
        self.assertRaises(ConflictError, one.escalate, at("13:26:00"))
        self.assertRaises(ConflictError, one.answer_it, "again", at("13:27:00"))

    def test_the_jury_decides_and_that_is_final(self):
        one = complaint()
        one.answer_it("checked and correct", at("13:20:00"))
        one.escalate(at("13:25:00"))
        one.decide("upheld", "the control was forty metres from its position",
                   ["Ada", "Nils", "Jo"])
        self.assertEqual(one.stage, "decided")
        self.assertEqual(one.outcome, "upheld")
        self.assertRaises(ConflictError, one.decide, "rejected", "no", ["A", "B", "C"])

    def test_a_jury_is_three_people(self):
        one = complaint()
        one.answer_it("checked", at("13:20:00"))
        one.escalate(at("13:25:00"))
        self.assertRaises(ValidationError, one.decide, "upheld", "yes", ["Ada", "Nils"])

    def test_there_must_be_a_protest_to_decide(self):
        self.assertRaises(ConflictError, complaint().decide, "upheld", "yes", ["A", "B", "C"])


class Corrections(unittest.TestCase):
    def upheld(self):
        one = complaint()
        one.answer_it("checked and correct", at("13:20:00"))
        one.escalate(at("13:25:00"))
        one.decide("upheld", "the control was forty metres out", ["Ada", "Nils", "Jo"])
        return one

    def test_an_upheld_protest_produces_a_correction(self):
        correction = self.upheld().correction("reinstate")
        self.assertEqual(correction.entry, "ENT-0001")
        self.assertEqual(correction.decision, "reinstate")
        self.assertEqual(correction.by, "jury")
        self.assertIn("forty metres", correction.reason)

    def test_a_rejected_protest_changes_nothing(self):
        one = complaint()
        one.answer_it("checked", at("13:20:00"))
        one.escalate(at("13:25:00"))
        one.decide("rejected", "the control was correct", ["A", "B", "C"])
        self.assertRaises(ConflictError, one.correction, "reinstate")

    def test_the_book_gathers_the_corrections(self):
        book = ComplaintBook()
        book.add(self.upheld())
        book.add(complaint(reference="CMP-0002", entry="ENT-0002"))
        corrections = book.corrections()
        self.assertEqual([row.entry for row in corrections], ["ENT-0001"])

    def test_what_is_still_open(self):
        book = ComplaintBook()
        book.add(self.upheld())
        book.add(complaint(reference="CMP-0002", entry="ENT-0002"))
        self.assertEqual([row.reference for row in book.open()], ["CMP-0002"])
        self.assertEqual(len(book.about("ENT-0002")), 1)

    def test_a_reference_is_not_used_twice(self):
        book = ComplaintBook()
        book.add(complaint())
        self.assertRaises(ConflictError, book.add, complaint())
        self.assertEqual(len(book.to_list()), 1)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
