import { defineConfig, devices } from "@playwright/test";

/** Prueba de humo contra el stack levantado con `make up` (http://localhost:8080). */
export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 15_000 }, // margen para arranques en frío (Cloud Run escala a cero)
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: process.env.BASE_URL ?? "http://localhost:8080",
    locale: "es-CL",
    screenshot: "only-on-failure",
    trace: "retain-on-failure",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"] } }],
});
