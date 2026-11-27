import { expect, type Page, test } from "@playwright/test";

const PASSWORD = process.env.DEMO_USERS_PASSWORD ?? "Demo-pass-2026";
const SHOTS = process.env.SCREENSHOTS_DIR;

async function login(page: Page) {
  await page.goto("/login");
  await page.getByLabel("Email").fill("ana@thinknex.example");
  await page.getByLabel("Contraseña").fill(PASSWORD);
  await page.getByRole("button", { name: "Ingresar" }).click();
  await expect(page.getByText(/^Hola, /)).toBeVisible();
}

test("asistente flotante: responde con citas y guarda la conversación", async ({ page }) => {
  test.setTimeout(150_000);
  await login(page);
  const fab = page.getByRole("button", { name: "Abrir asistente" });
  test.skip((await fab.count()) === 0, "IA no disponible en este entorno");

  await fab.click();
  const drawer = page.getByRole("dialog");
  await drawer
    .getByLabel("Mensaje para el asistente")
    .fill("¿Qué planes ofrece el catálogo de productos 2026?");
  await drawer.getByRole("button", { name: "Enviar" }).click();
  await expect(drawer.getByRole("button", { name: /^Fuente \d+$/ }).first()).toBeVisible({
    timeout: 90_000,
  });
  await expect(drawer.getByText(/Plan (Básico|Plus|Enterprise)/).first()).toBeVisible();
  await expect(drawer.getByRole("button", { name: "Enviar" })).toBeVisible({ timeout: 60_000 });
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/17-asistente-flotante.png` });

  await drawer.getByRole("button", { name: "Abrir en pantalla completa" }).click();
  await expect(page).toHaveURL(/\/asistente\?c=/);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByText("¿Qué planes ofrece el catálogo de productos 2026?").first(),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Nueva conversación" })).toBeVisible();
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/18-asistente-pagina.png` });
});

test("botón del asistente en un documento con sugerencias de contexto", async ({ page }) => {
  test.setTimeout(150_000);
  await login(page);
  test.skip(
    (await page.getByRole("button", { name: "Abrir asistente" }).count()) === 0,
    "IA no disponible en este entorno",
  );
  await page.getByRole("link", { name: "Documentos", exact: true }).click();
  await page.getByRole("link", { name: /^Marketing/ }).click();
  await page.getByRole("button", { name: "Asistente: Catálogo de productos 2026" }).click();

  const drawer = page.getByRole("dialog").filter({ hasText: "Resume este documento" });
  await expect(drawer.getByText("Catálogo de productos 2026")).toBeVisible();
  await drawer.getByRole("button", { name: "Resume este documento" }).click();
  await expect(drawer.getByRole("button", { name: /^Fuente \d+$/ }).first()).toBeVisible({
    timeout: 90_000,
  });
});
