"""Settings, read once from environment variables (backend/.env locally).

Why a separate file: every other module imports settings from here, so there is
exactly one place that knows about environment variables.
"""
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BACKEND_DIR / ".env")

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
LLM_TIMEOUT_SECONDS = float(os.getenv("LLM_TIMEOUT_SECONDS", "20"))

DB_PATH = os.getenv("DB_PATH", str(BACKEND_DIR / "hospital.db"))
STAFF_KEY = os.getenv("STAFF_KEY", "demo-staff")

# India Standard Time as a fixed offset. A fixed offset avoids needing the
# tz database, which Windows Python does not ship with.
IST = timezone(timedelta(hours=5, minutes=30))


def now_ist() -> datetime:
    return datetime.now(IST)
