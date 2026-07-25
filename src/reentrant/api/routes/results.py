"""Downloading cards, and everything that comes out of it."""

from __future__ import annotations

from typing import Any

from ...courses.statistics import event_statistics
from ...event.download import outstanding, process, results_from
from ...event.report import build_report
from ...results.analysis import analyse_legs, leg_table, losses_for, superman_seconds
from ...results.classify import by_class, by_course, classify, counts
from ...geo.grid import parse as parse_grid
from ...geo.route import Fix, Route, compare
from ...timing.punch import CardRead, Punch
from ...timing.validate import splits
from ...util.times import format_clock, format_time_of_day, parse_time_of_day
from ...util.validate import optional, require_int, require_list, require_mapping
from ..router import Router


def _read_from(raw: dict[str, Any]) -> CardRead:
    punches = []
    for row in require_list(raw.get("punches", []), "punches"):
        entry = require_mapping(row, "punch")
        punches.append(Punch(str(entry.get("code", "")),
                             parse_time_of_day(str(entry.get("at", "")), "punch time")))
    return CardRead(
        card=require_int(raw.get("card"), "card", minimum=1),
        punches=punches,
        start_seconds=optional(raw.get("start"), lambda v: parse_time_of_day(str(v), "start")),
        finish_seconds=optional(raw.get("finish"), lambda v: parse_time_of_day(str(v), "finish")),
    )


def result_routes() -> Router:
    router = Router()

    def post_download(*, body, context, **_: Any):
        read = _read_from(require_mapping(body, "body"))
        download = process(context.event, read)
        context.downloads.append(read)
        context.processed.append(download)
        context.results = results_from(context.event, context.processed)
        context.persist()
        return 201, {
            "card": download.card,
            "name": download.name,
            "course": download.course,
            "ok": download.ok,
            "problem": download.problem,
            "seconds": download.seconds,
            "time": format_clock(download.seconds),
            "start": None if download.start_seconds is None else format_time_of_day(download.start_seconds),
            "splits": [{**row, "leg": format_clock(int(row["leg_seconds"])),
                        "elapsed": format_clock(int(row["elapsed_seconds"]))}
                       for row in download.splits],
            "slip": download.slip(),
        }

    def list_downloads(*, context, **_: Any):
        return {
            "count": len(context.processed),
            "downloads": [{"card": download.card, "name": download.name,
                           "course": download.course, "ok": download.ok,
                           "time": format_clock(download.seconds),
                           "problem": download.problem}
                          for download in context.processed],
        }

    def get_outstanding(*, context, **_: Any):
        rows = outstanding(context.event, context.processed)
        return {"count": len(rows),
                "entries": [{"entry": entry.reference,
                             "name": entry.competitor.listed_name,
                             "course": context.event.entry_course(entry),
                             "start": format_time_of_day(entry.start_seconds)
                             if entry.start_seconds is not None else None}
                            for entry in rows]}

    def get_results(*, query, context, **_: Any):
        rows = context.results or results_from(context.event, context.processed)
        blocks = by_course(rows) if query.get("by") == "course" else by_class(rows)
        return {
            "by": query.get("by") or "class",
            "counts": counts(rows),
            "blocks": [{"name": name, "results": [row.to_dict() for row in block]}
                       for name, block in sorted(blocks.items())],
        }

    def get_class_results(*, params, context, **_: Any):
        rows = context.results or results_from(context.event, context.processed)
        block = by_class(rows).get(params["code"].upper(), [])
        return {"class": params["code"].upper(),
                "results": [row.to_dict() for row in block]}

    def get_splits(*, params, context, **_: Any):
        """Splits for everybody on one course, with the analysis."""
        event = context.event
        course_name = params["name"]
        event.courses.require(course_name)

        by_entry: dict[str, list[dict[str, object]]] = {}
        names: dict[str, str] = {}
        for download in context.processed:
            if download.entry is None or download.course != course_name or not download.ok:
                continue
            by_entry[download.entry.reference] = download.splits
            names[download.entry.reference] = download.entry.competitor.listed_name

        legs = analyse_legs(by_entry)
        return {
            "course": course_name,
            "superman": format_clock(superman_seconds(legs)),
            "superman_seconds": superman_seconds(legs),
            "runners": [{
                "entry": reference,
                "name": names[reference],
                "legs": leg_table(legs, reference),
                "lost": losses_for(reference, legs),
            } for reference in sorted(by_entry, key=lambda key: names[key])],
        }

    def get_statistics(*, context, **_: Any):
        rows = context.results or results_from(context.event, context.processed)
        return {"courses": [row.to_dict()
                            for row in event_statistics(rows, context.event.class_courses)]}

    def get_report(*, context, **_: Any):
        rows = context.results or results_from(context.event, context.processed)
        return build_report(context.event, rows).to_dict()

    def post_route(*, params, body, context, **_: Any):
        """A runner's drawn route for one leg."""
        raw = require_mapping(body, "body")
        entry = context.event.entries.require(params["reference"])
        fixes = []
        for row in require_list(raw.get("fixes", []), "fixes", min_len=2):
            fix = require_mapping(row, "fix")
            fixes.append(Fix(parse_grid(str(fix.get("at_position", fix.get("position", "")))),
                             parse_time_of_day(str(fix.get("at", "")), "at")))
        route = Route(entry=entry.reference, fixes=fixes)
        context.routes = getattr(context, "routes", {})
        context.routes.setdefault(params["reference"], []).append(route)
        return 201, route.to_dict()

    def get_routes(*, params, context, **_: Any):
        routes = getattr(context, "routes", {}).get(params["reference"], [])
        return {"entry": params["reference"],
                "routes": [route.to_dict() for route in routes],
                "compared": compare(routes)}

    router.post("/entries/:reference/routes", post_route)
    router.get("/entries/:reference/routes", get_routes)
    router.get("/statistics", get_statistics)
    router.get("/report", get_report)
    router.post("/download", post_download)
    router.get("/downloads", list_downloads)
    router.get("/outstanding", get_outstanding)
    router.get("/results", get_results)
    router.get("/results/classes/:code", get_class_results)
    router.get("/splits/:name", get_splits)
    return router


__all__ = ["result_routes", "classify", "splits"]
