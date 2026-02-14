"""The event, its controls and its courses."""

from __future__ import annotations

from typing import Any

from ...courses.control import Control
from ...courses.course import Course
from ...courses.planning import check_event, summary as planning_summary
from ...errors import NotFoundError
from ...event.event import summary
from ...geo.grid import parse as parse_grid
from ...util.validate import require_mapping, require_str
from ..router import Router


def event_routes() -> Router:
    router = Router()

    def get_event(*, context, **_: Any):
        return summary(context.event)

    def get_check(*, context, **_: Any):
        problems = context.event.check_ready()
        notes = check_event(context.event.courses, context.event.controls)
        return {
            "ready": not problems,
            "problems": problems,
            "notes": [note.to_dict() for note in notes],
            "note_counts": planning_summary(notes),
        }

    def list_controls(*, context, **_: Any):
        return {"count": len(context.event.controls),
                "controls": context.event.controls.to_list()}

    def get_control(*, params, context, **_: Any):
        return context.event.controls.require(params["code"]).to_dict()

    def add_control(*, body, context, **_: Any):
        raw = require_mapping(body, "body")
        control = Control(
            code=str(raw.get("code", "")),
            position=parse_grid(require_str(raw.get("position"), "position")),
            height=raw.get("height"),
            note=str(raw.get("note") or ""),
        )
        context.event.controls.add(control)
        context.persist()
        return 201, control.to_dict()

    def list_courses(*, context, **_: Any):
        event = context.event
        rows = []
        for course in event.courses.all():
            rows.append({
                **course.to_dict(),
                "controls": course.size,
                "metres": course.length_metres(event.controls),
                "climb": course.climb_metres(event.controls),
                "classes": event.classes_on(course.name),
            })
        return {"count": len(rows), "courses": rows}

    def get_course(*, params, context, **_: Any):
        event = context.event
        course = event.courses.require(params["name"])
        return {
            **course.to_dict(),
            "metres": course.length_metres(event.controls),
            "climb": course.climb_metres(event.controls),
            "descriptions": course.describe(event.controls),
            "legs": [{"number": leg.number, "from": leg.start.code, "to": leg.finish.code,
                      "metres": round(leg.metres), "bearing": round(leg.bearing, 1)}
                     for leg in course.legs(event.controls)],
        }

    def add_course(*, body, context, **_: Any):
        raw = require_mapping(body, "body")
        course = Course.from_dict(raw)
        course.check(context.event.controls)
        context.event.courses.add(course)
        context.persist()
        return 201, course.to_dict()

    def set_class_course(*, params, body, context, **_: Any):
        raw = require_mapping(body, "body")
        course = require_str(raw.get("course"), "course")
        context.event.set_class_course(params["code"], course)
        context.persist()
        return {"class": params["code"].upper(), "course": course}

    def list_classes(*, context, **_: Any):
        return {"classes": [{"class": code, "course": course}
                            for code, course in sorted(context.event.class_courses.items())]}

    router.get("/event", get_event)
    router.get("/event/check", get_check)
    router.get("/controls", list_controls)
    router.post("/controls", add_control)
    router.get("/controls/:code", get_control)
    router.get("/courses", list_courses)
    router.post("/courses", add_course)
    router.get("/courses/:name", get_course)
    router.get("/classes", list_classes)
    router.put("/classes/:code", set_class_course)
    return router


__all__ = ["event_routes", "NotFoundError"]
