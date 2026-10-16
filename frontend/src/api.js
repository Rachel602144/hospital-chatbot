// Every call from the browser to the Python backend goes through here.
// Note what is NOT here: the AI key. The browser never talks to the AI provider.

async function request(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    /* empty or non-JSON body */
  }
  if (!res.ok) {
    const err = new Error((data && data.detail && typeof data.detail === "string" && data.detail) || `Request failed (${res.status})`);
    err.status = res.status;
    throw err;
  }
  return data;
}

export const api = {
  newSession: () => request("/api/session", { method: "POST" }),
  chat: (session_id, message) =>
    request("/api/chat", { method: "POST", body: JSON.stringify({ session_id, message }) }),
  handoff: (session_id) =>
    request("/api/handoff", { method: "POST", body: JSON.stringify({ session_id }) }),
  clear: (session_id) => request(`/api/session/${session_id}`, { method: "DELETE" }),
  inbox: (key) => request("/api/staff/inbox", { headers: { "X-Staff-Key": key } }),
  resolve: (key, id) =>
    request(`/api/staff/handoffs/${id}/resolve`, { method: "POST", headers: { "X-Staff-Key": key } }),
};
