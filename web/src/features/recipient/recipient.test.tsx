import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { renderApp } from "../../test/render";
import { server } from "../../test/server";

const TOKEN = "tok_ABCDEFGHIJKL";
const expires = new Date(Date.now() + 3 * 24 * 3600e3).toISOString();

function view(permission: "VIEW" | "DOWNLOAD" | "EDIT") {
  return {
    title: "Propuesta comercial",
    mime_type: "application/pdf",
    kind: "pdf",
    version: 2,
    live: permission === "EDIT",
    page_count: 2,
    permission,
    can_download: permission !== "VIEW",
    can_edit: permission === "EDIT",
    viewer_label: "Pedro Externo",
    watermark: true,
  };
}

function mockAccess(opts: { audience: "SPECIFIC" | "ANYONE"; permission: "VIEW" | "EDIT" }) {
  const session = {
    access_token: "sess",
    token_type: "bearer",
    expires_in: 1800,
    remaining_accesses: 2,
  };
  server.use(
    http.get(`*/api/v1/access/${TOKEN}`, () =>
      HttpResponse.json({
        shared_by: "Ana Rojas",
        audience: opts.audience,
        permission: opts.permission,
        requires_code: opts.audience === "SPECIFIC",
        destination: opts.audience === "SPECIFIC" ? "p***@cliente.example" : null,
        document_title: opts.audience === "ANYONE" ? "Propuesta comercial" : null,
        expires_at: expires,
      }),
    ),
    http.post(`*/api/v1/access/${TOKEN}/open`, () => HttpResponse.json(session)),
    http.post(`*/api/v1/access/${TOKEN}/otp`, () =>
      HttpResponse.json({ sent_to: "p***@cliente.example", expires_in_seconds: 600 }),
    ),
    http.post(`*/api/v1/access/${TOKEN}/verify`, async ({ request }) => {
      const { code } = (await request.json()) as { code: string };
      return code === "123456"
        ? HttpResponse.json(session)
        : HttpResponse.json({ title: "Código incorrecto", remaining_attempts: 4 }, { status: 401 });
    }),
    http.get(`*/api/v1/access/${TOKEN}/document`, ({ request }) =>
      request.headers.get("Authorization") === "Bearer sess"
        ? HttpResponse.json(view(opts.permission))
        : HttpResponse.json({ title: "Enlace no disponible" }, { status: 404 }),
    ),
    http.get(`*/api/v1/access/${TOKEN}/pages/:n`, () =>
      HttpResponse.arrayBuffer(new Uint8Array([137, 80, 78, 71]).buffer, {
        headers: { "Content-Type": "image/png" },
      }),
    ),
  );
}

beforeAll(() => {
  URL.createObjectURL = vi.fn(() => "blob:page");
  URL.revokeObjectURL = vi.fn();
});

describe("Visor del destinatario", () => {
  it("enlace para cualquiera de solo lectura: abre sin código y no ofrece descarga", async () => {
    mockAccess({ audience: "ANYONE", permission: "VIEW" });
    renderApp(`/s/${TOKEN}`);
    expect(await screen.findByText("Ana Rojas compartió un documento contigo")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Abrir documento" }));

    expect(await screen.findByText(/v2 · Pedro Externo/)).toBeInTheDocument();
    await waitFor(() => expect(screen.getAllByRole("img", { name: /Página/ })).toHaveLength(2));
    expect(screen.queryByRole("button", { name: "Descargar" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Subir versión" })).not.toBeInTheDocument();
    expect(screen.getByText("Solo ver")).toBeInTheDocument();
  });

  it("persona específica con permiso de edición: verifica el código y puede subir versión", async () => {
    mockAccess({ audience: "SPECIFIC", permission: "EDIT" });
    renderApp(`/s/${TOKEN}`);
    expect(await screen.findByText(/p\*\*\*@cliente\.example/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Enviarme el código" }));
    const first = (await screen.findAllByRole("textbox"))[0]!;
    await userEvent.click(first);
    await userEvent.keyboard("000000");
    expect(await screen.findByText(/Te quedan 4 intento/)).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("textbox")[0]!);
    await userEvent.keyboard("123456");

    expect(await screen.findByRole("button", { name: "Subir versión" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Descargar" })).toBeInTheDocument();
    expect(screen.getByText(/v2 vigente/)).toBeInTheDocument();
  });

  it("muestra 'Enlace no disponible' ante un enlace inválido", async () => {
    server.use(
      http.get(`*/api/v1/access/${TOKEN}`, () =>
        HttpResponse.json({ title: "Enlace no disponible" }, { status: 404 }),
      ),
    );
    renderApp(`/s/${TOKEN}`);
    expect(await screen.findByText("Enlace no disponible")).toBeInTheDocument();
  });
});
