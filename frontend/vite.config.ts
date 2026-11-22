import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// In development the API runs separately (docker-compose.local.yml publishes it
// on 127.0.0.1:8000); the page always calls it under the relative path /api.
export default defineConfig({
  plugins: [react()],
  // The page forbids data: fonts in its Content-Security-Policy, so no file is inlined.
  build: { assetsInlineLimit: 0 },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
    },
  },
});
