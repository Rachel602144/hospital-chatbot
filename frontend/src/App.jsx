import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";

// sessionStorage: kept while this browser tab is open (survives refresh),
// gone when the tab closes. Another tab or another person gets a fresh conversation.
const STORE_KEY = "aranya-chat";

const SUGGESTIONS = [
  "When is the cardiology OPD open?",
  "I'd like to request an appointment",
  "How do I prepare for a fasting blood test?",
  "What are the visiting hours?",
];

function loadStored() {
  try {
    return JSON.parse(sessionStorage.getItem(STORE_KEY)) || null;
  } catch {
    return null;
  }
}

function formatDate(iso) {
  if (!iso) return null;
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
}

// Reception hours in India time, worked out in the browser for the side panel.
function receptionStatus() {
  const ist = new Date(Date.now() + (330 + new Date().getTimezoneOffset()) * 60000);
  const day = ist.getDay(); // 0 = Sunday
  const h = ist.getHours();
  const open = day === 0 ? h >= 9 && h < 13 : h >= 8 && h < 20;
  return open ? "Reception is open now" : "Reception is closed now. Requests are picked up when it opens.";
}

function RequestStatus({ state }) {
  if (!state || state.appointment_status === "none") return null;
  const { appointment_status: status, appointment_summary: s, still_missing, appointment_reference } = state;
  const parts = [s.department, formatDate(s.date), s.time_slot].filter(Boolean).join(", ");
  if (status === "pending_confirmation") {
    return (
      <div className="request request--sent" role="status">
        <strong>Request {appointment_reference} sent to reception</strong>
        <span>{parts}. Not confirmed yet. Reception will call to confirm the time and doctor.</span>
      </div>
    );
  }
  return (
    <div className="request" role="status">
      <strong>Appointment request in progress</strong>
      <span>
        {parts || "No details yet"}
        {still_missing.length > 0 && `. Still needed: ${still_missing.map((f) => f.replace("_", " ")).join(", ")}`}
      </span>
    </div>
  );
}

