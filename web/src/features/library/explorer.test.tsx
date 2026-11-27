import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { loggedInAs, renderApp } from "../../test/render";
import { server } from "../../test/server";

const now = new Date().toISOString();
const library = { id: "comercial", name: "Comercial", description: "Clientes", document_count: 1 };
const folder = {
  id: "f-1",
  library_id: "comercial",
  parent_id: null,
  name: "Certificados",
  created_by: "sistema@thinknex.example",
  created_at: now,
};
const doc = {
  id: "doc-006",
  title: "Certificado de cliente",
  filename: "certificado.pdf",
  mime_type: "application/pdf",
  size_bytes: 2048,
  sha256: "a".repeat(64),
  version: 2,
  classification: "INTERNAL",
  owner: "comercial@thinknex.example",
  library_id: "comercial",
  folder_id: "f-1",
  created_by: "ana@thinknex.example",
  updated_at: now,
  active_shares: 2,
};
const share = {
  id: "11111111-1111-1111-1111-111111111111",
  document: {
    source_id: "doc-006",
    source_version: 2,
    title: doc.title,
    sha256: doc.sha256,
    classification: "INTERNAL",
  },
  recipient: { name: "María González", contact: "m***@cliente.example", is_external: true },
  shared_by: "ana@thinknex.example",
  channel: "EMAIL",
  reason: "Certificado",
  status: "ACTIVE",
  created_at: now,
  expires_at: now,
  max_accesses: 3,
  access_count: 1,
  sensitivity_decision: "WARN",
  sensitivity_report: {},
  notification_status: null,
  revoked_at: null,
};

function mockLibrary() {
  server.use(
    http.get("*/api/v1/library/libraries", () => HttpResponse.json([library])),
    http.get("*/api/v1/library/items", ({ request }) => {
      const inFolder = new URL(request.url).searchParams.get("folder_id") === "f-1";
      return HttpResponse.json({
        library,
        breadcrumbs: inFolder ? [folder] : [],
        folders: inFolder ? [] : [folder],
        documents: inFolder ? [doc] : [],
      });
    }),
    http.get("*/api/v1/library/documents/doc-006", () =>
      HttpResponse.json({
        document: doc,
        library,
        breadcrumbs: [folder],
        versions: [
          {
            version: 2,
            sha256: doc.sha256,
            size_bytes: 2048,
            comment: "Actualización",
            created_by: "ana@thinknex.example",
            created_at: now,
          },
          {
            version: 1,
            sha256: "b".repeat(64),
            size_bytes: 2000,
            comment: "Versión inicial",
            created_by: "ana@thinknex.example",
            created_at: now,
          },
        ],
      }),
    ),
    http.get("*/api/v1/library/documents/doc-006/content", () =>
      HttpResponse.arrayBuffer(new TextEncoder().encode("%PDF-1.4").buffer, {
        headers: { "Content-Type": "application/pdf" },
      }),
    ),
    http.get("*/api/v1/library/documents/doc-006/access", () => HttpResponse.json([share])),
  );
}

