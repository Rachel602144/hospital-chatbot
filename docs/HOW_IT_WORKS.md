# How it works, in plain words

Read this with the code open next to it. Every section names the exact file and function.

## The one-sentence version

> **The AI handles language. My code handles anything with consequences.**

The AI understands "can i book for my dad thurs". My code decides whether that's allowed, saves it, catches emergencies, and makes sure the bot never lies about a booking.

## The map

```
Browser (React)                     frontend/src/App.jsx  -> what Priya sees
   |   POST /api/chat {session_id, message}         (frontend/src/api.js)
   v
FastAPI server                      backend/app/main.py   -> the front door
   |   checks input, rate limit, loads this conversation from SQLite
   v
engine.handle_message()             backend/app/engine.py -> the brain, in order:
   1. safety.classify()             backend/app/safety.py  -> emergency? (no AI)
   2. build_system_prompt()         backend/app/prompts.py -> rules + hospital info + state
   3. llm.chat()                    backend/app/llm.py     -> phone call to Groq
   4. tools.execute()               backend/app/tools.py   -> validate & do what the AI asked
   5. _guard()                      engine.py              -> block "it's booked" lies
   |
   v   saves state to SQLite        backend/app/db.py
reply goes back to the browser
```

The other two files:
- `knowledge/hospital_info.md` is the hospital's approved facts, which the bot is allowed to repeat.
- `schedule.py` says which department runs on which day. The code checks requests against it.

---

## Follow Priya, one message at a time

### Opening the page
- `App.jsx` runs `startNew()`, which calls `POST /api/session`.
- `main.py: new_session()` calls `db.create_session()`, which makes a **random ID** like `9b7e5931-...` and an empty **state** record:
```json
{ "mode": "normal",
  "appointment": { "department": null, "date": null, "time_slot": null,
                   "patient_name": null, "phone": null, "status": "none" },
  "handoff_ticket": null }
```
- The browser keeps the ID in `sessionStorage`, so a refresh keeps the chat but a new tab starts fresh.

**Why a random ID?** It's how the server knows which conversation a message belongs to. Because the ID is random, nobody can guess someone else's.

### Message 1: "hi what time does cardiology opd open"
1. `main.py: chat()`
   - **Pydantic** (`ChatIn`) checks the message isn't empty and is ≤ 1000 characters. If not, it sends back **422** automatically.
   - `check_rate()` allows 20 messages per minute per person (otherwise **429**).
   - `_load_or_404()` fetches this conversation's state and history (unknown ID: **404**).
2. `engine.handle_message()`
   - `safety.classify("hi what time...")` returns `NONE`, so the AI is used.
   - `build_system_prompt(state)` builds the hidden instructions: the rules, today's date, whether reception is open, the current state, and the **whole** hospital info file.
   - `llm.chat(messages, TOOL_SCHEMAS)` sends everything to Groq. The model answers in text: "Cardiology OPD runs Monday to Saturday…"
   - `_guard()` checks the reply doesn't claim a booking. It doesn't, so it's fine.
3. The state and history are saved, and the reply goes back to the browser.

**Why the whole file and not RAG?** It's one page, and the model can read 131k tokens at once. It always sees every fact, so nothing can be "retrieved wrong".

### Message 2: "can i book for my dad friday"
- The model doesn't reply with text. It asks to use a **tool**:
```json
{"name": "update_appointment_request",
 "arguments": {"department": "Cardiology", "date": "2026-10-23", "booked_by": "daughter"}}
```
- The loop in `engine.py` sees `tool_calls` and runs `tools.execute()`, which runs `_update()`:
  - `normalise_department("Cardiology")` returns `"Cardiology"`, a real department. ✅
  - `validate_slot("Cardiology", "2026-10-23", ...)`: is it in the future, within 30 days, not a Sunday, does Cardiology run on Fridays? ✅
  - It saves into `state["appointment"]` and sets status to `draft`.
  - It returns `{"ok": true, "still_missing": ["time_slot", "patient_name", "phone"]}` **to the model**.
- The model reads that result and writes: "Sure, Friday for your father. Morning or evening?"

**This is the key idea:** the model *proposed* "save Friday". The **code** checked and saved it. If the model had said "Dermatology", `_update()` would reply `"no such OPD department"`, and the model would tell Priya kindly.

The loop runs at most `MAX_TOOL_ROUNDS = 4` times, so a confused model can't loop forever.

### Message 3: "actually friday is better, morning"
- The model calls `update_appointment_request(date=..., time_slot="morning")`. **One field is overwritten.** Nothing else changes.
- The state is also put in the prompt with the words *"trust this over the chat history"*, so the model doesn't get confused by the old date earlier in the chat.

### Message 4: "Ramesh Iyer, +91 98765 43210"
- `_update()` cleans up the phone number (`+91 98765 43210` becomes `9876543210`) and checks it's a real Indian mobile format.
- Now `still_missing` is empty. The prompt tells the model to show a summary and **ask before sending**.

