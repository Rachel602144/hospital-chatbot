# Aranya Hospital: patient assistant

A web chat assistant for a (fictional) 250-bed hospital in Bengaluru. It answers patient questions from approved information, takes appointment requests, recognises possible emergencies, and hands over to front-desk staff. It talks like a calm receptionist, not a form.

> **Prototype.** The hospital, its phone numbers and its policies are invented. It is not clinically validated and is not for real patients. Emergency wording would need clinical and legal review before any real use.

---

## The problem

Reception phones at a busy hospital are taken up by the same questions every day: timings, which department, what to bring, how to prepare for a test, *"can I get an appointment?"*. After 8pm nobody answers at all, and appointment requests get lost.

**The person messaging is usually not the patient.** I designed for **Priya, 34**. She lives in Pune and is booking a cardiology check-up for her 72-year-old father in Bengaluru, on her phone, at 10:40pm. That one decision shaped the product:

- The bot asks for the **patient's** name, not "your name", and understands "for my dad".
- Replies are short, with **one question at a time**, because she's tired and on a phone.
- She may mention her father's symptoms halfway through booking, so **emergency handling can't depend on the conversation being "about health"**.

Full assumptions are in [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md), along with the questions I would ask the real hospital.

---

## What it does

| | |
|---|---|
| **Answers questions** | Timings, departments, test preparation, visiting hours, fees, what to bring. It answers **only** from an approved information file, and says "I can't confirm that" instead of guessing. |
| **Takes appointment requests** | Understands *"can I book for my dad friday morning"*, asks only for what's missing, and handles *"actually, make it Saturday"*. It sends a **request**; it never claims a booking. |
| **Handles emergencies** | *"He's breathless and his lips look blue"* stops everything and shows a fixed emergency message with tap-to-call buttons (108 / Emergency). Any half-finished request is kept, not lost. |
| **Refuses medical advice, kindly** | No diagnoses, doses or "should he stop his medicine". It says why, points to the doctor, and offers to add the question as a note on the appointment request. |
| **Hands over to a human** | A button that's always visible, or just saying so. It creates one ticket with a summary so staff don't re-ask, and is honest that the inbox is simulated, whether reception is open, and that it is **not** an emergency line. |
| **Fails safely** | If the AI provider is down, patients get phone numbers instead of an error page, and emergency detection and handoff still work. |

---

## The key design decision: the AI proposes, the code decides

The language model is good at **language**: understanding messy messages, handling corrections, sounding human. It isn't trustworthy for anything with **consequences**. So I split the responsibilities:

```
Patient message
     │
     ▼
1. Safety check (plain Python, runs BEFORE the AI)
     │  emergency / self-harm phrase? → fixed message, AI never called
     ▼
2. AI, given: rules + approved hospital info + the current request form + recent chat
     │  it can only ACT through 4 tools:
     │  update request · submit request · hand off to a human · flag urgent symptoms
     ▼
3. Code validates every tool call
     │  real department? runs that weekday? future date? valid phone?
     ▼
4. Code checks the reply before the patient sees it
     │  claims "booked"/"confirmed"? → replaced with the truth
     ▼
Patient sees the reply
```

**What that buys:**
- **Emergencies are handled the same way every time**, instantly, and even if the AI provider is down.
- **The AI can't create an invalid request.** Asking for Dermatology (which the hospital doesn't have), or ENT on a Monday (it runs Tue/Thu/Sat), is rejected by code, and the AI explains it to the patient.
- **The patient is never told "booked".** No "booked" status exists in the system; only code moves a request to *pending confirmation*.
- **Facts survive long conversations.** Key details live in a structured form that is re-sent every turn, not only in chat history.

**Why there's no RAG, multi-agent setup or vector database:** the hospital's information is about one page and fits in the model's context. Retrieval would add a new failure mode without solving a real problem. One model with four tools covers the job. ([`docs/DECISIONS.md`](docs/DECISIONS.md) has every decision with the alternatives and trade-offs.)

---

## Safety, in layers

| Layer | What it does | Honest limit |
|---|---|---|
| **Code keyword check** | Three levels: **emergency** (stop, fixed message) · **possible** (*"chest pain last year"* gets "if this is happening now, call 108", then continues) · **none** | English only; misses paraphrases; occasionally over-triggers |
| **AI urgent flag** | Catches paraphrases the keywords miss (*"feels like an elephant is sitting on his chest"*) and picks *emergency now* or *possibly serious* | Depends on the model; not validated |
| **Fixed templates** | Emergency and self-harm text is pre-written, never generated | Needs clinical review |
| **Output guard** | Replaces any reply that claims a booking | Pattern-based |

False alarms are accepted on purpose: showing emergency advice unnecessarily is much less harmful than missing a real emergency.

---

## What testing against the real model found

I tested every behaviour with the real model as well as with automated tests. Real testing found problems that unit tests couldn't:

