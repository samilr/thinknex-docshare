import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { server } from "../test/server";
import { emptyStats, loggedInAs, renderApp, sessionFor } from "../test/render";

describe("autenticación y roles", () => {
  it("redirige al login cuando no hay sesión", async () => {
    const { router } = renderApp("/envios");
    expect(await screen.findByRole("button", { name: "Ingresar" })).toBeInTheDocument();
    expect(router.state.location.pathname).toBe("/login");
  });

  it("muestra el error de credenciales inválidas", async () => {
    server.use(
      http.post("*/api/v1/auth/login", () =>
        HttpResponse.json({ detail: "Usuario o contraseña inválidos" }, { status: 401 }),
      ),
    );
    renderApp("/login");
    await userEvent.type(await screen.findByLabelText("Email"), "ana@thinknex.example");
    await userEvent.type(screen.getByLabelText("Contraseña"), "incorrecta");
    await userEvent.click(screen.getByRole("button", { name: "Ingresar" }));
    expect(await screen.findByText("Usuario o contraseña inválidos")).toBeInTheDocument();
  });

  it("inicia sesión y muestra el menú según el rol", async () => {
    server.use(
      http.post("*/api/v1/auth/login", () => HttpResponse.json(sessionFor(["SHARER"]))),
      http.get("*/api/v1/stats", () => HttpResponse.json(emptyStats)),
    );
    renderApp("/login");
    await userEvent.type(await screen.findByLabelText("Email"), "ana@thinknex.example");
    await userEvent.type(screen.getByLabelText("Contraseña"), "Demo-pass-2026");
    await userEvent.click(screen.getByRole("button", { name: "Ingresar" }));
    expect(await screen.findByText("Hola, Ana")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Documentos/ })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Usuarios/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Auditoría/ })).not.toBeInTheDocument();
  });

  it("bloquea secciones de otro rol", async () => {
    loggedInAs(["SHARER"]);
    renderApp("/usuarios");
    expect(await screen.findByText("Sin acceso")).toBeInTheDocument();
  });

  it("obliga a cambiar una contraseña temporal", async () => {
    loggedInAs(["SHARER"], { must_change_password: true });
    const { router } = renderApp("/envios");
    await waitFor(() => expect(router.state.location.pathname).toBe("/cuenta/clave"));
    expect(await screen.findByText("Contraseña temporal")).toBeInTheDocument();
  });
});
