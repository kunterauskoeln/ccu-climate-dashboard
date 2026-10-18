import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Same public build shape as the previous CRA setup, so Dockerfile and
// nginx.conf (which cache /static/ as immutable) don't need to change.
export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "build",
    assetsDir: "static",
  },
  server: {
    port: 3000,
  },
});
