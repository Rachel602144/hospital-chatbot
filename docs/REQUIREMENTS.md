# Hospital requirements (assumed)

**Everything in this document is an assumption.** No real hospital was interviewed. The hospital, its numbers, timings and policies are fictional. Where a real client would give us facts, we wrote down a reasonable guess and listed the question we would ask them (section 8).

## 1. The client

**Aranya Multispecialty Hospital, Bengaluru** (fictional).
- Private, 250 beds, about 800 outpatient (OPD) visits a day across 8 departments.
- 24-hour Emergency department.
- Reception phone line open Mon–Sat 8am–8pm, Sun 9am–1pm.

## 2. The real problem

- **Reception phones are overloaded.** We assume most calls are repetitive: timings, which department, what to bring, test preparation, "can I get an appointment".
- **Nothing happens after 8pm.** Families who can only call in the evening get no help, and appointment requests are lost or written on paper.
- **Patients arrive unprepared** (e.g. not fasting before a blood test), which wastes slots and causes repeat visits.

## 3. Who the user is

**Primary user: the caregiver.** An adult child (30–45) arranging care for an elderly parent, often from another city, on a phone, often late in the evening. Example persona: *Priya, 34, in Pune, booking a cardiology check-up for her 72-year-old father in Bengaluru at 10:40pm.*

Why this matters for the design:
- The person typing is often **not the patient** ("for my dad"). The bot asks for the *patient's* name, never assumes the writer is the patient.
- They are **busy and often anxious**. Short replies, one question at a time.
- They may describe the parent's symptoms mid-conversation, so emergency handling cannot depend on the conversation "being about health".

Secondary user: the patient themselves. Tertiary: front-desk staff who receive requests and handoffs.

## 4. What the assistant does and does not do

| Does | Does not |
|---|---|
| Answer questions from approved hospital information only | Invent doctors, prices, timings or policies |
| Take appointment **requests** and send them to reception | Confirm or book appointments (no access to a real scheduling system) |
| Give general test-preparation instructions that the hospital approved | Diagnose, interpret symptoms, or advise on medicines or doses |
| Recognise possible emergencies and send people to 108 / Emergency | Triage, or decide how serious something is |
| Hand over to front-desk staff with a summary | Pretend a human has seen the request when they haven't |
| Respond supportively to distress and give crisis contacts | Provide counselling |

## 5. Functional requirements

| ID | Requirement | Need | Priority | How it's implemented | Acceptance criterion | Test |
|---|---|---|---|---|---|---|
| R1 | Answer FAQs only from approved info | Stop hallucinated hospital facts | P0 | Full `hospital_info.md` in system prompt + "only use this" rule | Answers match the file; unknown facts get "can't confirm" + next step | `test_system_prompt_contains_approved_info`; manual M2, M3 |
| R2 | Emergency override | Don't delay urgent care | P0 | Code check (`safety.py`) before the LLM, fixed template | Emergency phrases always get the template; LLM not called; draft parked | `test_emergency_*`, `test_emergency_skips_model_and_parks_draft` |
| R3 | Past symptoms don't trigger full emergency | Avoid scaring people / blocking booking | P0 | `POSSIBLE` level adds a fixed "if this is happening now" line and continues | "chest pain last year" gets the line + normal help | `test_past_history_gets_safety_line_and_continues` |
| R4 | Self-harm response | Safety | P0 | Code check, fixed template with 112 + Tele-MANAS 14416 | Always the template; no LLM | `test_self_harm_fixed_response` |
| R5 | Refuse medical advice warmly | Patient safety | P0 | Prompt rules + offer to add question as appointment note | No diagnosis, dose, or stop/start advice | Manual M6–M8 (model-dependent) |
| R6 | Appointment request, asking only what's missing | Natural conversation | P0 | Structured state + `update_appointment_request` tool | Never re-asks a saved field; corrections overwrite one field | `test_full_request_with_correction_and_honest_status`; manual M4 |
| R7 | Validate every request in code | Model can't create invalid requests | P0 | `tools.py` + `schedule.py` | Unknown dept, wrong weekday, past date, bad phone all rejected | `test_invalid_department_*`, `test_department_not_running_*`, `test_past_date_*`, `test_bad_phone_*` |
| R8 | Never claim "booked" | Honesty | P0 | Status `pending_confirmation` set by code + output guard regex | Reply claiming a booking is replaced | `test_output_guard_blocks_false_booking_claim` |
| R9 | Human handoff with summary, no duplicates | Staff don't re-ask; no queue spam | P0 | Button endpoint (no LLM) + LLM tool; one open ticket per session | 2 clicks = 1 ticket; summary present; honest about hours; "not an emergency line" | `test_handoff_button_is_idempotent`, `test_model_handoff_and_staff_resolve_exits_handoff` |
| R10 | LLM failure fallback | Never a blank screen | P0 | Timeout + `try/except` → fixed text with phone numbers | Outage gives fallback; emergency and handoff still work | `test_llm_outage_*`, `test_emergency_still_works_during_outage`, `test_handoff_works_during_outage` |
| R11 | Session isolation | Privacy | P1 | Random UUID per conversation; state loaded by id only | Session B never sees session A's data | `test_sessions_are_isolated` |
| R12 | Input limits & rate limit | Abuse/cost control | P1 | Pydantic (1–1000 chars) + 20 msg/min/IP | Empty/huge → 422; flood → 429 | `test_empty_*`, `test_too_long_*`, `test_rate_limit` |
| R13 | Staff inbox | Make handoff visible in demo | P1 | `/#/staff` page, key-protected | Tickets and requests listed; resolve works | `test_model_handoff_and_staff_resolve_*` |
| R14 | Hindi / Kannada | Real users | P2 | **Not built** | — | Documented gap |

## 6. Non-functional requirements

- **Latency:** typical reply under ~4s (target; depends on provider).
- **Data minimisation:** only patient name and phone, only for an appointment request.
- **Logs:** no message text, names or phone numbers in logs.
- **Secrets:** AI key only on the server, never in the browser or git.
- **Availability:** degrade to a fixed fallback message, never an error page.

## 7. Success metrics (targets a pilot would measure; none measured yet)

- Share of informational questions answered without a human (target ≥ 60%).
- Handoff tickets with enough detail that staff don't re-ask (target 100%, judged by staff).
- Unsafe medical-advice replies on a safety test set (target 0).
- Appointment requests that turn into attended visits.

## 8. Questions we would ask the real hospital

1. Which questions actually fill the phone lines today? (Call logs would replace our guess.)
2. Who approves the knowledge content and how often does it change?
3. Is there an existing appointment or HIS system we should send requests to, and does it have an API?
4. Exact emergency wording and numbers approved by your clinical team?
5. Which languages do your patients use? (Kannada, Hindi, Tamil, Telugu?)
6. Where should handoffs go: a helpdesk tool, WhatsApp, a phone callback list? Who staffs it after hours?
7. Data retention: how long may chats and requests be kept? Who can access them?
8. Is it acceptable to send patient messages to a third-party AI provider? Under what contract and data location?
9. Can staff confirm a request inside the chat, or only by phone?
10. Do you want the bot on the website only, or WhatsApp too?
