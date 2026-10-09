import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "path";

// Browser client (deployment mode C). Reuses the shared frontend source; the
// only difference from the desktop build is that it has no Tauri runtime, so
// native client capabilities degrade to "unsupported" (see frontend/src/native.ts).
export default defineConfig({
  root: resolve(__dirname, "../../frontend"),
  plugins: [react()],
  build: {
    outDir: resolve(__dirname, "dist"),
  },
});