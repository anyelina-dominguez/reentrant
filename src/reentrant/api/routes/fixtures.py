"""The season's fixture list, over http.

This is the one part of the surface a member of the public reads: the club
website asks for the calendar and shows it. It is therefore the one part that
must never 500, so a season that has not been set up answers with an empty
calendar rather than an error.
"""

from __future__ import annotations

from typing import Any

from ...errors import NotFoundError
from ...event.fixtures import Fixture, Season
from ...util.validate import optional, require_int, require_mapping, require_str
from ..router import Router


def _season(context) -> Season:
    if not hasattr(context, "season") or context.season is None:
        context.season = Season(name="season")
    return context.season


def fixture_routes() -> Router:
    router = Router()

    def get_calendar(*, query, context, **_: Any):
        season = _season(context)
        today = query.get("on") or context.event.date
        return {
            "season": season.name,
            "on": today,
            "fixtures": season.calendar(today),
            "next": None if season.next_after(today) is None else season.next_after(today).name,
        }

    def get_fixture(*, params, context, **_: Any):
        return _season(context).require(params["name"]).to_dict()

    def add_fixture(*, body, context, **_: Any):
        raw = require_mapping(body, "body")
        fixture = Fixture(
            name=require_str(raw.get("name"), "name", max_len=80),
            date=require_str(raw.get("date"), "date", max_len=10),
            venue=str(raw.get("venue") or ""),
            opens=optional(raw.get("opens"), lambda v: require_str(v, "opens", max_len=10)),
            closes=optional(raw.get("closes"), lambda v: require_str(v, "closes", max_len=10)),
            capacity=optional(raw.get("capacity"), lambda v: require_int(v, "capacity", minimum=1)),
            note=str(raw.get("note") or ""),
        )
        _season(context).add(fixture)
        return 201, fixture.to_dict()

    def enter_fixture(*, params, body, context, **_: Any):
        raw = require_mapping(body or {}, "body")
        season = _season(context)
        fixture = season.require(params["name"])
        today = require_str(raw.get("on") or context.event.date, "on", max_len=10)
        count = require_int(raw.get("count", 1), "count", minimum=1, maximum=100)
        fixture.take_entry(today, count=count)
        return 201, fixture.to_dict()

    def cancel_fixture(*, params, body, context, **_: Any):
        raw = require_mapping(body or {}, "body")
        fixture = _season(context).require(params["name"])
        fixture.cancelled = True
        fixture.note = str(raw.get("reason") or fixture.note)
        return fixture.to_dict()

    router.get("/fixtures", get_calendar)
    router.post("/fixtures", add_fixture)
    router.get("/fixtures/:name", get_fixture)
    router.post("/fixtures/:name/entries", enter_fixture)
    router.delete("/fixtures/:name", cancel_fixture)
    return router


__all__ = ["fixture_routes", "NotFoundError"]
