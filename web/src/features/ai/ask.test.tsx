import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { loggedInAs, renderApp } from "../../test/render";
import { server } from "../../test/server";

const source = {
  n: 1,
  document_id: "doc-004",
  title: "Catálogo de productos 2026",
  filename: "catalogo.pdf",
  library_id: "marketing",
  folder_id: null,
  page_from: 2,
  page_to: 2,
  snippet: "Plan Básico: soporte en horario hábil",
  score: 0.03,
};

function sse(events: [string, unknown][]) {
  return events.map(([e, d]) => `event: ${e}\ndata: ${JSON.stringify(d)}\n\n`).join("");
}

describe("Preguntar a los documentos", () => {
  it("muestra la respuesta en streaming con su cita y abre la fuente en su página", async () => {
    loggedInAs(["SHARER"]);
    let sent: Record<string, unknown> | null = null;
    server.use(
      http.get("*/api/v1/ai/status", () =>
        HttpResponse.json({ enabled: true, llm: true, chat_model: "claude-sonnet-5-5" }),
      ),
      http.get("*/api/v1/library/libraries", () => HttpResponse.json([])),
      http.post("*/api/v1/ai/ask", async ({ request }) => {
        sent = (await request.json()) as Record<string, unknown>;
        return new HttpResponse(
          sse([
            ["sources", { sources: [source] }],
            ["text", { text: "El **Plan Básico** incluye soporte en horario hábil." }],
            ["citation", { n: 1, document_id: "doc-004", page_from: 2 }],
            ["block_end", {}],
            ["done", { usage: { model: "claude-sonnet-5-5" } }],
          ]),
          { headers: { "Content-Type": "text/event-stream" } },
        );
      }),
    );
    const { router } = renderApp("/preguntar");
    expect(await screen.findByRole("link", { name: "Preguntar" })).toBeInTheDocument();
    await userEvent.type(await screen.findByLabelText("Pregunta"), "¿Qué incluye el plan básico?");
    await userEvent.click(screen.getByRole("button", { name: "Preguntar" }));

    expect(await screen.findByText("Plan Básico")).toBeInTheDocument();
    expect(screen.getByText(/incluye soporte en horario hábil/)).toBeInTheDocument();
    expect(sent).toMatchObject({ question: "¿Qué incluye el plan básico?", document_ids: [] });

    await userEvent.click(screen.getByRole("button", { name: "Fuente 1" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/documentos/marketing"));
    expect(router.state.location.search).toBe("?doc=doc-004&page=2");
  });

  it("sin IA disponible no aparece en el menú", async () => {
    loggedInAs(["SHARER"]);
    renderApp("/");
    expect(await screen.findByText(/^Hola, /)).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Preguntar" })).not.toBeInTheDocument();
  });
});
