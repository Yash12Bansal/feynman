import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/ws": {
        target: "ws://localhost:8000",
        ws: true,
      },
      // v2 precompute preview server (tools/preview_server.py on :8080).
      // Explicit 127.0.0.1 avoids Node DNS resolving "localhost" to IPv6 (::1)
      // when an orphan IPv6 listener squats on the port — that bug produced
      // mysterious 404s during Phase 2 validation.
      "/lecture-api": {
        target: "http://127.0.0.1:8080",
        changeOrigin: true,
      },
      "/lecture-artifacts": {
        target: "http://127.0.0.1:8080",
        changeOrigin: true,
      },
    },
  },
});
