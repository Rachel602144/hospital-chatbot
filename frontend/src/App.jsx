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

const icon = (d) => (
  <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">{d}</svg>
);
const CHIP_ICONS = [
  icon(<><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>),
  icon(<><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M3 10h18M8 3v4M16 3v4" /></>),
  icon(<><path d="M9 3h6M10 3v6l-5 9a2 2 0 0 0 1.8 3h10.4a2 2 0 0 0 1.8-3l-5-9V3" /></>),
  icon(<><circle cx="9" cy="8" r="3" /><path d="M3 20a6 6 0 0 1 12 0M16 4a3 3 0 0 1 0 6M21 20a6 6 0 0 0-4-5.6" /></>),
];

function PersonIcon() {
  return icon(<><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>);
}

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
  return open ? "Reception is open now" : "Reception closed now. Requests are picked up when it opens.";
}

export function Logo({ size = 44 }) {
  // Aranya = "forest": a simple sprout mark instead of a letter placeholder.
  return (
    <svg className="logo" width={size} height={size} viewBox="0 0 48 48" aria-hidden="true">
      <rect width="48" height="48" rx="14" fill="var(--forest)" />
      <path d="M24 36V24" stroke="#fff" strokeWidth="3" strokeLinecap="round" />
      <path d="M24 26c-1-6-5-10-11-10 0 6 4 10 11 10z" fill="#fff" />
      <path d="M24 23c1-6 5-10 11-10 0 6-4 10-11 10z" fill="#bfe0cf" />
    </svg>
  );
}

const STEPS = [
  ["department", "Department"],
  ["date", "Date"],
  ["time_slot", "Session"],
  ["patient_name", "Patient"],
  ["phone", "Phone"],
];

function RequestStatus({ state }) {
  if (!state || state.appointment_status === "none") return null;
  const { appointment_status: status, appointment_summary: s, still_missing, appointment_reference } = state;
  const sent = status === "pending_confirmation";
  const summary = [s.department, formatDate(s.date), s.time_slot].filter(Boolean).join(", ");
  return (
    <div className={`request ${sent ? "request--sent" : ""}`} role="status">
      <div className="request__top">
        <strong>{sent ? `Request ${appointment_reference} sent to reception` : "Appointment request"}</strong>
        <span className="request__summary">{summary}</span>
      </div>
      <ol className="steps">
        {STEPS.map(([key, label]) => {
          const done = sent || !still_missing.includes(key);
          return (
            <li key={key} className={done ? "done" : ""}>
              <span className="tick" aria-hidden="true">{done ? "✓" : ""}</span>
              {label}
              <span className="sr-only">{done ? " (given)" : " (still needed)"}</span>
            </li>
          );
        })}
      </ol>
      {sent && <p className="request__note">Not confirmed yet. Reception will call to confirm the time and doctor.</p>}
    </div>
  );
}