describe("explorador de documentos", () => {
  it("navega bibliotecas y carpetas con migas de pan", async () => {
    loggedInAs(["SHARER"]);
    mockLibrary();
    renderApp("/documentos/comercial");
    await userEvent.click(await screen.findByText("Certificados"));
    expect(await screen.findByText("Certificado de cliente")).toBeInTheDocument();
    expect(screen.getByText("Compartido · 2")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Comercial" })).toBeInTheDocument();
  });

  it("abre el panel del archivo con versiones y personas con acceso", async () => {
    loggedInAs(["SHARER"]);
    mockLibrary();
    renderApp("/documentos/comercial/f-1");
    await userEvent.click(await screen.findByText("Certificado de cliente"));
    expect(await screen.findByTitle("Vista previa del documento")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /Detalles/ }));
    expect(await screen.findByText("Versión inicial")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: /Acceso/ }));
    expect(await screen.findByText("María González")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Revocar" })).toBeInTheDocument();
  });

  it("ofrece subir como nueva versión si el nombre ya existe", async () => {
    loggedInAs(["SHARER"]);
    mockLibrary();
    let versionUploaded = false;
    server.use(
      http.post("*/api/v1/library/documents", () =>
        HttpResponse.json(
          {
            title: "Conflicto",
            detail: "Ya existe",
            code: "name_conflict",
            document_id: "doc-006",
          },
          { status: 409 },
        ),
      ),
      http.post("*/api/v1/library/documents/doc-006/versions", () => {
        versionUploaded = true;
        return HttpResponse.json(
          { document: { ...doc, version: 3 }, findings: [], new_version: true },
          { status: 201 },
        );
      }),
    );
    renderApp("/documentos/comercial/f-1");
    await userEvent.click(await screen.findByRole("button", { name: "Subir" }));
    const dialog = await screen.findByRole("dialog");
    await waitFor(() => expect(dialog.querySelector('input[type="file"]')).not.toBeNull());
    const input = dialog.querySelector<HTMLInputElement>('input[type="file"]')!;
    await userEvent.upload(
      input,
      new File(["%PDF-1.4"], "certificado.pdf", { type: "application/pdf" }),
    );
    await userEvent.click(within(dialog).getByRole("button", { name: "Subir" }));
    await userEvent.click(await screen.findByRole("button", { name: "Subir como nueva versión" }));
    await waitFor(() => expect(versionUploaded).toBe(true));
  });

  it("edita el nombre de un archivo conservando la extensión y muestra el conflicto", async () => {
    loggedInAs(["SHARER"]);
    mockLibrary();
    const sent: string[] = [];
    server.use(
      http.patch("*/api/v1/library/documents/doc-006", async ({ request }) => {
        const { name } = (await request.json()) as { name: string };
        sent.push(name);
        if (name === "Existente") {
          return HttpResponse.json(
            {
              detail: "Ya existe un archivo con ese nombre en esta ubicación",
              code: "name_conflict",
            },
            { status: 409 },
          );
        }
        return HttpResponse.json({ ...doc, title: name, filename: `${name}.pdf` });
      }),
    );
    renderApp("/documentos/comercial/f-1");
    await screen.findByText("Certificado de cliente");
    await userEvent.click(
      screen.getAllByRole("button", { name: "Acciones de Certificado de cliente" })[0]!,
    );
    await userEvent.click(await screen.findByRole("menuitem", { name: "Editar" }));

    const input = await screen.findByLabelText("Nombre");
    expect(input).toHaveValue("certificado");
    expect(screen.getByText(".pdf")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Clasificación" })).toBeDisabled(); // no es ADMIN
    const submit = screen.getByRole("button", { name: "Guardar" });
    expect(submit).toBeDisabled(); // sin cambios

    await userEvent.clear(input);
    await userEvent.type(input, "Existente");
    await userEvent.click(submit);
    expect(await screen.findByText(/Ya existe un archivo con ese nombre/)).toBeInTheDocument();

    await userEvent.clear(input);
    await userEvent.type(input, "Certificado María 2026");
    await userEvent.click(submit);
    await waitFor(() => expect(screen.queryByLabelText("Nombre")).not.toBeInTheDocument());
    expect(sent).toEqual(["Existente", "Certificado María 2026"]);
  });

  it("el ADMIN reclasifica un archivo, pero no ve Compartir", async () => {
    loggedInAs(["ADMIN"], { email: "admin@thinknex.example", name: "Administrador" });
    mockLibrary();
    const patches: unknown[] = [];
    server.use(
      http.patch("*/api/v1/library/documents/doc-006", async ({ request }) => {
        patches.push(await request.json());
        return HttpResponse.json({ ...doc, classification: "CONFIDENTIAL" });
      }),
    );
    renderApp("/documentos/comercial/f-1");
    await screen.findByText("Certificado de cliente");
    const actions = () =>
      screen.getAllByRole("button", { name: "Acciones de Certificado de cliente" })[0]!;

    await userEvent.click(actions());
    expect(screen.queryByRole("menuitem", { name: "Compartir" })).not.toBeInTheDocument();
    await userEvent.click(await screen.findByRole("menuitem", { name: "Editar" }));
    await userEvent.click(screen.getByRole("combobox", { name: "Clasificación" }));
    await userEvent.click(screen.getByRole("option", { name: "Confidencial", hidden: true }));
    await userEvent.click(screen.getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(patches).toEqual([{ classification: "CONFIDENTIAL" }]));
  });

  it("el ADMIN elimina un archivo y se le avisa de los envíos que se revocarán", async () => {
    loggedInAs(["ADMIN"], { email: "admin@thinknex.example", name: "Administrador" });
    mockLibrary();
    let deleted = false;
    server.use(
      http.delete("*/api/v1/library/documents/doc-006", () => {
        deleted = true;
        return HttpResponse.json({ revoked_shares: 2 });
      }),
    );
    renderApp("/documentos/comercial/f-1");
    await screen.findByText("Certificado de cliente");
    await userEvent.click(
      screen.getAllByRole("button", { name: "Acciones de Certificado de cliente" })[0]!,
    );
    await userEvent.click(await screen.findByRole("menuitem", { name: "Eliminar" }));
    expect(await screen.findByText(/2 envío\(s\) activo\(s\) se revocarán/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Eliminar" }));
    await waitFor(() => expect(deleted).toBe(true));
  });

  it("un auditor no accede a la biblioteca", async () => {
    loggedInAs(["AUDITOR"]);
    renderApp("/documentos");
    expect(await screen.findByText("Sin acceso")).toBeInTheDocument();
  });
});
