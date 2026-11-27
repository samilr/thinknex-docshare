import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";

export const server = setupServer(
  http.post("*/api/v1/auth/refresh", () =>
    HttpResponse.json({ detail: "sin sesión" }, { status: 401 }),
  ),
);