function UrgentActions({ mode }) {
  const calls =
    mode === "crisis"
      ? [["tel:112", "Call 112"], ["tel:14416", "Tele-MANAS 14416"]]
      : [["tel:108", "Call 108 ambulance"], ["tel:08040001999", "Call our Emergency"]];
  return (
    <div className="urgent">
      <strong className="urgent__title">{mode === "crisis" ? "You don't have to deal with this alone" : "Please get urgent help now"}</strong>
      <div className="urgent__buttons">
        {calls.map(([href, label]) => (
          <a key={href} className="urgent__btn" href={href}>{label}</a>
        ))}
      </div>
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
    // Keep the newest message in view, but not on the welcome screen (it would cut off its top).
    if (!messages.some((m) => m.role === "user") && !sending) return;
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, sending]);

  async function startNew() {
    setError(null);
    try {
      const data = await api.newSession();
      setSessionId(data.session_id);
      setMessages([{ role: "assistant", text: data.greeting, at: Date.now() }]);
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
      setMessages((m) => [...m, { role: "assistant", text: data.reply, mode: data.state.mode, fallback: data.fallback, at: Date.now() }]);
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
    setMessages((m) => [...m, { role: "user", text, at: Date.now() }]);
    run(() => api.chat(sessionId, text));
  }

  function askForPerson() {
    if (sending || !sessionId) return;
    setMessages((m) => [...m, { role: "user", text: "I'd like to talk to a person.", at: Date.now() }]);
    run(() => api.handoff(sessionId));
  }

  const inHandoff = botState?.mode === "handoff";
  const fresh = !messages.some((m) => m.role === "user");
  const open = receptionStatus().startsWith("Reception is open");

  return (
    <div className="page">
      <div className="band" aria-hidden="true" />
      <nav className="topbar">
        <div className="topbar__brand">
          <Logo size={40} />
          <div>
            <strong>Aranya Hospital</strong>
            <span>Hebbal, Bengaluru</span>
          </div>
        </div>
        <a className="sos" href="tel:108">
          <span className="sos__pulse" aria-hidden="true" />
          <span className="sos__label">Medical emergency? Call 108</span>
          <span className="sos__nums">Emergency 24×7: 080-4000-1999</span>
        </a>
      </nav>

      <div className="layout">
        <aside className="info">
          <h1 className="info__title">Hospital help, at any hour.</h1>
          <p className="info__lede">
            Ask about timings and tests, request an appointment, or reach our front desk. Calm answers, no forms.
          </p>

          <div className="card">
            <p className={`status ${open ? "is-open" : ""}`}>
              <span className="status__dot" aria-hidden="true" />
              {open ? "Reception is open now" : "Reception is closed. Requests are picked up when it opens."}
            </p>
            <dl className="hours">
              <div><dt>OPD</dt><dd>Mon–Sat 9–1 and 4–7<br />Saturday mornings only</dd></div>
              <div><dt>Reception</dt><dd>080-4000-1000<br />Mon–Sat 8am–8pm, Sun 9am–1pm</dd></div>
              <div><dt>Emergency</dt><dd>Open 24 hours<br />080-4000-1999</dd></div>
            </dl>
          </div>

          <div className="card card--split">
            <div>
              <h2>The assistant can</h2>
              <ul className="ticks">
                <li>answer timings and test questions</li>
                <li>send appointment requests</li>
                <li>pass you to the front desk</li>
              </ul>
            </div>
            <div>
              <h2>It won't</h2>
              <ul className="crosses">
                <li>give medical advice</li>
                <li>confirm appointments itself</li>
              </ul>
            </div>
          </div>

          <p className="info__note">
            Demo prototype for a fictional hospital. <a href="#/staff">Front desk inbox</a>
          </p>
        </aside>

        <section className="chat" aria-label="Chat with the hospital assistant">
          <header className="chat__head">
            <div className="who">
              <Logo size={40} />
              <div>
                <strong>Aranya assistant</strong>
                <span className="who__sub">
                  <span className="online" aria-hidden="true" />
                  {inHandoff ? `Passed to front desk, ticket ${botState.handoff_ticket}` : "Online. Usually replies in a few seconds"}
                </span>
              </div>
            </div>
            <div className="chat__actions">
              <button className="btn btn--ghost" onClick={clearConversation} type="button">
                New conversation
              </button>
              <button className="btn btn--person" onClick={askForPerson} disabled={sending || inHandoff} type="button">
                <PersonIcon />
                {inHandoff ? "With front desk" : "Talk to a person"}
              </button>
            </div>
          </header>

          <div className="log" aria-live="polite">
            {fresh && sessionId && !sending ? (
              <div className="welcome">
                <Logo size={64} />
                <h2>Hello, how can I help today?</h2>
                <p>I can answer questions about timings, departments and test preparation, send an appointment request to reception, or connect you with our front desk.</p>
                <div className="suggest" aria-label="Suggested questions">
                  {SUGGESTIONS.map((s, i) => (
                    <button key={s} type="button" className="chip" onClick={() => sendText(s)}>
                      <span className="chip__icon" aria-hidden="true">{CHIP_ICONS[i]}</span>
                      <span>{s}</span>
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              messages.map((m, i) => (
                <div key={i} className={`row row--${m.role}`}>
                  {m.role === "assistant" && <Logo size={30} />}
                  <div className="bubble-wrap">
                    <div
                      className={[
                        "msg",
                        `msg--${m.role}`,
                        (m.mode === "emergency" || m.mode === "crisis") && "msg--urgent",
                        m.fallback && "msg--fallback",
                      ].filter(Boolean).join(" ")}
                    >
                      {(m.mode === "emergency" || m.mode === "crisis") && <UrgentActions mode={m.mode} />}
                      {/* Plain text: React escapes it, so HTML inside a message can't run (XSS-safe). */}
                      <span className="msg__text">{m.text}</span>
                    </div>
                    {m.at && <time className="stamp">{new Date(m.at).toLocaleTimeString("en-IN", { hour: "numeric", minute: "2-digit" })}</time>}
                  </div>
                </div>
              ))
            )}

            {sending && (
              <div className="row row--assistant" aria-label="Assistant is replying">
                <Logo size={30} />
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
                placeholder="Type your message…"
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    sendText(input);
                  }
                }}
                autoFocus
              />
              <button className="send" type="submit" disabled={sending || !input.trim()} aria-label="Send message">
                <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true">
                  <path d="M4 12l16-8-6 16-2.5-6.5L4 12z" fill="currentColor" />
                </svg>
              </button>
            </form>
            <p className="fineprint">Not for medical advice. Please don't share sensitive medical details here.</p>
          </footer>
        </section>
      </div>
    </div>
  );
}
