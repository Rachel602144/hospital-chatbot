import React from "react";
import { createRoot } from "react-dom/client";
import App from "./App.jsx";
import Staff from "./Staff.jsx";
import "./styles.css";

// Tiny router: /#/staff shows the simulated staff inbox, everything else is the patient chat.
function Root() {
  const [hash, setHash] = React.useState(window.location.hash);
  React.useEffect(() => {
    const onHash = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);
  return hash === "#/staff" ? <Staff /> : <App />;
}

createRoot(document.getElementById("root")).render(<Root />);
