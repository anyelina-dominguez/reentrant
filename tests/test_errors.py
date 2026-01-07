from __future__ import annotations

import unittest

from . import context  # noqa: F401  (puts src on the path)

from reentrant.errors import (
    ConflictError, NotFoundError, ReentrantError, RuleError, SchemaError,
    ValidationError, status_of,
)
from reentrant.util.validate import (
    fail, optional, require, require_bool, require_int, require_list,
    require_mapping, require_number, require_one_of, require_str, unique,
)


class ErrorKinds(unittest.TestCase):
    def test_each_error_carries_the_status_the_http_layer_uses(self):
        self.assertEqual(ValidationError("x").status, 400)
        self.assertEqual(NotFoundError("x").status, 404)
        self.assertEqual(ConflictError("x").status, 409)
        self.assertEqual(RuleError("x").status, 409)
        self.assertEqual(SchemaError("x").status, 500)
        self.assertEqual(status_of(RuntimeError("plain")), 500)

    def test_an_error_serialises_with_its_name_and_details(self):
        error = NotFoundError("no such competitor", card=205431)
        self.assertEqual(
            error.to_dict(),
            {"error": "NotFoundError", "message": "no such competitor", "card": 205431},
        )

    def test_a_rule_error_is_not_a_conflict_error(self):
        self.assertIsInstance(RuleError("x"), ReentrantError)
        self.assertNotIsInstance(RuleError("x"), ConflictError)


class Strings(unittest.TestCase):
    def test_require_str_trims_and_bounds(self):
        self.assertEqual(require_str("  Dark Peak  ", "club"), "Dark Peak")
        self.assertRaises(ValidationError, require_str, "", "club")
        self.assertRaises(ValidationError, require_str, 7, "club")
        self.assertRaises(ValidationError, require_str, "abcd", "club", max_len=3)

    def test_a_pattern_is_matched_in_full(self):
        self.assertEqual(require_str("101", "code", pattern=r"\d{2,3}"), "101")
        self.assertRaises(ValidationError, require_str, "101a", "code", pattern=r"\d{2,3}")

    def test_strip_can_be_turned_off(self):
        self.assertEqual(require_str(" a ", "s", strip=False), " a ")


class Numbers(unittest.TestCase):
    def test_require_int_takes_digit_strings_but_not_floats(self):
        self.assertEqual(require_int("205431", "card"), 205431)
        self.assertEqual(require_int(-3, "delta"), -3)
        self.assertRaises(ValidationError, require_int, 1.5, "card")
        self.assertRaises(ValidationError, require_int, "1.5", "card")

    def test_a_boolean_is_not_a_number(self):
        # bool subclasses int in Python, and a True where a count belongs is a bug.
        self.assertRaises(ValidationError, require_int, True, "count")
        self.assertRaises(ValidationError, require_number, False, "climb")

    def test_bounds(self):
        self.assertEqual(require_int(5, "n", minimum=1, maximum=10), 5)
        self.assertRaises(ValidationError, require_int, 0, "n", minimum=1)
        self.assertRaises(ValidationError, require_int, 11, "n", maximum=10)
        self.assertEqual(require_number("2.5", "km"), 2.5)
        self.assertRaises(ValidationError, require_number, float("nan"), "km")
        self.assertRaises(ValidationError, require_number, float("inf"), "km")
        self.assertRaises(ValidationError, require_number, "wide", "km")


class Collections(unittest.TestCase):
    def test_lists_and_mappings(self):
        self.assertEqual(require_list((1, 2), "controls"), [1, 2])
        self.assertRaises(ValidationError, require_list, {}, "controls")
        self.assertRaises(ValidationError, require_list, [], "controls", min_len=1)
        self.assertRaises(ValidationError, require_list, [1, 2], "controls", max_len=1)
        self.assertEqual(require_mapping({"a": 1}, "body"), {"a": 1})
        self.assertRaises(ValidationError, require_mapping, [], "body")

    def test_require_one_of_names_what_it_would_have_taken(self):
        self.assertEqual(require_one_of("M21", "class", ["M21", "W21"]), "M21")
        with self.assertRaises(ValidationError) as caught:
            require_one_of("X", "class", ["M21", "W21"])
        self.assertEqual(caught.exception.details["allowed"], ["M21", "W21"])

    def test_unique_keeps_first_seen_order(self):
        self.assertEqual(unique([3, 1, 3, 2, 1]), [3, 1, 2])


class Optionals(unittest.TestCase):
    def test_optional_lets_none_through(self):
        self.assertIsNone(optional(None, lambda v: require_int(v, "n")))
        self.assertEqual(optional("4", lambda v: require_int(v, "n")), 4)

    def test_require_and_fail(self):
        self.assertEqual(require(0, "n"), 0)
        self.assertRaises(ValidationError, require, None, "n")
        self.assertRaises(ValidationError, fail, "boom")
        self.assertRaises(ValidationError, require_bool, "true", "hired")
        self.assertTrue(require_bool(True, "hired"))


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
