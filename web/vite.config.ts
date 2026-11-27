/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const apiTarget = process.env.API_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,

    proxy: {
      "/api": { target: apiTarget, changeOrigin: false },
    },
  },
  build: { sourcemap: false, chunkSizeWarningLimit: 1200 },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    include: ["src/**/*.test.{ts,tsx}"],

    alias: { "@tabler/icons-react": "@tabler/icons-react/dist/cjs/tabler-icons-react.cjs" },
  },
});
