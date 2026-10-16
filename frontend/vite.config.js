import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the React page runs on :5173 and the Python API on :8000.
// The proxy forwards /api/* to Python, so the browser only ever talks to one origin (no CORS setup).
export default defineConfig({
  plugins: [react()],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
});
