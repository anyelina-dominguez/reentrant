from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.courses.control import (
    ANY_FEATURE_METRES, SIMILAR_FEATURE_METRES, Control, ControlSet,
)
from reentrant.courses.descriptions import Description, parse_description
from reentrant.errors import ConflictError, NotFoundError, RuleError, ValidationError
from reentrant.geo.grid import parse as grid


def control(code: str, east: int, north: int = 67890, feature: str = "boulder", **kwargs) -> Control:
    return Control(
        code=code,
        position=grid(f"SK {east} {north}"),
        description=parse_description(feature),
        **kwargs,
    )


class Descriptions(unittest.TestCase):
    def test_the_columns_read_in_order(self):
        described = Description(feature="re-entrant", which="northern",
                                appearance="overgrown", location="foot")
        self.assertEqual(described.text(), "northern overgrown re-entrant, foot")

    def test_only_the_feature_is_compulsory(self):
        self.assertEqual(Description(feature="boulder").text(), "boulder")
        self.assertRaises(ValidationError, Description, feature="")
        self.assertRaises(ValidationError, Description, feature="wormhole")

    def test_the_other_columns_are_checked_against_the_vocabulary(self):
        self.assertRaises(ValidationError, Description, feature="boulder", which="leftish")
        self.assertRaises(ValidationError, Description, feature="boulder", location="underneath")
        self.assertRaises(ValidationError, Description, feature="boulder", other="catering")
        self.assertRaises(ValidationError, Description, feature="boulder", appearance="damp")

    def test_dimensions_and_the_tail_columns(self):
        described = Description(feature="boulder", dimensions="2m", location="north-side", other="manned")
        self.assertEqual(described.text(), "boulder 2m, north side, manned")

    def test_the_planner_shorthand(self):
        self.assertEqual(parse_description("boulder").text(), "boulder")
        self.assertEqual(parse_description("re-entrant/foot").text(), "re-entrant, foot")
        self.assertEqual(
            parse_description("northern:overgrown:re-entrant/foot").text(),
            "northern overgrown re-entrant, foot",
        )
        self.assertEqual(parse_description("PATH/junction").text(), "path, junction")

    def test_shorthand_that_is_not_a_description(self):
        self.assertRaises(ValidationError, parse_description, "sideways:boulder")
        self.assertRaises(ValidationError, parse_description, "/foot")
        self.assertRaises(ValidationError, parse_description, "")

    def test_a_description_round_trips(self):
        described = parse_description("northern:overgrown:re-entrant/foot")
        self.assertEqual(Description.from_dict(described.to_dict()), described)
        self.assertRaises(ValidationError, Description.from_dict, [])


class Controls(unittest.TestCase):
    def test_a_control_is_a_code_a_place_and_a_description(self):
        one = control("101", 12345, height=210)
        self.assertEqual(one.code, "101")
        self.assertEqual(one.feature, "boulder")
        self.assertEqual(one.height, 210)
        self.assertEqual(one.describe(), " 101  boulder")
        self.assertFalse(one.is_start)

    def test_start_and_finish_are_controls_too(self):
        start = Control("S1", grid("SK 12000 67000"))
        self.assertTrue(start.is_start)
        self.assertFalse(start.is_finish)
        self.assertTrue(Control("F1", grid("SK 12000 67000")).is_finish)
        self.assertEqual(start.describe(), "  S1")

    def test_what_a_control_will_not_accept(self):
        self.assertRaises(ValidationError, Control, "12", grid("SK 12000 67000"))
        self.assertRaises(ValidationError, Control, "101", "SK 12000 67000")
        self.assertRaises(ValidationError, Control, "101", grid("SK 12000 67000"), "boulder")
        self.assertRaises(ValidationError, Control, "101", grid("SK 12000 67000"), None, 9000)

    def test_a_control_round_trips(self):
        one = control("101", 12345, height=210, note="check the tape")
        self.assertEqual(Control.from_dict(one.to_dict()).to_dict(), one.to_dict())
        bare = Control("102", grid("SK 12000 67000"))
        self.assertIsNone(Control.from_dict(bare.to_dict()).description)


