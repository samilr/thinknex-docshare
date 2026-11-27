import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { loggedInAs, renderApp } from "../../test/render";
import { server } from "../../test/server";

const CONV = "11111111-2222-3333-4444-555555555555";
const SHARE = "99999999-8888-7777-6666-555555555555";
const source = {
  n: 1,
  document_id: "doc-004",
  title: "Catálogo de productos 2026",
  library_id: "marketing",
  folder_id: null,
  page_from: 1,
  page_to: 1,
};

function sse(events: [string, unknown][]) {
  return events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join("");
}

function aiOn() {
  server.use(
    http.get("*/api/v1/ai/status", () =>
      HttpResponse.json({ enabled: true, llm: true, chat_model: "claude-sonnet-5-5" }),
    ),
  );
}

describe("asistente", () => {
  it("botón flotante: sugerencias, respuesta con cita y propuesta que se confirma", async () => {
    loggedInAs(["SHARER"]);
    aiOn();
    let chatBody: Record<string, unknown> | null = null;
    let revoked = false;
    let outcome: Record<string, unknown> | null = null;
    server.use(
      http.post("*/api/v1/ai/chat", async ({ request }) => {
        chatBody = (await request.json()) as Record<string, unknown>;
        return new HttpResponse(
          sse([
            ["conversation", { id: CONV, title: "Resume mis envíos activos" }],
            ["thinking", { tool: "listar_envios" }],
            ["step", { tool: "listar_envios", label: "Revisó los envíos", error: false }],
            ["text", { text: "Tienes un envío activo del **catálogo**." }],
            ["citation", { n: 1, source }],
            ["block_end", {}],
            [
              "proposal",
              {
                id: "p1",
                kind: "revoke",
                summary: "Revocar el envío del catálogo a Pedro",
                data: { share_id: SHARE },
              },
            ],
            ["done", { conversation_id: CONV }],
          ]),
          { headers: { "Content-Type": "text/event-stream" } },
        );
      }),
      http.get("*/api/v1/ai/conversations", () => HttpResponse.json([])),
      http.post(`*/api/v1/shares/${SHARE}/revoke`, () => {
        revoked = true;
        return HttpResponse.json({ id: SHARE });
      }),
      http.post(`*/api/v1/ai/conversations/${CONV}/proposals/p1`, async ({ request }) => {
        outcome = (await request.json()) as Record<string, unknown>;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderApp("/");
    await userEvent.click(await screen.findByRole("button", { name: "Abrir asistente" }));
    const drawer = await screen.findByRole("dialog");
    await userEvent.click(
      within(drawer).getByRole("button", { name: "Resume mis envíos activos" }),
    );

    expect(await within(drawer).findByText("catálogo")).toBeInTheDocument();
    expect(within(drawer).getByText("Revisó los envíos")).toBeInTheDocument();
    expect(within(drawer).getByRole("button", { name: "Fuente 1" })).toBeInTheDocument();
    expect(chatBody).toMatchObject({ message: "Resume mis envíos activos", conversation_id: null });
    expect((chatBody as unknown as { context: { path: string } }).context.path).toBe("/");

    await userEvent.click(within(drawer).getByRole("button", { name: "Revocar" }));
    expect(await within(drawer).findByText("Confirmada")).toBeInTheDocument();
    expect(revoked).toBe(true);
    await waitFor(() => expect(outcome).toMatchObject({ status: "confirmed" }));
  });

  it("la página del asistente lista y abre conversaciones guardadas", async () => {
    loggedInAs(["SHARER"]);
    aiOn();
    server.use(
      http.get("*/api/v1/ai/conversations", () =>
        HttpResponse.json([
          { id: CONV, title: "Planes del catálogo", updated_at: new Date().toISOString() },
        ]),
      ),
      http.get(`*/api/v1/ai/conversations/${CONV}`, () =>
        HttpResponse.json({
          id: CONV,
          title: "Planes del catálogo",
          updated_at: new Date().toISOString(),
          messages: [
            { id: 1, role: "user", display: { text: "¿Qué planes hay?" }, created_at: "" },
            {
              id: 4,
              role: "assistant",
              display: {
                parts: [{ text: "Hay tres planes.", cites: [1] }],
                sources: [source],
                steps: ["Buscó «planes»"],
                proposals: [],
              },
              created_at: "",
            },
          ],
        }),
      ),
    );
    const { router } = renderApp("/asistente");
    await userEvent.click(await screen.findByText("Planes del catálogo"));
    expect(await screen.findByText("Hay tres planes.")).toBeInTheDocument();
    expect(screen.getByText("¿Qué planes hay?")).toBeInTheDocument();
    expect(router.state.location.search).toBe(`?c=${CONV}`);
    expect(screen.queryByRole("button", { name: "Abrir asistente" })).not.toBeInTheDocument();
  });

  it("sin IA no hay botón flotante ni entrada en el menú", async () => {
    loggedInAs(["SHARER"]);
    renderApp("/");
    expect(await screen.findByText(/^Hola, /)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Abrir asistente" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Asistente" })).not.toBeInTheDocument();
  });
});
