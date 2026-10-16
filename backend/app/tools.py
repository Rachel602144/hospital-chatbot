"""The ONLY actions the LLM can ask for. Each one is validated here by plain code.

The model proposes ("please save date = 2026-10-19"), this file decides
(is that a real date? is that department open then?) and replies with a
result the model reads before writing its answer. The model never touches
the database directly and cannot run arbitrary code or queries.
"""
import json
import logging
import re

from . import db
from .config import now_ist
from .schedule import DEPARTMENTS, SLOTS, normalise_department, validate_slot

log = logging.getLogger("tools")

REQUIRED_FIELDS = ["department", "date", "time_slot", "patient_name", "phone"]

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "update_appointment_request",
            "description": (
                "Save or correct details of the patient's appointment request. Pass only the fields "
                "the user has just given or changed. Call it again to correct a field."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "department": {"type": "string", "description": "OPD department name"},
                    "date": {"type": "string", "description": "Preferred date as YYYY-MM-DD"},
                    "time_slot": {"type": "string", "enum": ["morning", "evening"]},
                    "patient_name": {"type": "string", "description": "Name of the patient (who will see the doctor)"},
                    "phone": {"type": "string", "description": "10-digit Indian mobile number for the callback"},
                    "booked_by": {"type": "string", "description": "Who is making the request, e.g. 'self' or 'daughter'"},
                    "note": {"type": "string", "description": "Short administrative note for reception, e.g. a question for the doctor"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "submit_appointment_request",
            "description": (
                "Send the completed appointment request to reception. Only call after all required "
                "fields are saved AND the user has confirmed the summary."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_human_handoff",
            "description": (
                "Pass the conversation to front-desk staff. Use when the user asks for a person, is "
                "very upset, or needs something you cannot do."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {"type": "string", "description": "Why a human is needed, one line"},
                    "summary": {"type": "string", "description": "What staff need to know so the user does not repeat themselves. Administrative facts only."},
                },
                "required": ["reason", "summary"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "flag_urgent_symptoms",
            "description": (
                "Call immediately if the user describes symptoms that may need emergency care right "
                "now (e.g. severe pain, breathing trouble, signs of stroke, heavy bleeding), even if phrased unusually."
            ),
            "parameters": {
                "type": "object",
                "properties": {"description": {"type": "string"}},
                "required": ["description"],
            },
        },
    },
]


def missing_fields(appt: dict) -> list[str]:
    return [f for f in REQUIRED_FIELDS if not appt.get(f)]


def _update(state: dict, args: dict) -> dict:
    appt = state["appointment"]
    if appt["status"] == "pending_confirmation":
        return {"ok": False, "error": "This request was already sent to reception. Changes must be made by calling reception."}

    saved, errors = {}, {}
    today = now_ist()

    if "department" in args and args["department"]:
        dept = normalise_department(str(args["department"]))
        if dept is None:
            errors["department"] = f"no such OPD department. Available: {', '.join(DEPARTMENTS)}"
        else:
            saved["department"] = dept

    if "time_slot" in args and args["time_slot"]:
        slot = str(args["time_slot"]).lower().strip()
        if slot not in SLOTS:
            errors["time_slot"] = "must be 'morning' or 'evening'"
        else:
            saved["time_slot"] = slot

    if "date" in args and args["date"]:
        saved["date"] = str(args["date"]).strip()

    if "patient_name" in args and args["patient_name"]:
        name = " ".join(str(args["patient_name"]).split())
        if not re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,59}", name):
            errors["patient_name"] = "name should be 2-60 letters"
        else:
            saved["patient_name"] = name

    if "phone" in args and args["phone"]:
        digits = re.sub(r"\D", "", str(args["phone"]))
        if len(digits) == 12 and digits.startswith("91"):
            digits = digits[2:]
        if not re.fullmatch(r"[6-9]\d{9}", digits):
            errors["phone"] = "must be a 10-digit Indian mobile number starting with 6-9"
        else:
            saved["phone"] = digits

    for f in ("booked_by", "note"):
        if args.get(f):
            saved[f] = str(args[f])[:200]

    # Check department + date + slot together, using values already saved where not given now.
    dept = saved.get("department", appt["department"])
    date = saved.get("date", appt["date"])
    slot = saved.get("time_slot", appt["time_slot"])
    if dept and date and "date" not in errors:
        err = validate_slot(dept, date, slot, today)
        if err:
            # Reject only the field(s) the model just tried to change.
            for f in ("date", "department", "time_slot"):
                if f in saved:
                    errors[f] = err
                    saved.pop(f)

    appt.update(saved)
    if saved and appt["status"] == "none":
        appt["status"] = "draft"
    return {"ok": not errors, "saved": saved, "errors": errors, "still_missing": missing_fields(appt)}


def _submit(state: dict, session_id: str) -> dict:
    appt = state["appointment"]
    if appt["status"] == "pending_confirmation":
        return {"ok": True, "already_submitted": True, "reference": appt["reference"]}
    missing = missing_fields(appt)
    if missing:
        return {"ok": False, "error": "cannot submit yet", "still_missing": missing}
    err = validate_slot(appt["department"], appt["date"], appt["time_slot"], now_ist())
    if err:
        return {"ok": False, "error": err}
    req_id = db.submit_appointment(session_id, appt)
    appt["status"] = "pending_confirmation"
    appt["reference"] = f"REQ-{req_id:04d}"
    return {
        "ok": True,
        "reference": appt["reference"],
        "status": "pending_confirmation",
        "meaning": "Reception has NOT confirmed yet. They will call the phone number to confirm the exact time and doctor. This is a simulated staff inbox in the demo.",
    }


def reception_open(now=None) -> bool:
    now = now or now_ist()
    if now.weekday() == 6:
        return 9 <= now.hour < 13
    return 8 <= now.hour < 20


def open_handoff(state: dict, session_id: str, reason: str, summary: str) -> dict:
    if state.get("emergency_shown"):
        summary = "ATTENTION: urgent-care advice was shown earlier in this conversation. " + summary
    ticket_id, created = db.open_handoff(session_id, reason[:200], summary[:1000])
    state["handoff_ticket"] = ticket_id
    state["mode"] = "handoff"
    return {
        "ok": True,
        "ticket": f"HO-{ticket_id:04d}",
        "duplicate": not created,
        "reception_open_now": reception_open(),
        "meaning": "Ticket is in the SIMULATED staff inbox. No staff member has replied yet. Do not say anyone has been notified by phone or will call immediately.",
    }


def execute(name: str, raw_args: str, state: dict, session_id: str) -> tuple[dict, bool]:
    """Run one tool call. Returns (result_for_model, urgent_flag_raised)."""
    try:
        args = json.loads(raw_args or "{}")
        if not isinstance(args, dict):
            raise ValueError
    except (json.JSONDecodeError, ValueError):
        return {"ok": False, "error": "arguments were not valid JSON"}, False

    log.info("tool=%s fields=%s", name, sorted(args.keys()))  # field names only, never values
    if name == "update_appointment_request":
        return _update(state, args), False
    if name == "submit_appointment_request":
        return _submit(state, session_id), False
    if name == "request_human_handoff":
        return open_handoff(state, session_id, str(args.get("reason", "")), str(args.get("summary", ""))), False
    if name == "flag_urgent_symptoms":
        return {"ok": True}, True
    return {"ok": False, "error": f"unknown tool {name}"}, False
