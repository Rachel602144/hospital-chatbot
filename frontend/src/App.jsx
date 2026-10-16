import { useEffect, useRef, useState } from "react";
import { api } from "./api.js";

// sessionStorage: kept while this browser tab is open (survives refresh),
// gone when the tab closes. Another tab or another person gets a fresh conversation.
const STORE_KEY = "aranya-chat";

function loadStored() {
  try {
    return JSON.parse(sessionStorage.getItem(STORE_KEY)) || null;
  } catch {
    return null;
  }
}

const SLOT_LABEL = { morning: "morning", evening: "evening" };

function formatDate(iso) {
  if (!iso) return null;
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" });
}

function RequestStatus({ state }) {
  if (!state) return null;
  const { appointment_status: status, appointment_summary: s, still_missing, appointment_reference } = state;
  if (status === "none") return null;
  const parts = [s.department, formatDate(s.date), SLOT_LABEL[s.time_slot]].filter(Boolean).join(", ");
  if (status === "pending_confirmation") {
    return (
      <div className="request request--sent" role="status">
        <strong>Request {appointment_reference} sent to reception</strong>
        <span>{parts}. Not confirmed yet: reception will call to confirm the time and doctor.</span>
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

  // Start a conversation if we don't have one.
  useEffect(() => {
    if (!sessionId) startNew();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Remember the conversation for this tab.
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
      setError({ text: "Couldn't reach the assistant. Check your connection, or call reception on 080-4000-1000.", retry: startNew });
    }
  }

  async function clearConversation() {
    if (sessionId) await api.clear(sessionId).catch(() => {});
    sessionStorage.removeItem(STORE_KEY);
    setSessionId(null);
    await startNew();
    inputRef.current?.focus();
  }

  async function run(call, userText) {
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
        setError({ text: "Your message didn't go through.", retry: () => run(call, userText) });
      }
    } finally {
      clearTimeout(slowTimer);
      setSlow(false);
      setSending(false);
      inputRef.current?.focus();
    }
  }

  function send(e) {
    e.preventDefault();
    const text = input.trim();
    if (!text || sending || !sessionId) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text }]);
    run(() => api.chat(sessionId, text), text);
  }

  function askForPerson() {
    if (sending || !sessionId) return;
    setMessages((m) => [...m, { role: "user", text: "I'd like to talk to a person." }]);
    run(() => api.handoff(sessionId));
  }

  const inHandoff = botState?.mode === "handoff";

  return (
    <div className="shell">
      <a className="emergency" href="tel:108">
        <span className="emergency__lead">Medical emergency?</span>
        <span>Call 108, or come to Emergency, open 24 hours: 080-4000-1999</span>
      </a>

      <header className="top">
        <div className="brand">
          <span className="brand__name">Aranya Hospital</span>
          <span className="brand__sub">Patient assistant</span>
        </div>
        <div className="top__actions">
          <button className="btn btn--quiet" onClick={clearConversation} type="button">
            New conversation
          </button>
          <button className="btn btn--person" onClick={askForPerson} disabled={sending || inHandoff} type="button">
            {inHandoff ? `With front desk (${botState.handoff_ticket})` : "Talk to a person"}
          </button>
        </div>
      </header>

      <main className="log" aria-live="polite" aria-label="Conversation">
        {messages.map((m, i) => (
          <div
            key={i}
            className={[
              "msg",
              `msg--${m.role}`,
              (m.mode === "emergency" || m.mode === "crisis") && "msg--urgent",
              m.fallback && "msg--fallback",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            {/* Rendered as plain text: React escapes it, so HTML in a message can't run (XSS-safe). */}
            {m.text}
          </div>
        ))}
        {sending && (
          <div className="msg msg--assistant msg--typing" aria-label="Assistant is replying">
            <span className="dots"><i /><i /><i /></span>
            {slow && <span className="slow">Taking longer than usual…</span>}
          </div>
        )}
        <div ref={endRef} />
      </main>

      <footer className="dock">
        <RequestStatus state={botState} />
        {error && (
          <div className="error" role="alert">
            <span>{error.text}</span>
            {error.retry && (
              <button className="btn btn--quiet" onClick={error.retry} type="button">
                Try again
              </button>
            )}
          </div>
        )}
        <form className="composer" onSubmit={send}>
          <label htmlFor="msg" className="sr-only">
            Your message
          </label>
          <textarea
            id="msg"
            ref={inputRef}
            rows={1}
            maxLength={1000}
            value={input}
            placeholder="Type your message"
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) send(e);
            }}
            autoFocus
          />
          <button className="btn btn--send" type="submit" disabled={sending || !input.trim()}>
            Send
          </button>
        </form>
        <p className="fineprint">
          Demo prototype for a fictional hospital. Not for medical advice. Please don't share sensitive medical details here.
        </p>
      </footer>
    </div>
  );
}
