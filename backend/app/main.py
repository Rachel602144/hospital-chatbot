"""FastAPI app: the HTTP endpoints the React page talks to.

Endpoint map
  GET    /api/health                      is the server up? (used by hosting health checks)
  POST   /api/session                     start a new conversation -> random session id
  POST   /api/chat                        send one message, get one reply
  POST   /api/handoff                     "Talk to a person" button (works even if the LLM is down)
  DELETE /api/session/{id}                clear my conversation
  GET    /api/staff/inbox                 simulated staff inbox (needs X-Staff-Key header)
  POST   /api/staff/handoffs/{id}/resolve staff marks a ticket done
"""
import logging
import threading
import time
from collections import defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

from . import db, engine, tools
from .config import STAFF_KEY
from .llm import LLMClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("api")

app = FastAPI(title="Aranya Hospital Assistant (demo)")
db.connect()  # open the database file and create tables once, at startup
llm = LLMClient()  # tests swap this for a fake: main.llm = FakeLLM()

GREETING = (
    "Hello, I'm the Aranya Hospital assistant. I can help with OPD timings, departments, "
    "test preparation and appointment requests, or connect you with our front desk. "
    "How can I help?"
)
MAX_STORED_HISTORY = 60

# ---- request / response shapes (Pydantic validates these automatically -> 422 if wrong) ----

class ChatIn(BaseModel):
    session_id: str = Field(min_length=36, max_length=36)
    message: str = Field(max_length=1000)

    @field_validator("message")
    @classmethod
    def not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("message is empty")
        return v


class SessionIn(BaseModel):
    session_id: str = Field(min_length=36, max_length=36)


def public_state(state: dict) -> dict:
    """What the browser is allowed to see. No phone number, no name."""
    appt = state["appointment"]
    return {
        "mode": state["mode"],
        "appointment_status": appt["status"],
        "appointment_reference": appt["reference"],
        "appointment_summary": {k: appt[k] for k in ("department", "date", "time_slot")},
        "still_missing": tools.missing_fields(appt) if appt["status"] == "draft" else [],
        "handoff_ticket": f"HO-{state['handoff_ticket']:04d}" if state["handoff_ticket"] else None,
    }


# ---- tiny in-memory rate limiter: 20 messages per minute per IP --------------------------
_hits: dict[str, deque] = defaultdict(deque)
_hits_lock = threading.Lock()
RATE_LIMIT, RATE_WINDOW = 20, 60.0


def check_rate(ip: str) -> None:
    now = time.monotonic()
    with _hits_lock:
        q = _hits[ip]
        while q and now - q[0] > RATE_WINDOW:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            raise HTTPException(429, "Too many messages. Please wait a minute.")
        q.append(now)


# One lock per session: two messages for the same conversation are processed one
# after another, so the second never overwrites the first one's state.
_session_locks: dict[str, threading.Lock] = defaultdict(threading.Lock)


def _load_or_404(sid: str):
    loaded = db.load_session(sid)
    if loaded is None:
        raise HTTPException(404, "Conversation not found. Please start a new one.")
    return loaded


# ---- endpoints -----------------------------------------------------------------------

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/session")
def new_session():
    sid = db.create_session()
    return {"session_id": sid, "greeting": GREETING}


@app.post("/api/chat")
def chat(body: ChatIn, request: Request):
    # Sync (def, not async def): FastAPI runs it in a worker thread, so a slow LLM call
    # for one patient doesn't block other patients.
    check_rate(request.client.host if request.client else "unknown")
    with _session_locks[body.session_id]:
        state, history = _load_or_404(body.session_id)
        result = engine.handle_message(body.message, state, history, body.session_id, llm)
        db.save_session(body.session_id, state, history[-MAX_STORED_HISTORY:])
    log.info("session=%s level=%s llm=%s fallback=%s",
             body.session_id[:8], result["level"], result["used_llm"], result["fallback"])
    return {"reply": result["reply"], "fallback": result["fallback"], "state": public_state(state)}


@app.post("/api/handoff")
def handoff_button(body: SessionIn):
    """Deterministic 'Talk to a person'. No LLM involved, so it works during an outage."""
    with _session_locks[body.session_id]:
        state, history = _load_or_404(body.session_id)
        appt = state["appointment"]
        parts = ["Patient asked for a person via the button."]
        if appt["status"] != "none":
            parts.append(f"Appointment request ({appt['status']}): {appt['department'] or '?'} on "
                         f"{appt['date'] or '?'} {appt['time_slot'] or ''}, patient {appt['patient_name'] or '?'}, "
                         f"phone {appt['phone'] or 'not given'}.")
        recent = [m["content"][:200] for m in history if m["role"] == "user"][-3:]
        if recent:
            parts.append("Recent messages: " + " | ".join(recent))
        res = tools.open_handoff(state, body.session_id, "Button: talk to a person", " ".join(parts))
        open_now = res["reception_open_now"]
        reply = (
            f"I've passed this conversation to our front desk (ticket {res['ticket']}), so you won't need to repeat yourself. "
            + ("They're open now and will reply here or call you. " if open_now else
               "Reception is closed right now; they'll pick it up when they open at 8am (9am on Sunday). ")
            + "Demo note: this goes to a simulated staff inbox. "
            "This is not an emergency line. For an emergency, call 108."
        )
        if res["duplicate"]:
            reply = f"You're already in the queue (ticket {res['ticket']}), no need to request again. For an emergency, call 108."
        history.append({"role": "assistant", "content": reply})
        db.save_session(body.session_id, state, history[-MAX_STORED_HISTORY:])
    return {"reply": reply, "fallback": False, "state": public_state(state)}


@app.delete("/api/session/{sid}")
def clear_session(sid: str):
    db.delete_session(sid)
    return {"deleted": True}


def _staff(key: str | None):
    if key != STAFF_KEY:
        raise HTTPException(401, "Staff key required")


@app.get("/api/staff/inbox")
def staff_inbox(x_staff_key: str | None = Header(default=None)):
    _staff(x_staff_key)
    return {"handoffs": db.list_handoffs(), "appointments": db.list_appointments()}


@app.post("/api/staff/handoffs/{ticket_id}/resolve")
def staff_resolve(ticket_id: int, x_staff_key: str | None = Header(default=None)):
    _staff(x_staff_key)
    if not db.resolve_handoff(ticket_id):
        raise HTTPException(404, "No open ticket with that id")
    return {"resolved": True}


# ---- serve the built React app (one server, one URL, no CORS needed) ---------------------
DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404)
        return FileResponse(DIST / "index.html")
