from __future__ import annotations

import unittest

from . import context  # noqa: F401

from reentrant.event.league import (
    DEFAULT_COUNTING, LeagueEvent, LeagueScore, build_league, score_event, standings,
)
from reentrant.results.classify import Result
from reentrant.results.team import club_totals, score_course
from reentrant.results.team import score_event as score_teams


def result(entry, name, club, seconds=None, outcome="ok", course="Blue", class_code="M21"):
    return Result(entry, name, club, class_code, course, seconds, outcome)


class Teams(unittest.TestCase):
    def field(self):
        # DPO take 1, 3, 5, 7 and SYO take 2, 4, 6, 8.
        return [result(f"E{index}", f"Runner {index}",
                       "DPO" if index % 2 else "SYO", 1700 + index * 10)
                for index in range(1, 9)]

    def test_the_first_three_from_each_club_score(self):
        scores = score_course(self.field())
        self.assertEqual([score.club for score in scores], ["DPO", "SYO"])
        self.assertEqual(scores[0].points, 9, "places 1, 3 and 5")
        self.assertEqual(scores[1].points, 12)
        self.assertEqual(scores[0].places[:3], [1, 3, 5])
        self.assertEqual(scores[0].to_dict()["places"], [1, 3, 5], "only the counters are reported")

    def test_a_club_short_of_a_team_does_not_score(self):
        rows = self.field() + [result("E9", "Runner 9", "HALO", 1900)]
        scores = score_course(rows)
        halo = next(score for score in scores if score.club == "HALO")
        self.assertFalse(halo.complete)
        self.assertIsNone(halo.points, "not nought, and not last -- simply not a team")
        self.assertEqual(scores[-1].club, "HALO", "incomplete teams come after complete ones")

    def test_a_tie_is_broken_by_the_last_counter(self):
        rows = [
            result("A1", "A one", "AAA", 1000), result("B1", "B one", "BBB", 1010),
            result("B2", "B two", "BBB", 1020), result("A2", "A two", "AAA", 1030),
            result("B3", "B three", "BBB", 1040), result("A3", "A three", "AAA", 1050),
        ]
        # AAA: 1, 4, 6 = 11.  BBB: 2, 3, 5 = 10.
        scores = score_course(rows)
        self.assertEqual([score.club for score in scores], ["BBB", "AAA"])
        self.assertEqual([score.points for score in scores], [10, 11])

    def test_an_exact_tie_goes_to_the_better_last_counter(self):
        rows = [
            result("A1", "A one", "AAA", 1000), result("B1", "B one", "BBB", 1010),
            result("B2", "B two", "BBB", 1020), result("B3", "B three", "BBB", 1030),
            result("A2", "A two", "AAA", 1040), result("A3", "A three", "AAA", 1050),
        ]
        # AAA: 1, 5, 6 = 12.  BBB: 2, 3, 4 = 9.
        scores = score_course(rows)
        self.assertEqual(scores[0].club, "BBB")
        self.assertLess(scores[0].last_counter, scores[1].last_counter)

    def test_unattached_runners_do_not_score(self):
        rows = self.field() + [result("E9", "Nobody", "", 1000)]
        self.assertEqual(sorted(score.club for score in score_course(rows)), ["DPO", "SYO"])

    def test_a_different_team_size(self):
        scores = score_course(self.field(), counting=2)
        self.assertEqual(scores[0].points, 4, "places 1 and 3")

    def test_the_whole_event_and_the_trophy(self):
        rows = self.field() + [result(f"G{index}", f"Green {index}",
                                      "DPO" if index % 2 else "SYO", 2000 + index,
                                      course="Green") for index in range(1, 7)]
        scored = score_teams(rows)
        self.assertEqual(sorted(scored), ["Blue", "Green"])
        totals = club_totals(scored)
        self.assertEqual(totals[0]["club"], "DPO")
        self.assertEqual(totals[0]["courses"], 2)


class League(unittest.TestCase):
    def events(self, count=3):
        made = []
        for number in range(1, count + 1):
            made.append(LeagueEvent(
                name=f"Fixture {number}",
                date=f"2026-0{number}-10",
                results=[
                    result("E1", "Okonkwo, Ada", "DPO", 1700 + number),
                    result("E2", "Bergstrom, Nils", "SYO", 1800 + number),
                    result("E3", "Cai, Jo", "HALO", None, "mispunch"),
                ],
            ))
        return made

    def test_points_come_from_the_place_in_the_class(self):
        rows = score_event(self.events(1)[0])
        self.assertEqual(rows[0]["points"], 100)
        self.assertEqual(rows[1]["points"], 98)
        self.assertEqual(rows[2]["points"], 0, "a mispunch scores nothing")

    def test_a_league_adds_the_best_events_up(self):
        league = build_league(self.events(3), counting=2)
        table = league["M21"]
        self.assertEqual(table[0].name, "Okonkwo, Ada")
        self.assertEqual(table[0].points, 200, "two firsts")
        self.assertEqual(table[0].events, 3)
        self.assertEqual(len(table[0].counted), 2)

    def test_only_the_best_count(self):
        events = self.events(2)
        events.append(LeagueEvent("Fixture 3", "2026-03-10", [
            result("E1", "Okonkwo, Ada", "DPO", None, "mispunch"),
        ]))
        league = build_league(events, counting=2)
        ada = next(score for score in league["M21"] if score.name == "Okonkwo, Ada")
        self.assertEqual(ada.points, 200, "the nought is not among the best two")
        self.assertEqual(ada.events, 3)

    def test_a_runner_at_one_event_only(self):
        events = self.events(1)
        events.append(LeagueEvent("Fixture 2", "2026-02-10", [
            result("E9", "Newcomer, Sam", "DPO", 1650),
        ]))
        league = build_league(events, counting=6)
        sam = next(score for score in league["M21"] if score.name == "Newcomer, Sam")
        self.assertEqual(sam.events, 1)
        self.assertEqual(sam.points, 100)

    def test_a_cancelled_fixture_is_simply_absent(self):
        self.assertEqual(len(build_league(self.events(2))["M21"][0].scores), 2)

    def test_the_table_places_ties_together(self):
        events = [LeagueEvent("One", "2026-01-10", [
            result("E1", "A", "DPO", 1000), result("E2", "B", "SYO", 1000),
        ])]
        table = standings(build_league(events), "m21")
        self.assertEqual([row["place"] for row in table], [1, 1])
        self.assertEqual(standings(build_league(events), "W45"), [])

    def test_the_counting_default(self):
        self.assertEqual(DEFAULT_COUNTING, 6)
        self.assertEqual(LeagueScore("A", "DPO", "M21").points, 0)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
