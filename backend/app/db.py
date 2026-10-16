"""SQLite storage: sessions, appointment requests, handoff tickets.

Why SQLite: one file, no server to install, and the data survives a page
refresh and a server restart. That matters because handoff tickets and
appointment requests must not vanish, and the staff inbox page must see them.
For many concurrent users a real database (e.g. PostgreSQL) would replace it.

Every query uses "?" placeholders. Values are never pasted into SQL strings,
which prevents SQL injection.
"""
import json
import sqlite3
import threading
import uuid

from .config import DB_PATH, now_ist

_lock = threading.RLock()  # SQLite + threads: serialise all access through one (re-entrant) lock
_conn: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    state_json TEXT NOT NULL,
    history_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS appointment_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL UNIQUE,
    department TEXT, date TEXT, time_slot TEXT,
    patient_name TEXT, phone TEXT, booked_by TEXT, note TEXT,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS handoffs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    reason TEXT NOT NULL,
    summary TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def new_state() -> dict:
    """The structured state of one conversation. This is the bot's 'form'."""
    return {
        "mode": "normal",  # normal | emergency | crisis | handoff
        "after_emergency_reminder": False,
        "appointment": {
            "department": None, "date": None, "time_slot": None,
            "patient_name": None, "phone": None, "booked_by": None, "note": None,
            "status": "none",  # none | draft | pending_confirmation
            "reference": None,
        },
        "handoff_ticket": None,
    }


def connect(path: str | None = None) -> None:
    global _conn
    with _lock:
        _conn = sqlite3.connect(path or DB_PATH, check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
        _conn.commit()


def _db() -> sqlite3.Connection:
    if _conn is None:
        connect()
    return _conn


def _now() -> str:
    return now_ist().isoformat(timespec="seconds")


# ---- sessions ---------------------------------------------------------------

def create_session() -> str:
    sid = str(uuid.uuid4())  # random and unguessable, so it acts as a weak access token
    with _lock:
        _db().execute(
            "INSERT INTO sessions (id, created_at, updated_at, state_json, history_json) VALUES (?, ?, ?, ?, ?)",
            (sid, _now(), _now(), json.dumps(new_state()), "[]"),
        )
        _db().commit()
    return sid


def load_session(sid: str) -> tuple[dict, list] | None:
    with _lock:
        row = _db().execute("SELECT state_json, history_json FROM sessions WHERE id = ?", (sid,)).fetchone()
    if row is None:
        return None
    return json.loads(row["state_json"]), json.loads(row["history_json"])


def save_session(sid: str, state: dict, history: list) -> None:
    with _lock:
        _db().execute(
            "UPDATE sessions SET state_json = ?, history_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(state), json.dumps(history), _now(), sid),
        )
        _db().commit()


def delete_session(sid: str) -> None:
    """'Clear my conversation': removes the chat and its draft. Submitted
    requests and tickets stay, because staff may already be acting on them."""
    with _lock:
        _db().execute("DELETE FROM sessions WHERE id = ?", (sid,))
        _db().commit()


# ---- appointment requests -----------------------------------------------------

def submit_appointment(sid: str, appt: dict) -> int:
    """Insert once per session. A second call returns the existing id (idempotent)."""
    with _lock:
        row = _db().execute("SELECT id FROM appointment_requests WHERE session_id = ?", (sid,)).fetchone()
        if row:
            return row["id"]
        cur = _db().execute(
            "INSERT INTO appointment_requests (session_id, department, date, time_slot, patient_name, phone, booked_by, note, status, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending_confirmation', ?)",
            (sid, appt["department"], appt["date"], appt["time_slot"], appt["patient_name"],
             appt["phone"], appt.get("booked_by"), appt.get("note"), _now()),
        )
        _db().commit()
        return cur.lastrowid


def list_appointments() -> list[dict]:
    with _lock:
        rows = _db().execute("SELECT * FROM appointment_requests ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


# ---- handoff tickets --------------------------------------------------------------

def open_handoff(sid: str, reason: str, summary: str) -> tuple[int, bool]:
    """Create a ticket, unless this session already has an open one.
    Returns (ticket_id, created_now). This is what stops duplicate tickets
    when a patient clicks 'talk to a person' three times."""
    with _lock:
        row = _db().execute(
            "SELECT id FROM handoffs WHERE session_id = ? AND status = 'open'", (sid,)
        ).fetchone()
        if row:
            return row["id"], False
        cur = _db().execute(
            "INSERT INTO handoffs (session_id, reason, summary, status, created_at) VALUES (?, ?, ?, 'open', ?)",
            (sid, reason, summary, _now()),
        )
        _db().commit()
        return cur.lastrowid, True


def list_handoffs() -> list[dict]:
    with _lock:
        rows = _db().execute("SELECT * FROM handoffs ORDER BY id DESC").fetchall()
    return [dict(r) for r in rows]


def resolve_handoff(ticket_id: int) -> bool:
    with _lock:
        cur = _db().execute("UPDATE handoffs SET status = 'resolved' WHERE id = ? AND status = 'open'", (ticket_id,))
        _db().commit()
        return cur.rowcount == 1


def handoff_status(ticket_id: int) -> str | None:
    with _lock:
        row = _db().execute("SELECT status FROM handoffs WHERE id = ?", (ticket_id,)).fetchone()
    return row["status"] if row else None
