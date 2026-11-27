import { expect, test } from "@playwright/test";

const PASSWORD = process.env.DEMO_USERS_PASSWORD ?? "Demo-pass-2026";
const SHOTS = process.env.SCREENSHOTS_DIR;

/**
 * Enlace de ThinkNex Docs para cualquiera, de solo lectura: Ana copia el enlace, alguien sin
 * cuenta lo abre en el visor (sin botón Descargar) y luego Ana genera un enlace nuevo, con lo
 * que el anterior deja de funcionar.
 */
test("enlace para cualquiera de solo lectura y regeneración del enlace", async ({
  page,
  browser,
}) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("ana@thinknex.example");
  await page.getByLabel("Contraseña").fill(PASSWORD);
  await page.getByRole("button", { name: "Ingresar" }).click();
  await expect(page.getByText(/^Hola, /)).toBeVisible();

  await page.getByRole("link", { name: "Documentos" }).click();
  await page.getByRole("link", { name: /^Marketing/ }).click();
  await page.getByText("Catálogo de productos 2026", { exact: true }).first().click();
  const panel = page.getByRole("dialog");
  await panel.getByRole("button", { name: "Compartir" }).first().click();

  const wizard = page.getByRole("dialog").filter({ hasText: "Revisar seguridad" });
  await wizard.getByText("Enlace ThinkNex Docs").click();
  await wizard.getByText("Cualquiera con el enlace").click();
  await wizard.getByText("Solo ver").click();
  await wizard.getByLabel(/Motivo/).fill("Catálogo para prospectos");
  await wizard.getByRole("button", { name: "Revisar seguridad" }).click();
  const review = page.getByRole("dialog").filter({ hasText: "Revisión de seguridad" });
  await expect(review.getByText("Permitido")).toBeVisible();
  await review.getByRole("button", { name: "Compartir", exact: true }).click();
  const linkField = review.getByLabel("Enlace para compartir");
  await expect(linkField).toBeVisible();
  const link = await linkField.inputValue();
  expect(link).toMatch(/\/s\/[A-Za-z0-9_-]{20,}$/);
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/12-enlace-creado.png` });
  await review.getByRole("button", { name: "Listo" }).click();

  // Alguien sin cuenta (otro contexto, sin cookies) abre el enlace.
  const stranger = await browser.newContext();
  const viewer = await stranger.newPage();
  await viewer.goto(link);
  await expect(viewer.getByText("Ana Rojas compartió un documento contigo")).toBeVisible();
  await viewer.getByRole("button", { name: "Abrir documento" }).click();
  await expect(viewer.getByRole("img", { name: "Página 1" })).toBeVisible();
  await expect(viewer.getByText(/Solo lectura/)).toBeVisible();
  await expect(viewer.getByRole("button", { name: "Descargar" })).toHaveCount(0);
  if (SHOTS)
    await viewer.screenshot({ path: `${SHOTS}/13-visor-solo-lectura.png`, fullPage: true });

  // Ana genera un enlace nuevo desde "Personas con acceso": el anterior deja de funcionar.
  await panel.getByRole("tab", { name: /Acceso/ }).click();
  await expect(panel.getByText("Cualquier persona con el enlace").first()).toBeVisible();
  await panel.getByRole("button", { name: "Nuevo enlace" }).first().click();
  await page.getByRole("button", { name: "Generar" }).click();
  await expect(panel.getByLabel("Enlace para compartir")).toBeVisible();
  expect(await panel.getByLabel("Enlace para compartir").inputValue()).not.toBe(link);

  await viewer.goto(link);
  await expect(viewer.getByText("Enlace no disponible")).toBeVisible();
  await stranger.close();
});