export default function App() {
  const stored = loadStored();
  const [sessionId, setSessionId] = useState(stored?.sessionId || null);
  const [messages, setMessages] = useState(stored?.messages || []);
  const [botState, setBotState] = useState(stored?.botState || null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const [slow, setSlow] = useState(false);
  const [error, setError] = useState(null); // { text, retry }
  const endRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    if (!sessionId) startNew();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (sessionId) sessionStorage.setItem(STORE_KEY, JSON.stringify({ sessionId, messages, botState }));
  }, [sessionId, messages, botState]);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, sending]);

  async function startNew() {
    setError(null);
    try {
      const data = await api.newSession();
      setSessionId(data.session_id);
      setMessages([{ role: "assistant", text: data.greeting }]);
      setBotState(null);
    } catch {
      setError({
        text: "The assistant isn't reachable right now. Reception: 080-4000-1000.",
        retry: startNew,
      });
    }
  }

  async function clearConversation() {
    if (sessionId) await api.clear(sessionId).catch(() => {});
    sessionStorage.removeItem(STORE_KEY);
    setSessionId(null);
    await startNew();
    inputRef.current?.focus();
  }

  async function run(call) {
    setError(null);
    setSending(true);
    const slowTimer = setTimeout(() => setSlow(true), 6000);
    try {
      const data = await call();
      setMessages((m) => [...m, { role: "assistant", text: data.reply, mode: data.state.mode, fallback: data.fallback }]);
      setBotState(data.state);
    } catch (e) {
      if (e.status === 404) {
        setError({ text: "This conversation has expired. Start a new one to continue.", retry: clearConversation });
      } else if (e.status === 429) {
        setError({ text: "You're sending messages quickly. Wait a minute, then try again.", retry: null });
      } else {
        setError({ text: "Your message didn't go through.", retry: () => run(call) });
      }
    } finally {
      clearTimeout(slowTimer);
      setSlow(false);
      setSending(false);
      inputRef.current?.focus();
    }
  }

  function sendText(text) {
    text = text.trim();
    if (!text || sending || !sessionId) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text }]);
    run(() => api.chat(sessionId, text));
  }

  function askForPerson() {
    if (sending || !sessionId) return;
    setMessages((m) => [...m, { role: "user", text: "I'd like to talk to a person." }]);
    run(() => api.handoff(sessionId));
  }

  const inHandoff = botState?.mode === "handoff";
  const fresh = !messages.some((m) => m.role === "user");

  return (
    <div className="page">
      <a className="emergency" href="tel:108">
        <span className="emergency__lead">Medical emergency?</span>
        <span>Call 108 or come to our Emergency, open 24 hours: 080-4000-1999</span>
      </a>

      <div className="layout">
        <aside className="info">
          <div className="info__brand">
            <span className="mark" aria-hidden="true">A</span>
            <div>
              <h1>Aranya Hospital</h1>
              <p>Hebbal, Bengaluru</p>
            </div>
          </div>

          <p className={`info__status ${receptionStatus().startsWith("Reception is open") ? "is-open" : ""}`}>{receptionStatus()}</p>

          <dl className="hours">
            <div><dt>OPD</dt><dd>Mon–Sat, 9am–1pm and 4pm–7pm<br />Saturday mornings only</dd></div>
            <div><dt>Reception</dt><dd>080-4000-1000<br />Mon–Sat 8am–8pm, Sun 9am–1pm</dd></div>
            <div><dt>Emergency</dt><dd>Open 24 hours<br />080-4000-1999</dd></div>
          </dl>

          <div className="info__scope">
            <h2>This assistant can</h2>
            <ul>
              <li>answer questions about timings, departments and tests</li>
              <li>send an appointment request to reception</li>
              <li>pass you to the front desk</li>
            </ul>
            <h2>It can't</h2>
            <ul>
              <li>give medical advice or confirm appointments</li>
            </ul>
          </div>

          <p className="info__note">
            Demo prototype for a fictional hospital. <a href="#/staff">Front desk inbox</a>
          </p>
        </aside>

        <section className="chat" aria-label="Chat with the hospital assistant">
          <header className="chat__head">
            <div className="who">
              <span className="mark mark--small" aria-hidden="true">A</span>
              <div>
                <strong>Aranya assistant</strong>
                <span className="who__sub">{inHandoff ? `Front desk ticket ${botState.handoff_ticket}` : "Usually replies in a few seconds"}</span>
              </div>
            </div>
            <div className="chat__actions">
              <button className="btn btn--ghost" onClick={clearConversation} type="button">
                New conversation
              </button>
              <button className="btn btn--person" onClick={askForPerson} disabled={sending || inHandoff} type="button">
                {inHandoff ? "With front desk" : "Talk to a person"}
              </button>
            </div>
          </header>

          <div className="log" aria-live="polite">
            {messages.map((m, i) => (
              <div key={i} className={`row row--${m.role}`}>
                {m.role === "assistant" && <span className="mark mark--tiny" aria-hidden="true">A</span>}
                <div
                  className={[
                    "msg",
                    `msg--${m.role}`,
                    (m.mode === "emergency" || m.mode === "crisis") && "msg--urgent",
                    m.fallback && "msg--fallback",
                  ].filter(Boolean).join(" ")}
                >
                  {/* Plain text: React escapes it, so HTML inside a message can't run (XSS-safe). */}
                  {m.text}
                </div>
              </div>
            ))}

            {fresh && sessionId && !sending && (
              <div className="suggest" aria-label="Suggested questions">
                {SUGGESTIONS.map((s) => (
                  <button key={s} type="button" className="chip" onClick={() => sendText(s)}>
                    {s}
                  </button>
                ))}
              </div>
            )}

            {sending && (
              <div className="row row--assistant" aria-label="Assistant is replying">
                <span className="mark mark--tiny" aria-hidden="true">A</span>
                <div className="msg msg--assistant msg--typing">
                  <span className="dots"><i /><i /><i /></span>
                  {slow && <span>Taking longer than usual…</span>}
                </div>
              </div>
            )}
            <div ref={endRef} />
          </div>

          <footer className="dock">
            <RequestStatus state={botState} />
            {error && (
              <div className="error" role="alert">
                <span>{error.text}</span>
                {error.retry && (
                  <button className="btn btn--ghost" onClick={error.retry} type="button">
                    Try again
                  </button>
                )}
              </div>
            )}
            <form
              className="composer"
              onSubmit={(e) => {
                e.preventDefault();
                sendText(input);
              }}
            >
              <label htmlFor="msg" className="sr-only">Your message</label>
              <textarea
                id="msg"
                ref={inputRef}
                rows={1}
                maxLength={1000}
                value={input}
                placeholder="Type your message"
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    sendText(input);
                  }
                }}
                autoFocus
              />
              <button className="btn btn--send" type="submit" disabled={sending || !input.trim()}>
                Send
              </button>
            </form>
            <p className="fineprint">Not for medical advice. Please don't share sensitive medical details here.</p>
          </footer>
        </section>
      </div>
    </div>
  );
}
