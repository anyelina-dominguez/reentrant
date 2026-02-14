"""Entries, the start draw, and the start list."""

from __future__ import annotations

from typing import Any

from ...entries.competitor import Competitor, Entry
from ...errors import ValidationError
from ...starts.draw import apply_draw, draw_course, start_list
from ...util.times import format_time_of_day, parse_time_of_day
from ...util.validate import optional, require_int, require_mapping, require_str
from ..router import Router


def _entry_dict(entry: Entry, event) -> dict[str, Any]:
    return {
        **entry.to_dict(),
        "name": entry.competitor.listed_name,
        "running": event.entry_course(entry) if entry.course or entry.class_code in event.class_courses else "",
        "start": None if entry.start_seconds is None else format_time_of_day(entry.start_seconds),
    }


def entry_routes() -> Router:
    router = Router()

    def list_entries(*, query, context, **_: Any):
        event = context.event
        rows = event.entries.all()
        if query.get("course"):
            rows = [entry for entry in rows if event.entry_course(entry) == query["course"]]
        if query.get("class"):
            rows = [entry for entry in rows if entry.class_code == query["class"].upper()]
        if query.get("club"):
            rows = [entry for entry in rows if entry.competitor.club == query["club"]]
        return {"count": len(rows), "entries": [_entry_dict(entry, event) for entry in rows]}

    def get_entry(*, params, context, **_: Any):
        return _entry_dict(context.event.entries.require(params["reference"]), context.event)

    def get_by_card(*, params, context, **_: Any):
        entry = context.event.entries.require_card(int(params["card"]))
        return _entry_dict(entry, context.event)

    def add_entry(*, body, context, **_: Any):
        raw = require_mapping(body, "body")
        entries = context.event.entries
        entry = Entry(
            reference=str(raw.get("reference") or entries.next_reference()),
            competitor=Competitor(
                surname=str(raw.get("surname", "")),
                forename=str(raw.get("forename", "")),
                club=str(raw.get("club") or ""),
                birth_year=optional(raw.get("birth_year"), lambda v: require_int(v, "birth_year")),
                sex=optional(raw.get("sex"), lambda v: require_str(v, "sex")),
                membership=str(raw.get("membership") or ""),
            ),
            course=str(raw.get("course") or ""),
            class_code=str(raw.get("class") or raw.get("class_code") or ""),
            card=optional(raw.get("card"), lambda v: require_int(v, "card")),
            hired=bool(raw.get("hired", False)),
            start_seconds=optional(raw.get("start"), lambda v: parse_time_of_day(str(v), "start")),
        )
        entries.add(entry)
        context.persist()
        return 201, _entry_dict(entry, context.event)

    def update_entry(*, params, body, context, **_: Any):
        raw = require_mapping(body, "body")
        held = context.event.entries.require(params["reference"])
        changed = Entry.from_dict({
            **held.to_dict(),
            **{key: value for key, value in raw.items()
               if key in ("course", "class_code", "card", "hired", "state", "note")},
        })
        context.event.entries.update(changed)
        context.persist()
        return _entry_dict(changed, context.event)

    def delete_entry(*, params, context, **_: Any):
        removed = context.event.entries.remove(params["reference"])
        context.persist()
        return {"removed": removed.reference}

    def draw_starts(*, body, context, **_: Any):
        raw = require_mapping(body or {}, "body")
        event = context.event
        first = parse_time_of_day(str(raw.get("first", "10:00:00")), "first")
        interval = require_int(raw.get("interval", 60), "interval", minimum=10, maximum=3600)
        seed = str(raw.get("seed") or event.name)

        draws = []
        for course in event.courses.all():
            runners = [entry for entry in event.entries.all()
                       if event.entry_course(entry) == course.name]
            if not runners:
                continue
            drawn = draw_course(course.name, runners, first_seconds=first,
                                interval_seconds=interval, seed=seed)
            for entry in apply_draw(runners, drawn):
                event.entries.update(entry)
            draws.append(drawn)

        if not draws:
            raise ValidationError("there is nobody to draw")
        context.persist()
        return 201, {
            "courses": [{"course": drawn.course, "starters": len(drawn.slots),
                         "unresolved": drawn.unresolved} for drawn in draws],
            "starts": start_list(draws),
        }

    def get_start_list(*, context, **_: Any):
        rows = []
        for entry in context.event.entries.all():
            if entry.start_seconds is None:
                continue
            rows.append({
                "time": format_time_of_day(entry.start_seconds),
                "seconds": entry.start_seconds,
                "course": context.event.entry_course(entry),
                "entry": entry.reference,
                "name": entry.competitor.listed_name,
                "club": entry.competitor.club,
            })
        rows.sort(key=lambda row: (row["seconds"], row["course"], row["name"]))
        return {"count": len(rows), "starts": rows}

    router.get("/entries", list_entries)
    router.post("/entries", add_entry)
    router.get("/entries/:reference", get_entry)
    router.patch("/entries/:reference", update_entry)
    router.delete("/entries/:reference", delete_entry)
    router.get("/cards/:card", get_by_card)
    router.post("/starts/draw", draw_starts)
    router.get("/starts", get_start_list)
    return router
