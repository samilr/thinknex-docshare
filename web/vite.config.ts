/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const apiTarget = process.env.API_URL ?? "http://localhost:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Mismo origen en desarrollo: el navegador habla solo con Vite, que reenvía al backend.
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
    // El barrel ESM de tabler importa ~6.000 archivos; en tests se usa el bundle CJS único.
    alias: { "@tabler/icons-react": "@tabler/icons-react/dist/cjs/tabler-icons-react.cjs" },
  },
});
