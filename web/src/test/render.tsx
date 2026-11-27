import { render } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { createMemoryRouter, RouterProvider } from "react-router";
import { Providers } from "../providers";
import { routes } from "../routes";
import { makeQueryClient } from "../theme";
import { server } from "./server";

export function sessionFor(roles: string[], overrides: Record<string, unknown> = {}) {
  return {
    access_token: "test-token",
    token_type: "bearer",
    expires_in: 900,
    user: {
      id: "00000000-0000-0000-0000-000000000001",
      email: "ana@thinknex.example",
      name: "Ana Rojas",
      roles,
      must_change_password: false,
      last_login_at: null,
      ...overrides,
    },
  };
}

export const emptyStats = {
  scope: "mine",
  shares_total: 0,
  shares_by_status: {},
  shares_by_channel: {},
  accesses_by_day: [],
  blocked_attempts_30d: 0,
  denied_accesses_30d: 0,
  sensitive_acknowledged: 0,
  top_documents: [],
  users_active: null,
};

export function loggedInAs(roles: string[], overrides: Record<string, unknown> = {}) {
  server.use(
    http.post("*/api/v1/auth/refresh", () => HttpResponse.json(sessionFor(roles, overrides))),
    http.get("*/api/v1/stats", () => HttpResponse.json(emptyStats)),
  );
}

export function renderApp(path = "/") {
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  return {
    router,
    ...render(
      <Providers queryClient={makeQueryClient()}>
        <RouterProvider router={router} />
      </Providers>,
    ),
  };
}
