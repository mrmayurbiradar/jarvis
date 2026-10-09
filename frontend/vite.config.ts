import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Shared frontend (desktop + web). The desktop shell (apps/desktop) loads the
// build output; the web client serves the same bundle in Remote mode.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 1420, // default Tauri dev port
    strictPort: true,
  },
  build: {
    outDir: "dist",
  },
});