import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { loggedInAs, renderApp } from "../test/render";
import { server } from "../test/server";

const now = new Date().toISOString();
const rule = {
  id: "00000000-0000-0000-0000-0000000000aa",
  name: "Datos personales a externos",
  description: "",
  action: "WARN",
  message: "Contiene datos personales y sale de la organización.",
  classifications: [],
  recipient: "EXTERNAL",
  finding_types: ["RUT", "EMAIL", "PHONE"],
  channels: [],
  enabled: true,
  created_by: "sistema",
  updated_by: "sistema",
  created_at: now,
  updated_at: now,
};

describe("políticas de compartición", () => {
  it("el ADMIN edita una regla (quita EMAIL) y la desactiva", async () => {
    loggedInAs(["ADMIN"], { email: "admin@thinknex.example", name: "Administrador" });
    const puts: Record<string, unknown>[] = [];
    server.use(
      http.get("*/api/v1/admin/policies", () => HttpResponse.json([rule])),
      http.put("*/api/v1/admin/policies/:id", async ({ request }) => {
        const body = (await request.json()) as Record<string, unknown>;
        puts.push(body);
        return HttpResponse.json({ ...rule, ...body });
      }),
    );
    renderApp("/politicas");
    expect(await screen.findByText("Datos personales a externos")).toBeInTheDocument();
    expect(screen.getByText(/Contiene RUT, Correo electrónico, Teléfono/)).toBeInTheDocument();

    await userEvent.click(
      screen.getByRole("button", { name: "Editar Datos personales a externos" }),
    );
    const dialog = await screen.findByRole("dialog");
    // En un MultiSelect, elegir una opción ya seleccionada la quita.
    // (en jsdom las opciones quedan ocultas por la transición del desplegable)
    await userEvent.click(within(dialog).getByRole("combobox", { name: /Datos detectados/ }));
    await userEvent.click(screen.getByRole("option", { name: "Correo electrónico", hidden: true }));
    await userEvent.click(within(dialog).getByRole("button", { name: "Guardar" }));
    await waitFor(() => expect(puts).toHaveLength(1));
    expect(puts[0]!.finding_types).toEqual(["RUT", "PHONE"]);

    await userEvent.click(
      screen.getByRole("switch", { name: "Activar Datos personales a externos" }),
    );
    await waitFor(() => expect(puts).toHaveLength(2));
    expect(puts[1]!.enabled).toBe(false);
  });

  it("el AUDITOR ve las reglas en solo lectura", async () => {
    loggedInAs(["AUDITOR"], { email: "carla@thinknex.example", name: "Carla" });
    server.use(http.get("*/api/v1/admin/policies", () => HttpResponse.json([rule])));
    renderApp("/politicas");
    expect(await screen.findByText("Datos personales a externos")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Nueva regla" })).not.toBeInTheDocument();
    expect(screen.getByRole("switch")).toBeDisabled();
  });

  it("un emisor no accede", async () => {
    loggedInAs(["SHARER"]);
    renderApp("/politicas");
    expect(await screen.findByText("Sin acceso")).toBeInTheDocument();
  });
});
