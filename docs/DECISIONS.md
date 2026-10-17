# Decision log

Each entry covers: what we chose, what else we considered, why, the cost of the choice, and what would make us change it.

---

### D1. Who the user is: the caregiver, not "any patient"
- **Chose:** design for an adult child arranging care for an elderly parent.
- **Why:** it's the most realistic person messaging a hospital website at night. It also forces good behaviour: ask for the *patient's* name, never assume the writer is the patient, keep replies short for a phone.
- **Cost:** some wording ("for your father") must come from the model reading context, not code.
- **Reconsider if:** the hospital's data shows most users are patients themselves.

### D2. Scope: FAQs + appointment *requests* + handoff
- **Considered:** also lab reports, billing, symptom checker, doctor directory.
- **Why:** these three cover most front-desk calls and can be built honestly in 6–8 hours. Reports and billing need patient login. A symptom checker is a clinical tool.
- **Cost:** less impressive feature list.
- **Reconsider if:** the hospital provides an appointment API (then we confirm bookings for real).

### D3. Architecture: "the model proposes, the code decides"
- **Considered:**
  - (A) one LLM call with everything in the prompt;
  - (B) a code safety check + LLM with a few validated tools + structured state;
  - (C) LangGraph multi-agent + RAG.
- **Chose:** B.
- **Why:** with A, safety and "booked or not" depend on the model obeying a prompt, and nothing can be proven. C adds latency, cost and failure points for a one-page knowledge base and three actions. B keeps language with the model and consequences with code, and everything important is testable.
- **Cost:** more code than A; the tool loop needs care (bounded at 4 rounds).
- **Reconsider if:** the knowledge grows to hundreds of documents (add retrieval) or many more workflows appear.

### D4. No RAG: the whole info file goes in the prompt
- **Why:**
  - The file is about 2.5k tokens, and the model's window is 131k.
  - The model sees *all* approved facts every time, so a fact can never be missed by bad retrieval.
- **Cost:** every call pays for those tokens (small), and the approach doesn't scale to large document sets.
- **Reconsider if:** the content goes past roughly 20–30 pages, or changes per department.

### D5. Safety check in code, before the model
- **Why:** an emergency must be handled the same way every time, instantly, and even if the AI provider is down.
- **Three levels:**
  - **EMERGENCY** stops everything and shows the fixed template.
  - **POSSIBLE** (symptom words + past/negation words) adds an "if this is happening now" line, then continues.
  - **NONE** proceeds normally.
- **Second layer:** the model can call `flag_urgent_symptoms` to catch paraphrases. It must pick a level: `emergency_now` (same fixed template as the code check) or `possibly_serious` (adds "if severe or sudden, call 108" and keeps helping). Added after real testing: "headache and dizzy" made the model trigger a full emergency stop, which helped nobody. A missing level is treated as an emergency, the safer direction.
- **Cost:**
  - Keywords miss paraphrases and non-English text (these are tested and documented as misses).
  - Keywords produce false positives. We accept those, because showing emergency advice unnecessarily is far less harmful than missing an emergency.
- **Reconsider if:** a validated multilingual classifier becomes available. It would *add to* the keywords, not replace them.

### D6. Fixed templates for safety text, not generated text
- **Why:** safety wording must be reviewed once and never drift. The LLM's wording varies run to run.
- **Cost:** the templates feel less personal.

### D7. Structured state + recent history
- **Chose:**
  - A JSON record per conversation (mode, appointment fields, status, handoff ticket).
  - The last 16 chat messages.
- **Why:**
  - Code can see exactly what's missing, so the bot asks only for that.
  - Corrections overwrite one field.
  - The model is told "trust this state over the chat".
- **Cost:** two sources of truth to keep consistent. The state wins.

### D8. Status set by code + output guard: never "booked"
- **Why:** telling a patient "booked" when nothing is booked is the most damaging honest-looking mistake.
- **How:**
  - The status `pending_confirmation` comes only from `submit_appointment_request` after validation.
  - A regex replaces any reply claiming "is booked / confirmed".
- **Cost:** the regex can over-trigger on harmless sentences. It replaces them with a correct status message, which is acceptable.

### D9. Handoff: button + model tool, one open ticket per session
- **Why:**
  - The button works without the model, so it still works during outages.
  - The model tool catches "I want a real person" in free text.
  - The "one open ticket per session" rule stops duplicates (idempotency).
- **Honesty:** the bot says the queue is simulated, whether reception is open, and that it's not an emergency line. Staff are warned if emergency advice was shown.
- **Reconsider when:** a real helpdesk exists. Then `db.open_handoff` becomes an API call to it, with retries and an acknowledgement.

### D10. Provider: Groq, `openai/gpt-oss-120b`
- **Considered:** OpenRouter free models, Gemini, Claude.
- **Why:**
  - Free tier and very fast (~500 tokens/s), which matters for a live demo.
  - Supports tool calling.
  - Uses the OpenAI-compatible format, so switching provider is a `.env` change.
  - The Llama models on our Groq account were marked Enterprise-only.
- **Cost:**
  - Free-tier rate limits.
  - Patient text goes to a third party (privacy, see D13).
- **Fallback:** `openai/gpt-oss-20b` (one line in `.env`).

### D11. FastAPI + React, served from one server
- **Why:**
  - **FastAPI:** validates requests automatically from type hints (bad input gets a 422 with no extra code), Python matches the AI libraries, and it's quick to build.
  - **React:** I already know it.
  - **One server:** in production FastAPI serves the built React files, which means one URL, no CORS setup, and one deploy.
- **Rejected:** Express. It would work, but it means writing validation by hand.

### D12. SQLite
- **Why:** appointment requests and tickets must survive a refresh and a restart, and the staff page must read them. SQLite is one file with zero setup. Queries use `?` placeholders, which block SQL injection.
- **Cost:** one server only, and on free hosting the file is wiped on redeploy.
- **Reconsider for:** multiple servers or real data, where we'd move to PostgreSQL.

### D13. Privacy choices
- **Data:**
  - Collect only the patient name and phone, only for a request.
  - The browser never receives the phone number back.
  - Logs hold metadata only.
- **Sessions:**
  - Random UUID session IDs.
  - A per-session lock stops two simultaneous messages from overwriting each other.
  - "New conversation" deletes the chat.
- **Input limits:** 1000 characters per message, 20 messages per minute per IP.
- **Not done:**
  - Encryption at rest.
  - Retention or deletion jobs.
  - Real staff authentication (a shared key stands in).
  - A data-processing agreement with the provider.
- **No compliance claims.**

### D14. Testing: fake model for code, manual script for the real model
- **Why:**
  - Automated tests must be repeatable, so they script the model's outputs and check *our* logic.
  - The real model's wording varies, so its behaviour is checked against expectations by hand (`TEST_PLAN.md`), focusing on meaning, not exact words.