| What I saw | Fix |
|---|---|
| The model "remembered" booking details in chat but never saved them, so nothing could be validated | Made tool use explicit in the prompt, and logged tools used per message to prove it |
| *"Friday"* was saved as Thursday: the model got the date arithmetic wrong, and validation passed because cardiology runs both days | The model now **looks dates up** in a calendar, and **code** computes the weekday it repeats back |
| After a request was successfully sent, a provider hiccup made the bot say *"I'm having trouble"* | If the AI fails *after* an action succeeds, code reports what actually happened |
| *"Headache and dizziness"* triggered a full emergency stop, which helped nobody | Gave the model two urgency levels: real emergencies still stop; common symptoms get a safety line plus help |
| The model asked *"who is making this request?"*, which is unnecessary | Told it to ask only for the 5 required details |

The pattern behind every fix is the same: **don't let the model do what deterministic code can do.**

---

## What's real and what's simulated

| Real | Simulated | Not built (and why) |
|---|---|---|
| Conversation, validation, safety checks, storage (SQLite), handoff tickets | The **staff inbox** (no real staff system) and the **confirmation call** | **Real booking or hospital-system integration**: there's no system to book against, and faking it would mislead patients |
| | | **Patient login / medical records**: needs real identity verification |
| | | **Symptom triage**: a clinical function that needs clinical design |
| | | **Hindi / Kannada**: the biggest real gap; the keyword safety layer is English-only, so this comes first before any pilot |

---

## Privacy

- Only the **patient's name and a phone number** are collected, and only for an appointment request. The browser never receives the phone number back.
- **Logs contain no message text or personal details.**
- Each conversation has a random ID, so sessions can't see each other. "New conversation" deletes the chat.
- The AI key lives only on the server.
- Messages are sent to a third-party AI provider. A real deployment would need a data-processing agreement, retention rules and a legal review. **No compliance is claimed.**

---

## Run it locally

You need **Python 3.10+** and a free **Groq API key** (console.groq.com → API Keys). The built frontend is included, so Node isn't needed.

```powershell
cd hospital-chatbot\backend
python -m venv .venv
.venv\Scripts\Activate.ps1          # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
Copy-Item .env.example .env         # macOS/Linux: cp .env.example .env
# open .env and paste your key after LLM_API_KEY=
python check_llm.py                 # checks the AI connection
python -m pytest -q                 # 66 passed
uvicorn app.main:app
```

- **Patient chat:** http://127.0.0.1:8000
- **Staff inbox:** http://127.0.0.1:8000/#/staff (key: `demo-staff`)

**Try these:**
- `can i book cardiology for my dad friday morning`, then `Ramesh Iyer 9876543210`, then `yes`
- Mid-booking: `he's breathless and his lips look a bit blue`
- `should he stop his blood thinners before the test?`
- `book ENT on monday`
- Click **Talk to a person** twice, then check the staff inbox.

| Setting (`backend/.env`) | Meaning | Default |
|---|---|---|
| `LLM_API_KEY` | Groq key (never commit) | none |
| `LLM_BASE_URL` | Any OpenAI-compatible provider | Groq |
| `LLM_MODEL` | Model | `openai/gpt-oss-120b` |
| `LLM_TIMEOUT_SECONDS` | Give up on the AI after this long | `20` |
| `STAFF_KEY` | Staff inbox password | `demo-staff` |

Switching provider (for example to OpenRouter) is a change to `.env`, not to code.

---

## Stack

**React** (chat UI) · **FastAPI** (Python API with automatic input validation) · **Groq, `gpt-oss-120b`** (fast, tool-calling, OpenAI-compatible) · **SQLite** (requests and tickets survive restarts, with zero setup) · **pytest** (66 tests with a scripted fake model, so they check my code rather than the model's mood).

```
backend/app/
  engine.py      what happens to one message: safety → AI + tools → guard → fallback
  safety.py      emergency / self-harm detection (no AI) + fixed messages
  tools.py       the 4 actions the AI may request, each validated in code
  schedule.py    which department runs on which day
  prompts.py     rules + approved hospital info + current state + calendar
  llm.py         AI provider call with timeout
  db.py          SQLite: conversations, requests, handoff tickets
  main.py        HTTP endpoints, input limits, rate limit
  knowledge/hospital_info.md   the approved hospital facts
frontend/src/    App.jsx (patient chat) · Staff.jsx (staff inbox) · api.js
```

---

## Documents

| | |
|---|---|
| [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) | The hospital, the user, requirements and acceptance criteria, questions for the client |
| [`docs/APPROACH_NOTE.md`](docs/APPROACH_NOTE.md) | 2-page approach note: edge cases and what I chose not to build |
| [`docs/DECISIONS.md`](docs/DECISIONS.md) | Each major decision, with the alternatives and trade-offs |
| [`docs/HOW_IT_WORKS.md`](docs/HOW_IT_WORKS.md) | One patient's messages traced through the code |
| [`docs/TEST_PLAN.md`](docs/TEST_PLAN.md) | Automated tests plus manual real-model scenarios |

---

## Next steps before any real pilot

1. Clinical and legal review of every safety message and number.
2. Hindi and Kannada support, with a safety test set in each language.
3. Integration with the hospital's appointment and helpdesk systems.
4. A data-processing agreement with the AI provider, plus retention rules.
5. Staff login for the inbox, and moving to PostgreSQL to run on more than one server.
6. A supervised pilot, measuring questions resolved without staff, handoff quality and safety misses.

---

*Built with Claude as a pair programmer. I chose the problem, the user, the scope and the safety design, tested every behaviour against the real model, and worked through the fixes listed above.*
