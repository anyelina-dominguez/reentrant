from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.entries.competitor import (
    ENTRY_STATES, Competitor, Entry, EntryList, require_card,
)
from reentrant.errors import ConflictError, NotFoundError, ValidationError


def person(surname="Okonkwo", forename="Ada", club="DPO", birth_year=1981, sex="W") -> Competitor:
    return Competitor(surname, forename, club, birth_year, sex)


def entry(reference="ENT-0001", card=205431, class_code="W45", course="Blue", **kwargs) -> Entry:
    return Entry(reference=reference, competitor=kwargs.pop("competitor", person()),
                 course=course, class_code=class_code, card=card, **kwargs)


class Competitors(unittest.TestCase):
    def test_names_are_held_in_two_pieces(self):
        who = Competitor("van der Berg", "Sam")
        self.assertEqual(who.name, "Sam van der Berg")
        self.assertEqual(who.listed_name, "van der Berg, Sam")

    def test_the_class_a_competitor_belongs_in(self):
        self.assertEqual(person().natural_class(2026).code, "W45")
        self.assertIsNone(Competitor("Bo", "Sam").natural_class(2026))
        self.assertIsNone(Competitor("Bo", "Sam", birth_year=1981).natural_class(2026))

    def test_what_a_competitor_will_not_accept(self):
        self.assertRaises(ValidationError, Competitor, "", "Ada")
        self.assertRaises(ValidationError, Competitor, "Okonkwo", "")
        self.assertRaises(ValidationError, Competitor, "Okonkwo", "Ada", sex="X")
        self.assertRaises(ValidationError, Competitor, "Okonkwo", "Ada", birth_year=1800)

    def test_a_competitor_round_trips(self):
        who = person()
        self.assertEqual(Competitor.from_dict(who.to_dict()), who)
        bare = Competitor("Bo", "Sam")
        self.assertEqual(Competitor.from_dict(bare.to_dict()), bare)


class Entries(unittest.TestCase):
    def test_an_entry_names_a_course_a_class_and_a_card(self):
        one = entry()
        self.assertEqual(one.course, "Blue")
        self.assertEqual(one.age_class.code, "W45")
        self.assertEqual(one.state, "entered")
        self.assertFalse(one.has_run)

    def test_card_numbers_are_bounded(self):
        self.assertEqual(require_card(205431), 205431)
        self.assertRaises(ValidationError, require_card, 0)
        self.assertRaises(ValidationError, require_card, 99_999_999)
        self.assertRaises(ValidationError, entry, card="two hundred")

    def test_an_entry_may_have_no_card_yet(self):
        one = entry(card=None)
        self.assertIsNone(one.card)

    def test_wanting_a_hire_card_before_one_is_allocated(self):
        # The entry form says "I want to hire"; the number comes at the desk.
        wanted = entry(card=None, hired=True)
        self.assertTrue(wanted.hired)
        self.assertIsNone(wanted.card)

    def test_eligibility_is_checked_against_the_class_entered(self):
        self.assertTrue(entry(class_code="W45").eligible(2026))
        self.assertTrue(entry(class_code="W21").eligible(2026))
        self.assertFalse(entry(class_code="W50").eligible(2026))

    def test_an_entry_with_no_birth_year_is_the_desk_problem_not_ours(self):
        one = entry(competitor=Competitor("Bo", "Sam"), class_code="M21")
        self.assertTrue(one.eligible(2026))

    def test_the_states_an_entry_moves_through(self):
        one = entry()
        self.assertEqual(ENTRY_STATES[0], "entered")
        self.assertTrue(one.with_state("finished").has_run)
        self.assertTrue(one.with_state("dnf").has_run)
        self.assertFalse(one.with_state("dns").has_run)
        self.assertEqual(one.with_state("dnf", note="retired at 3").note, "retired at 3")
        self.assertRaises(ValidationError, one.with_state, "lost")

    def test_an_entry_round_trips(self):
        one = entry(start_seconds=37800, hired=True)
        self.assertEqual(Entry.from_dict(one.to_dict()).to_dict(), one.to_dict())


class Lists(unittest.TestCase):
    def setUp(self):
        self.entries = EntryList()
        self.first = self.entries.add(entry("ENT-0001", 205431, "W45"))
        self.second = self.entries.add(
            entry("ENT-0002", 210022, "M21", "Brown",
                  competitor=Competitor("Bergstrom", "Nils", "SYO", 1990, "M")))

    def test_one_card_one_run(self):
        clash = entry("ENT-0003", 205431, "M21", "Brown", competitor=Competitor("Bo", "Sam"))
        with self.assertRaises(ConflictError) as caught:
            self.entries.add(clash)
        self.assertEqual(caught.exception.details["held_by"], "ENT-0001")
        self.assertEqual(len(self.entries), 2)

    def test_lookup_by_reference_and_by_card(self):
        self.assertEqual(self.entries.require("ENT-0001").card, 205431)
        self.assertEqual(self.entries.require_card(210022).reference, "ENT-0002")
        self.assertIsNone(self.entries.by_card(999999))
        self.assertRaises(NotFoundError, self.entries.require_card, 999999)
        self.assertRaises(NotFoundError, self.entries.require, "ENT-0009")

    def test_references_are_minted_past_what_is_there(self):
        self.assertEqual(self.entries.next_reference(), "ENT-0003")

    def test_removing_frees_the_card(self):
        self.entries.remove("ENT-0001")
        self.assertIsNone(self.entries.by_card(205431))
        self.entries.add(entry("ENT-0009", 205431, "M21", "Brown", competitor=Competitor("Bo", "Sam")))
        self.assertEqual(self.entries.require_card(205431).reference, "ENT-0009")

    def test_replacing_an_entry_moves_its_card_with_it(self):
        moved = Entry.from_dict({**self.first.to_dict(), "card": 300111})
        self.entries.update(moved)
        self.assertIsNone(self.entries.by_card(205431))
        self.assertEqual(self.entries.require_card(300111).reference, "ENT-0001")

    def test_slicing_the_field(self):
        self.assertEqual([e.reference for e in self.entries.on_course("Blue")], ["ENT-0001"])
        self.assertEqual([e.reference for e in self.entries.in_class("m21")], ["ENT-0002"])
        self.assertEqual(list(self.entries.by_club()), ["DPO", "SYO"])
        self.assertEqual(self.entries.hired_cards(), [])

    def test_entries_in_a_class_they_may_not_run(self):
        self.entries.add(entry("ENT-0004", 300222, "W50", "Blue"))
        self.assertEqual([e.reference for e in self.entries.ineligible(2026)], ["ENT-0004"])

    def test_a_list_round_trips(self):
        back = EntryList.from_list(self.entries.to_list())
        self.assertEqual([e.reference for e in back.all()], ["ENT-0001", "ENT-0002"])
        self.assertEqual(back.require_card(205431).competitor.listed_name, "Okonkwo, Ada")
        self.assertEqual(back.next_reference(), "ENT-0003")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
