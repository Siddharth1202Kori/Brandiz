import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// Dev: proxy /api to FastAPI so cookies stay same-origin (SameSite=Lax works).
// Prod: Netlify rewrites /api/* to the Render API for the same reason (Phase 4).
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://localhost:8000",
      "/healthz": "http://localhost:8000",
    },
  },
});
