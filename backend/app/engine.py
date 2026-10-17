"""The heart of the bot: what happens to ONE patient message, in order.

  1. Safety pre-check (code).      Emergency / self-harm -> fixed template, LLM never called.
  2. Load state + history.          (done by the caller, main.py)
  3. Ask the LLM, with tools.       Loop: model asks for a tool -> code validates & runs it
                                    -> result goes back to the model -> model writes the reply.
  4. Output guard (code).           Block replies that claim a booking that didn't happen.
  5. Fallback (code).               Any LLM failure -> fixed text with phone numbers.
"""
import json
import logging
import re

from . import db, safety, tools
from .llm import LLMUnavailable
from .prompts import build_system_prompt

log = logging.getLogger("engine")

MAX_TOOL_ROUNDS = 4     # stop a confused model from looping forever
HISTORY_MESSAGES = 16   # how much recent chat text the model sees (context-window + cost control)

FALSE_CLAIM = re.compile(
    r"\b(is|are|has been|have been|been|now|all|successfully)\s+(booked|scheduled|confirmed)\b"
    r"|\bbooked (you|your|him|her|it|the)\b|\bconfirmed (your|the|his|her) appointment\b",
    re.IGNORECASE,
)


def _draft_has_details(state: dict) -> bool:
    return state["appointment"]["status"] == "draft"


def _emergency_reply(state: dict) -> str:
    state["mode"] = "emergency"
    state["after_emergency_reminder"] = True
    state["emergency_shown"] = True   # so a later handoff summary tells staff
    reply = safety.EMERGENCY_TEMPLATE
    if _draft_has_details(state):
        reply += safety.DRAFT_PARKED_LINE  # parked, not submitted, not deleted
    return reply


def _state_reply(state: dict, tools_used: list) -> str | None:
    """If the model failed after a tool already did something, describe what the
    CODE knows happened, instead of a generic error that would mislead the patient."""
    appt = state["appointment"]
    if "submit_appointment_request" in tools_used and appt["status"] == "pending_confirmation":
        return (f"Your request {appt['reference']} has been sent to reception: {appt['department']}, "
                f"{tools.readable_date(appt['date'])}, {appt['time_slot']}. It isn't confirmed yet; "
                f"reception will call {appt['phone']} to confirm the time and doctor.")
    if "request_human_handoff" in tools_used and state["handoff_ticket"]:
        return (f"I've passed this to our front desk (ticket HO-{state['handoff_ticket']:04d}). "
                "This is not an emergency line. For an emergency, call 108.")
    return None


def _plain(reply: str) -> str:
    """The chat shows plain text, so strip markdown the model may still add."""
    reply = re.sub(r"\*\*(.+?)\*\*", r"\1", reply)
    reply = re.sub(r"__(.+?)__", r"\1", reply)
    reply = re.sub(r"^#{1,6}\s*", "", reply, flags=re.MULTILINE)
    return reply


def _guard(reply: str, state: dict) -> str:
    """Code-level check on what the model wrote. The model must never tell a
    patient their appointment is booked: only reception can confirm."""
    if FALSE_CLAIM.search(reply):
        log.warning("output guard replaced a reply that claimed a booking")
        appt = state["appointment"]
        if appt["status"] == "pending_confirmation":
            return (f"Your request {appt['reference']} has been sent to reception. It isn't confirmed yet: "
                    "reception will call you to confirm the exact time and doctor.")
        return "Your appointment isn't booked yet. Let's finish the request and reception will call to confirm it."
    return reply


def handle_message(text: str, state: dict, history: list, session_id: str, llm) -> dict:
    """Returns {"reply", "level", "used_llm", "fallback", "tools"} and mutates state/history in place."""
    level = safety.classify(text)
    history.append({"role": "user", "content": text})

    # ---- 1. deterministic safety, before any AI --------------------------------------
    if level == safety.Level.SELF_HARM:
        state["mode"] = "crisis"
        state["emergency_shown"] = True
        reply = safety.SELF_HARM_TEMPLATE
        history.append({"role": "assistant", "content": reply})
        return {"reply": reply, "level": level.value, "used_llm": False, "fallback": False}

    if level == safety.Level.EMERGENCY:
        reply = _emergency_reply(state)
        history.append({"role": "assistant", "content": reply})
        return {"reply": reply, "level": level.value, "used_llm": False, "fallback": False}

    prefix = ""
    if level == safety.Level.POSSIBLE:
        prefix = safety.POSSIBLE_LINE
    elif state.get("after_emergency_reminder"):
        prefix = safety.AFTER_EMERGENCY_LINE   # repeat the urgent-care advice once
        state["after_emergency_reminder"] = False
    if state["mode"] in ("emergency", "crisis"):
        state["mode"] = "normal"

    # Leave handoff mode once staff have resolved the ticket.
    if state["mode"] == "handoff" and state["handoff_ticket"]:
        if db.handoff_status(state["handoff_ticket"]) == "resolved":
            state["mode"] = "normal"
            state["handoff_ticket"] = None

    # ---- 3. LLM with tools -----------------------------------------------------
    messages = [{"role": "system", "content": build_system_prompt(state)}]
    if level == safety.Level.POSSIBLE:
        messages[0]["content"] += ("\nNOTE: the latest message mentions a serious symptom that sounds like past history. "
                                   "The system has already shown emergency advice. Continue helping normally; "
                                   "you may add the history as an administrative note if they are requesting an appointment.\n")
    messages += history[-HISTORY_MESSAGES:]

    tools_used = []
    try:
        reply = None
        for _ in range(MAX_TOOL_ROUNDS):
            msg = llm.chat(messages, tools.TOOL_SCHEMAS)
            calls = getattr(msg, "tool_calls", None) or []
            if not calls:
                reply = (msg.content or "").strip()
                break
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": [
                    {"id": c.id, "type": "function", "function": {"name": c.function.name, "arguments": c.function.arguments}}
                    for c in calls
                ],
            })
            for c in calls:
                tools_used.append(c.function.name)
                result, urgent = tools.execute(c.function.name, c.function.arguments, state, session_id)
                if urgent:  # second, model-based safety layer
                    log.info("model flagged urgent symptoms")
                    reply = _emergency_reply(state)
                    history.append({"role": "assistant", "content": reply})
                    return {"reply": reply, "level": "emergency_model", "used_llm": True, "fallback": False}
                messages.append({"role": "tool", "tool_call_id": c.id, "content": json.dumps(result)})
        if not reply:
            raise LLMUnavailable("no final text after tool rounds")
    except LLMUnavailable as exc:
        log.error("LLM unavailable: %s", exc)
        reply = prefix + (_state_reply(state, tools_used) or safety.FALLBACK_TEMPLATE)
        history.append({"role": "assistant", "content": reply})
        return {"reply": reply, "level": level.value, "used_llm": False, "fallback": True}

    # ---- 4. output guard --------------------------------------------------------
    reply = prefix + _guard(_plain(reply), state)
    history.append({"role": "assistant", "content": reply})
    return {"reply": reply, "level": level.value, "used_llm": True, "fallback": False, "tools": tools_used}
