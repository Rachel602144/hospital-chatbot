# Aranya Hospital patient assistant (prototype)

A web chat assistant for a **fictional** Bengaluru hospital. It:
- answers patient and caregiver questions from approved information,
- takes appointment **requests**,
- recognises possible emergencies, and
- hands over to front-desk staff.

> **Prototype. Not clinically validated. Not for real patients.** The hospital, phone numbers and policies are invented. Emergency wording needs clinical and legal review before any real use.

| Document | What it is |
|---|---|
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | The hospital requirements I assumed |
| [docs/APPROACH_NOTE.md](docs/APPROACH_NOTE.md) | 1–2 page note: approach, edge cases, what I didn't build |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Every major decision, alternatives and trade-offs |
| [docs/HOW_IT_WORKS.md](docs/HOW_IT_WORKS.md) | One message traced through the code |
| [docs/TEST_PLAN.md](docs/TEST_PLAN.md) | Automated results + manual real-model scenarios |
| [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) | 5-minute demo |

## What works

| Feature | Status |
|---|---|
| FAQ answers from `backend/app/knowledge/hospital_info.md` only | Implemented; real-model behaviour checked manually |
| Appointment request: natural conversation, corrections, code validation, honest "request not booking" status | Implemented and tested (automated) |
| Emergency / self-harm detection in code before the AI, fixed templates, 3 levels | Implemented and tested (automated); English keywords only |
| Model-side urgent-symptom flag (second net) | Implemented; model-dependent, not validated |
| Medical-advice refusal | Prompt-based; model-dependent, checked manually |
| Human handoff (button + conversational), no duplicates, staff inbox | Implemented and tested; **staff inbox is simulated** |
| Fallback when the AI is down | Implemented and tested |
| Session isolation, input limits, rate limit, no personal data in logs | Implemented and tested |
| Real booking, patient login, Indian languages, WhatsApp | **Not built** (see approach note) |

## Run it locally (Windows PowerShell)

You need Python 3.10+ and a free Groq API key (console.groq.com → API Keys). Node is only needed if you change the frontend.

```powershell
cd hospital-assistant\backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
notepad .env          # paste your key after LLM_API_KEY=, save
python check_llm.py   # checks the AI connection
python -m pytest -q   # should say: 63 passed
uvicorn app.main:app --reload
```

Then open these pages:
- **Patient chat:** http://127.0.0.1:8000
- **Staff inbox:** http://127.0.0.1:8000/#/staff (key: `demo-staff`)

The built React app (`frontend/dist`) is included, so one Python server runs everything.

### If you change the frontend
```powershell
cd hospital-assistant\frontend
npm install
npm run dev      # http://localhost:5173, forwards /api to the Python server on :8000
npm run build    # rebuild frontend/dist before committing
```

## Configuration (`backend/.env`)

| Variable | Meaning | Default |
|---|---|---|
| `LLM_API_KEY` | Groq (or other OpenAI-compatible) key. **Never commit.** | none |
| `LLM_BASE_URL` | Provider URL | `https://api.groq.com/openai/v1` |
| `LLM_MODEL` | Model id | `openai/gpt-oss-120b` |
| `LLM_TIMEOUT_SECONDS` | Give up on the AI after this long | `20` |
| `STAFF_KEY` | Password for the staff inbox | `demo-staff` |
| `DB_PATH` | SQLite file | `backend/hospital.db` |

To switch to OpenRouter, change `LLM_BASE_URL` to `https://openrouter.ai/api/v1` and set your OpenRouter key and model. No code changes are needed.

## Deploy (Render, free tier)

1. Push the repo to GitHub. Check that `.env` is **not** in it.
2. In Render, choose New → Web Service → your repo.
   - **Root directory:** `backend`
   - **Build command:** `pip install -r requirements.txt`
   - **Start command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Health check path:** `/api/health`
3. Add the environment variables from the table above in Render's dashboard.

Free-tier caveats:
- The service sleeps after inactivity, so the first request can take about a minute (cold start).
- The SQLite file is reset on every redeploy.

Open the site once before a demo to wake it up.

## Project layout

```
backend/
  app/
    main.py        HTTP endpoints, validation, rate limit, per-session lock
    engine.py      what happens to one message: safety -> AI + tools -> guard -> fallback
    safety.py      emergency / self-harm detection (no AI) + fixed templates
    tools.py       the 4 actions the AI may request, each validated in code
    schedule.py    which department runs which day
    prompts.py     system prompt (rules + approved info + current state)
    llm.py         call to the AI provider, with timeout
    db.py          SQLite: sessions, appointment requests, handoff tickets
    config.py      settings from .env
    knowledge/hospital_info.md   approved hospital facts (fictional)
  tests/           63 automated tests (fake AI, no key needed)
  check_llm.py     quick check that your key and model work
frontend/src/
  App.jsx          patient chat
  Staff.jsx        simulated staff inbox
  api.js           all calls to the backend
docs/              requirements, approach note, decisions, tests, demo
```
