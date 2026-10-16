import { useEffect, useState } from "react";
import { api } from "./api.js";

// SIMULATED staff inbox. In a real hospital these tickets would go to their
// helpdesk / CRM, behind proper staff login. Here a shared key stands in for that.
export default function Staff() {
  const [key, setKey] = useState(sessionStorage.getItem("aranya-staff-key") || "");
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);

  async function load(k = key) {
    setError(null);
    try {
      setData(await api.inbox(k));
      sessionStorage.setItem("aranya-staff-key", k);
    } catch (e) {
      setData(null);
      setError(e.status === 401 ? "Wrong staff key." : "Couldn't load the inbox.");
    }
  }

  useEffect(() => {
    if (key) load();
    const t = setInterval(() => key && load(), 5000); // refresh every 5s
    return () => clearInterval(t);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  async function resolve(id) {
    await api.resolve(key, id).catch(() => {});
    load();
  }

  return (
    <div className="staff">
      <header className="staff__head">
        <h1>Front desk inbox</h1>
        <p>Simulated for the demo. Nothing here reaches a real person or phone.</p>
        <a href="#/">Back to patient chat</a>
      </header>

      {!data && (
        <form
          className="staff__login"
          onSubmit={(e) => {
            e.preventDefault();
            load();
          }}
        >
          <label htmlFor="key">Staff key</label>
          <input id="key" type="password" value={key} onChange={(e) => setKey(e.target.value)} />
          <button className="btn btn--person" type="submit">Open inbox</button>
          {error && <p className="error">{error}</p>}
        </form>
      )}

      {data && (
        <>
          <section>
            <h2>Handoff requests</h2>
            {data.handoffs.length === 0 && <p className="empty">No one is waiting for a person.</p>}
            {data.handoffs.map((h) => (
              <article key={h.id} className={`ticket ${h.status === "open" ? "ticket--open" : ""}`}>
                <div className="ticket__row">
                  <strong>HO-{String(h.id).padStart(4, "0")}</strong>
                  <span>{h.status === "open" ? "Waiting" : "Resolved"}</span>
                  <span className="ticket__time">{h.created_at.replace("T", " ").slice(0, 16)}</span>
                </div>
                <p className="ticket__reason">{h.reason}</p>
                <p>{h.summary}</p>
                {h.status === "open" && (
                  <button className="btn btn--quiet" onClick={() => resolve(h.id)} type="button">
                    Mark resolved
                  </button>
                )}
              </article>
            ))}
          </section>

          <section>
            <h2>Appointment requests</h2>
            {data.appointments.length === 0 && <p className="empty">No appointment requests yet.</p>}
            {data.appointments.length > 0 && (
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Ref</th><th>Department</th><th>Date</th><th>Slot</th><th>Patient</th><th>Phone</th><th>Note</th><th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.appointments.map((a) => (
                      <tr key={a.id}>
                        <td>REQ-{String(a.id).padStart(4, "0")}</td>
                        <td>{a.department}</td>
                        <td>{a.date}</td>
                        <td>{a.time_slot}</td>
                        <td>{a.patient_name}{a.booked_by ? ` (via ${a.booked_by})` : ""}</td>
                        <td>{a.phone}</td>
                        <td>{a.note || ""}</td>
                        <td>To call back</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      )}
    </div>
  );
}
