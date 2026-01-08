from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.util.order import by, first_by, group_by, partition, rank, sorted_by


class Row:
    def __init__(self, name: str, time: int | None = None, club: str = "") -> None:
        self.name = name
        self.time = time
        self.club = club

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Row({self.name!r})"


class Sorting(unittest.TestCase):
    def setUp(self):
        self.rows = [Row("c", 10), Row("a", None), Row("b", 10), Row("d", 5)]

    def test_sorts_on_several_keys(self):
        self.assertEqual([r.name for r in sorted_by(self.rows, "time", "name")], ["d", "b", "c", "a"])

    def test_absent_values_sort_last_ascending(self):
        self.assertEqual([r.name for r in sorted_by(self.rows, "time")][-1], "a")

    def test_absent_values_sort_last_descending_too(self):
        # A runner with no time is not the fastest, and is not the slowest either;
        # they are simply not in the ordering, so they go at the end both ways.
        self.assertEqual([r.name for r in sorted_by(self.rows, "-time")][-1], "a")
        self.assertEqual([r.name for r in sorted_by(self.rows, "-time", "name")][:3], ["b", "c", "d"])

    def test_a_callable_key(self):
        self.assertEqual([r.name for r in sorted_by(self.rows, lambda r: r.name)], ["a", "b", "c", "d"])

    def test_dictionaries_work_the_same_way(self):
        rows = [{"name": "b", "time": 2}, {"name": "a", "time": 2}, {"name": "c", "time": 1}]
        self.assertEqual([r["name"] for r in sorted_by(rows, "time", "name")], ["c", "a", "b"])

    def test_sorting_copies(self):
        original = list(self.rows)
        sorted_by(self.rows, "name")
        self.assertEqual(self.rows, original)

    def test_the_key_function_is_reusable(self):
        key = by("time", "name")
        self.assertEqual([r.name for r in sorted(self.rows, key=key)], ["d", "b", "c", "a"])


class Grouping(unittest.TestCase):
    def test_group_by_keeps_first_seen_order(self):
        rows = [Row("a", club="DPO"), Row("b", club="SYO"), Row("c", club="DPO")]
        groups = group_by(rows, lambda r: r.club)
        self.assertEqual(list(groups), ["DPO", "SYO"])
        self.assertEqual([r.name for r in groups["DPO"]], ["a", "c"])

    def test_first_and_partition(self):
        rows = [Row("a", 30), Row("b", 10), Row("c", 20)]
        self.assertEqual(first_by(rows, "time").name, "b")
        self.assertIsNone(first_by([], "time"))
        fast, slow = partition(rows, lambda r: r.time < 25)
        self.assertEqual([r.name for r in fast], ["b", "c"])
        self.assertEqual([r.name for r in slow], ["a"])


class Ranking(unittest.TestCase):
    def test_ties_share_a_place_and_the_next_is_skipped(self):
        rows = [Row("a", 10), Row("b", 12), Row("c", 12), Row("d", 15)]
        placed = rank(rows, lambda r: r.time)
        self.assertEqual([(p, r.name) for p, r in placed], [(1, "a"), (2, "b"), (2, "c"), (4, "d")])

    def test_everyone_tied_is_all_first(self):
        rows = [Row("a", 10), Row("b", 10), Row("c", 10)]
        self.assertEqual([p for p, _ in rank(rows, lambda r: r.time)], [1, 1, 1])

    def test_ranking_an_empty_field(self):
        self.assertEqual(rank([], lambda r: r.time), [])


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
