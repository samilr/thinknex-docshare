import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

export const server = setupServer(
  http.post("*/api/v1/auth/refresh", () =>
    HttpResponse.json({ detail: "sin sesión" }, { status: 401 }),
  ),
  http.get("*/api/v1/ai/status", () =>
    HttpResponse.json({ enabled: false, llm: false, chat_model: null }),
  ),
  http.get("*/api/v1/meta", () => HttpResponse.json({ app_env: "local", version: "test" })),
);