class Sets(unittest.TestCase):
    def test_codes_are_unique_within_an_event(self):
        controls = ControlSet()
        controls.add(control("101", 12345))
        self.assertRaises(ConflictError, controls.add, control("101", 19999))
        self.assertEqual(len(controls), 1)
        self.assertIn("101", controls)

    def test_lookup_and_removal(self):
        controls = ControlSet()
        controls.add(control("101", 12345))
        self.assertEqual(controls.require("101").code, "101")
        self.assertIsNone(controls.get("199"))
        self.assertRaises(NotFoundError, controls.require, "199")
        self.assertEqual(controls.remove("101").code, "101")
        self.assertEqual(len(controls), 0)

    def test_the_start_and_finish_sort_last(self):
        controls = ControlSet()
        controls.add(Control("F1", grid("SK 12000 67000")))
        controls.add(control("103", 13000))
        controls.add(Control("S1", grid("SK 12000 67000")))
        controls.add(control("101", 12345))
        self.assertEqual(controls.codes(), ["101", "103", "F1", "S1"])

    def test_the_next_free_code(self):
        controls = ControlSet()
        for code in ("31", "32", "34"):
            controls.add(control(code, 12000 + int(code)))
        self.assertEqual(controls.next_code(), "33")
        self.assertEqual(controls.next_code(start=100), "100")

    def test_what_is_near_a_place(self):
        controls = ControlSet()
        controls.add(control("101", 12345))
        controls.add(control("102", 12360))
        controls.add(control("103", 13000))
        near = controls.near(grid("SK 12345 67890"), 100)
        self.assertEqual([code for code, _ in [(c.code, d) for c, d in near]], ["101", "102"])
        self.assertEqual(near[0][1], 0.0)

    def test_two_controls_on_similar_features_may_not_be_close(self):
        controls = ControlSet()
        controls.add(control("101", 12345, feature="boulder"))
        controls.add(control("102", 12360, feature="boulder"))
        problems = controls.conflicts()
        self.assertEqual(len(problems), 1)
        self.assertEqual(problems[0]["codes"], ["101", "102"])
        self.assertEqual(problems[0]["limit"], SIMILAR_FEATURE_METRES)
        self.assertEqual(problems[0]["reason"], "similar features too close")

    def test_different_features_get_the_shorter_limit(self):
        controls = ControlSet()
        controls.add(control("101", 12345, feature="boulder"))
        controls.add(control("102", 12385, feature="knoll"))
        # Forty metres apart: too close for two boulders, far enough for a
        # boulder and a knoll.
        self.assertEqual(controls.conflicts(), [])
        self.assertGreater(SIMILAR_FEATURE_METRES, ANY_FEATURE_METRES)

    def test_controls_far_enough_apart_are_no_trouble(self):
        controls = ControlSet()
        controls.add(control("101", 12345))
        controls.add(control("102", 13000))
        self.assertEqual(controls.conflicts(), [])
        controls.check()

    def test_the_start_and_finish_are_exempt(self):
        controls = ControlSet()
        controls.add(Control("S1", grid("SK 12345 67890")))
        controls.add(Control("F1", grid("SK 12346 67890")))
        controls.add(control("101", 12347))
        self.assertEqual(controls.conflicts(), [])

    def test_check_raises_on_the_worst_pair(self):
        controls = ControlSet()
        controls.add(control("101", 12345))
        controls.add(control("102", 12350))
        controls.add(control("103", 12420))
        with self.assertRaises(RuleError) as caught:
            controls.check()
        self.assertEqual(caught.exception.details["codes"], ["101", "102"])

    def test_a_set_round_trips(self):
        controls = ControlSet()
        controls.add(control("101", 12345, height=210))
        controls.add(Control("S1", grid("SK 12000 67000")))
        back = ControlSet.from_list(controls.to_list())
        self.assertEqual(back.codes(), controls.codes())
        self.assertEqual(back.require("101").height, 210)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
