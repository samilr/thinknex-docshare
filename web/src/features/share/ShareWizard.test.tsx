import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import { Providers } from "../../providers";
import { server } from "../../test/server";
import { makeQueryClient } from "../../theme";
import { ShareWizard } from "./ShareWizard";

const document = {
  id: "doc-006",
  title: "Certificado de cliente",
  mime_type: "application/pdf",
  size_bytes: 1000,
  sha256: "a".repeat(64),
  version: 1,
  classification: "INTERNAL" as const,
  owner: "comercial@thinknex.example",
};

const warnReport = {
  decision: "WARN",
  reasons: ["Contiene datos personales o financieros (RUT) y sale de la organización."],
  classification: "INTERNAL",
  recipient_external: true,
  findings: [{ type: "RUT", count: 1, samples: ["********89-K"] }],
  text_extracted: true,
  engine: "rules",
  llm: null,
  llm_model: null,
  llm_input_truncated: false,
};

function renderWizard() {
  render(
    <Providers queryClient={makeQueryClient()}>
      <MemoryRouter>
        <ShareWizard document={document} opened onClose={() => {}} />
      </MemoryRouter>
    </Providers>,
  );
}

describe("ShareWizard", () => {
  it("exige confirmar los hallazgos antes de compartir", async () => {
    let sentBody: Record<string, unknown> | null = null;
    server.use(
      http.post("*/api/v1/shares/precheck", () =>
        HttpResponse.json({ document, report: warnReport }),
      ),
      http.post("*/api/v1/shares", async ({ request }) => {
        sentBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(
          {
            id: "11111111-1111-1111-1111-111111111111",
            document: {
              source_id: "doc-006",
              source_version: 1,
              title: document.title,
              sha256: document.sha256,
              classification: "INTERNAL",
            },
            recipient: { name: "María", contact: "m***@cliente.example", is_external: true },
            shared_by: "ana@thinknex.example",
            channel: "EMAIL",
            reason: "Certificado solicitado",
            status: "ACTIVE",
            created_at: new Date().toISOString(),
            expires_at: new Date(Date.now() + 72 * 3600e3).toISOString(),
            max_accesses: 3,
            access_count: 0,
            sensitivity_decision: "WARN",
            sensitivity_report: warnReport,
            notification_status: "SENT",
            revoked_at: null,
          },
          { status: 201 },
        );
      }),
    );
    renderWizard();
    await userEvent.type(await screen.findByLabelText("Nombre del destinatario"), "María");
    await userEvent.type(screen.getByLabelText("Email del destinatario"), "maria@cliente.example");
    await userEvent.type(screen.getByLabelText(/Motivo/), "Certificado solicitado");
    await userEvent.click(screen.getByRole("button", { name: "Revisar seguridad" }));

    expect(await screen.findByText("Requiere confirmación")).toBeInTheDocument();
    expect(screen.getByText("********89-K")).toBeInTheDocument();
    const share = screen.getByRole("button", { name: "Compartir" });
    expect(share).toBeDisabled();

    await userEvent.click(screen.getByLabelText(/confirmo que corresponde compartir/));
    expect(share).toBeEnabled();
    await userEvent.click(share);

    expect(await screen.findByText(/Enlace enviado a María/)).toBeInTheDocument();
    expect(sentBody).toMatchObject({
      acknowledge_sensitive: true,
      channel: "EMAIL",
      max_accesses: 3,
    });
  });

  it("impide compartir cuando la política bloquea", async () => {
    server.use(
      http.post("*/api/v1/shares/precheck", () =>
        HttpResponse.json({
          document,
          report: {
            ...warnReport,
            decision: "BLOCK",
            classification: "RESTRICTED",
            reasons: ["Documento RESTRICTED"],
          },
        }),
      ),
    );
    renderWizard();
    await userEvent.type(await screen.findByLabelText("Nombre del destinatario"), "X");
    await userEvent.type(screen.getByLabelText("Email del destinatario"), "x@otra.example");
    await userEvent.type(screen.getByLabelText(/Motivo/), "Prueba");
    await userEvent.click(screen.getByRole("button", { name: "Revisar seguridad" }));
    expect(await screen.findByText("No es posible compartir")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Compartir" })).toBeDisabled();
  });
});