### Message 5: "yes send it"
- The model calls `submit_appointment_request`, which runs `_submit()`:
  - It refuses if anything is missing.
  - It re-checks the date.
  - `db.submit_appointment()` inserts **one** row per session. A second call returns the same row, so it can never create duplicates.
  - Status becomes **`pending_confirmation`** and the reference `REQ-0001` is created.
- The model says "I've sent the request; reception will call to confirm."
- **If the model ever wrote "your appointment is booked",** `_guard()` would replace it. The word "booked" can only be true if reception confirms, and they haven't.

### Message 6: "he's been breathless since morning and his lips look a bit blue"
- `safety.classify()` matches `breathless` and `lips look a bit blue`, plus "since morning", which signals it's **happening now**. The result is **EMERGENCY**.
- `engine.py` returns `EMERGENCY_TEMPLATE` **straight away. The AI is never called.**
  - The mode becomes `emergency`.
  - The appointment draft is **kept, not sent and not deleted**.
- The next normal message gets the advice repeated once ("Before we continue…"), then normal service resumes.

**Why code and not the AI?**
- It's the same answer every time.
- It's instant.
- It works even if Groq is down.
- It's provable with a test.

**Its weakness:** it only knows the phrases in the list. "Elephant sitting on his chest" isn't in the list. That's why the model also has `flag_urgent_symptoms` as a second net. Neither is perfect, and we say so.

**The middle level, POSSIBLE:** "chest pain *last year*" matches a symptom **and** a past-time phrase. The bot doesn't panic, and it doesn't ignore it either. It adds "If this is happening now, call 108…" and then carries on.

### Message 7: "I just want to talk to a real person"
Two routes lead to the same function, `tools.open_handoff()`:
- **The button** calls `POST /api/handoff`, which builds the summary in code. No AI is involved, so it works during an outage.
- **Free text** makes the model call `request_human_handoff(reason, summary)`.

Then `db.open_handoff()`:
- If this session already has an open ticket, it returns that one. This is **idempotency**: clicking 3 times still gives 1 ticket.
- If an emergency was shown earlier, the summary starts with "ATTENTION…" so staff check on the patient first.

The reply is honest about four things:
- The ticket number.
- Whether reception is open now.
- That the inbox is **simulated**.
- That it's **not an emergency line**.

Staff see it at `/#/staff` (key: `demo-staff`). When they click *Mark resolved*, the next message puts the chat back in normal mode.

### When Groq is down or the key is wrong
- `llm.py` gives up after `LLM_TIMEOUT_SECONDS` (20s, with 1 retry) and raises `LLMUnavailable`.
- `engine.py` catches it and returns `FALLBACK_TEMPLATE` (reception and emergency numbers).
- The browser shows it in a dashed bubble.
- **No error page, no blank screen.** Emergency detection and the handoff button still work, because they don't use the AI.

---

## Where things live (they will ask)

| Thing | Where | Survives refresh? | Survives server restart? |
|---|---|---|---|
| Session ID + messages shown on screen | Browser `sessionStorage` | Yes (same tab) | Yes |
| State (appointment fields, mode) | SQLite `sessions` table | Yes | Yes (SQLite file) |
| Chat history (last 60 stored, last 16 sent to model) | SQLite `sessions` table | Yes | Yes |
| Submitted requests, handoff tickets | SQLite tables | Yes | Yes. **But** on free hosting (Render) the file is wiped on redeploy |
| AI key | `backend/.env` on the server only | n/a | n/a |
| What the model "remembers" | Nothing. Each call we resend rules, info, state and recent history | — | — |

**The model has no memory of its own.** Every call is fresh, and "memory" is us resending the state and recent chat each time.

## Words you must be able to explain

- **API / endpoint:** a URL the browser can send data to, e.g. `POST /api/chat`.
- **HTTP status codes:**
  - 200 OK
  - 401 not allowed (staff key)
  - 404 not found (unknown session)
  - 422 your input was invalid (Pydantic)
  - 429 too many requests
  - 500 server crashed. We avoid sending this for LLM problems; we send a normal 200 with the fallback text instead.
- **System prompt:** hidden instructions sent with every call. They shape behaviour but **don't guarantee** it.
- **Temperature 0.3:** low randomness, for more consistent answers.
- **Token:** about ¾ of a word. The model's limits and costs are counted in tokens.
- **Context window:** how many tokens the model can read at once (131k here).
- **Tool calling:** the model returns structured JSON asking for an action instead of text. Our code decides whether to do it.
- **Hallucination:** the model stating something that isn't true or isn't in its sources. Countered by the approved-info-only rule, validation in code, and the output guard. **Not eliminated.**
- **Prompt injection:** a user trying to override the rules ("ignore previous instructions…"). Countered by keeping the important rules in code, not in the prompt.
- **Idempotent:** doing it twice has the same effect as once (the handoff ticket, the submit).
- **Environment variable / `.env`:** settings and secrets kept outside the code and out of git.
- **CORS:** a browser rule about calling a different domain. We avoid it by serving React and the API from the same server (and through the Vite proxy in development).
