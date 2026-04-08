"""What the desk does that is not reading cards.

Hire cards, corrections, complaints and the board. All of it is state that
lives on the context rather than in the event file, because it is the day's
paperwork rather than the event's definition -- and because the desk laptop
crashing should lose the hire log and nothing else.
"""

from __future__ import annotations

from typing import Any

from ...entries.hire import HireBox
from ...errors import ValidationError
from ...event.download import results_from
from ...reports.board import board, leaders, state, still_out_by_course
from ...results.protest import Complaint, ComplaintBook
from ...timing.repair import Correction, CorrectionLog, apply_corrections
from ...util.times import parse_time_of_day
from ...util.validate import optional, require_int, require_list, require_mapping, require_str
from ..router import Router


def _hire_box(context) -> HireBox:
    if not hasattr(context, "hire") or context.hire is None:
        context.hire = HireBox()
    return context.hire


def _corrections(context) -> CorrectionLog:
    if not hasattr(context, "corrections") or context.corrections is None:
        context.corrections = CorrectionLog()
    return context.corrections


def _complaints(context) -> ComplaintBook:
    if not hasattr(context, "complaints") or context.complaints is None:
        context.complaints = ComplaintBook()
    return context.complaints


def _results(context):
    rows = context.results or results_from(context.event, context.processed)
    return apply_corrections(rows, _corrections(context))


def desk_routes() -> Router:
    router = Router()

    # -- hire ----------------------------------------------------------------

    def get_hire(*, context, **_: Any):
        box = _hire_box(context)
        return {"summary": box.summary(),
                "available": box.available(),
                "out": [hire.to_dict() for hire in box.still_out()]}

    def stock_hire(*, body, context, **_: Any):
        raw = require_mapping(body, "body")
        cards = [require_int(card, "card", minimum=1) for card in require_list(raw.get("cards", []), "cards")]
        box = _hire_box(context)
        box.owned = sorted(set(box.owned) | set(cards))
        return 201, {"owned": box.owned}

    def lend_card(*, body, context, **_: Any):
        raw = require_mapping(body, "body")
        entry = context.event.entries.require(require_str(raw.get("entry"), "entry"))
        hire = _hire_box(context).lend(
            require_int(raw.get("card"), "card", minimum=1),
            entry.reference,
            entry.competitor.listed_name,
            optional(raw.get("at"), lambda v: parse_time_of_day(str(v), "at")) or context.clock.seconds(),
            deposit=str(raw.get("deposit") or ""),
        )
        return 201, hire.to_dict()

    def return_card(*, params, body, context, **_: Any):
        raw = require_mapping(body or {}, "body")
        back = optional(raw.get("at"), lambda v: parse_time_of_day(str(v), "at")) or context.clock.seconds()
        return _hire_box(context).take_back(int(params["card"]), back).to_dict()

    # -- corrections ---------------------------------------------------------

    def list_corrections(*, context, **_: Any):
        return {"corrections": _corrections(context).to_list()}

    def add_correction(*, body, context, **_: Any):
        raw = require_mapping(body, "body")
        context.event.entries.require(require_str(raw.get("entry"), "entry"))
        correction = _corrections(context).add(Correction.from_dict(raw))
        return 201, correction.to_dict()

    # -- complaints ----------------------------------------------------------

    def list_complaints(*, context, **_: Any):
        book = _complaints(context)
        return {"complaints": book.to_list(), "open": [row.reference for row in book.open()]}

    def add_complaint(*, body, context, **_: Any):
        raw = require_mapping(body, "body")
        book = _complaints(context)
        complaint = Complaint(
            reference=str(raw.get("reference") or f"CMP-{len(book) + 1:04d}"),
            entry=require_str(raw.get("entry"), "entry"),
            about=require_str(raw.get("about"), "about", max_len=400),
            made_seconds=optional(raw.get("made"), lambda v: parse_time_of_day(str(v), "made"))
            or context.clock.seconds(),
            results_seconds=parse_time_of_day(require_str(raw.get("results"), "results"), "results"),
        )
        book.add(complaint)
        return 201, complaint.to_dict()

    def answer_complaint(*, params, body, context, **_: Any):
        raw = require_mapping(body, "body")
        book = _complaints(context)
        complaint = next((row for row in book.complaints if row.reference == params["reference"]), None)
        if complaint is None:
            raise ValidationError("no such complaint", reference=params["reference"])
        complaint.answer_it(
            require_str(raw.get("answer"), "answer", max_len=400),
            optional(raw.get("at"), lambda v: parse_time_of_day(str(v), "at")) or context.clock.seconds(),
        )
        return 200, complaint.to_dict()

    # -- the board -----------------------------------------------------------

    def get_board(*, query, context, **_: Any):
        rows = _results(context)
        now = context.clock.seconds()
        shown = require_int(query.get("shown", 5), "shown", minimum=1, maximum=100)
        return {
            "state": state(context.event, rows, now).to_dict(),
            "still_out": still_out_by_course(context.event, rows),
            "leaders": leaders(rows, by=query.get("by") or "class"),
            "text": board(context.event, rows, now, shown=shown),
        }

    router.get("/hire", get_hire)
    router.post("/hire/stock", stock_hire)
    router.post("/hire", lend_card)
    router.delete("/hire/:card", return_card)
    router.get("/corrections", list_corrections)
    router.post("/corrections", add_correction)
    router.get("/complaints", list_complaints)
    router.post("/complaints", add_complaint)
    router.post("/complaints/:reference/answer", answer_complaint)
    router.get("/board", get_board)
    return router
