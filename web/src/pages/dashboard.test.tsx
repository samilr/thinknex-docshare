import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { emptyStats, loggedInAs, renderApp } from "../test/render";
import { server } from "../test/server";

const stats = {
  ...emptyStats,
  scope: "all",
  shares_total: 4,
  shares_by_status: { ACTIVE: 3, REVOKED: 1 },
  shares_by_channel: { EMAIL: 4 },
  blocked_attempts_30d: 2,
  users_active: 4,
};

function mockAudit(seen: URLSearchParams[]) {
  server.use(
    http.get("*/api/v1/stats", () => HttpResponse.json(stats)),
    http.get("*/api/v1/meta", () => HttpResponse.json({ app_env: "local" })),
    http.get("*/api/v1/audit/verify", () =>
      HttpResponse.json({
        valid: true,
        events_checked: 0,
        first_broken_event_id: null,
        last_hash: "",
      }),
    ),
    http.get("*/api/v1/audit", ({ request }) => {
      seen.push(new URL(request.url).searchParams);
      return HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 });
    }),
  );
}

describe("resumen", () => {
  it("el ADMIN abre la auditoría filtrada al tocar Bloqueos y denegaciones", async () => {
    loggedInAs(["ADMIN"], { email: "admin@thinknex.example", name: "Administrador" });
    const seen: URLSearchParams[] = [];
    mockAudit(seen);
    const { router } = renderApp("/");
    await userEvent.click(await screen.findByRole("link", { name: /^Bloqueos y denegaciones:/ }));
    expect(router.state.location.pathname).toBe("/auditoria");
    expect(await screen.findByText("Cadena de auditoría íntegra")).toBeInTheDocument();
    expect(seen.at(-1)?.get("event_type")).toBe("SHARE_BLOCKED");
  });

  it("un emisor va a sus envíos al tocar Envíos", async () => {
    loggedInAs(["SHARER"]);
    mockAudit([]);
    server.use(
      http.get("*/api/v1/stats", () => HttpResponse.json({ ...stats, scope: "mine" })),
      http.get("*/api/v1/shares", () =>
        HttpResponse.json({ items: [], total: 0, limit: 20, offset: 0 }),
      ),
    );
    const { router } = renderApp("/");
    await userEvent.click(await screen.findByRole("link", { name: /^Envíos: / }));
    expect(router.state.location.pathname).toBe("/envios");
  });
});
