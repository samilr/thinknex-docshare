import { expect, test } from "@playwright/test";

const PASSWORD = process.env.DEMO_USERS_PASSWORD ?? "Demo-pass-2026";

test("preguntar a los documentos responde con citas y abre la fuente", async ({ page }) => {
  test.setTimeout(120_000);
  await page.goto("/login");
  await page.getByLabel("Email").fill("ana@thinknex.example");
  await page.getByLabel("Contraseña").fill(PASSWORD);
  await page.getByRole("button", { name: "Ingresar" }).click();
  await expect(page.getByText(/^Hola, /)).toBeVisible();

  const ask = page.getByRole("link", { name: "Preguntar", exact: true });
  test.skip((await ask.count()) === 0, "IA no disponible en este entorno");
  await ask.click();
  await page.getByLabel("Pregunta", { exact: true }).fill("¿Qué planes ofrece el catálogo de productos 2026?");
  await page.getByRole("button", { name: "Preguntar", exact: true }).click();

  const citation = page.getByRole("button", { name: /^Fuente \d+$/ }).first();
  await expect(citation).toBeVisible({ timeout: 60_000 });
  await expect(page.getByText(/Plan (Básico|Plus|Enterprise)/).first()).toBeVisible();
  await expect(
    page.getByRole("button", { name: /Abrir fuente \d+: Catálogo de productos 2026/ }).first(),
  ).toBeVisible();
  if (process.env.SCREENSHOTS_DIR) {
    await page.screenshot({
      path: `${process.env.SCREENSHOTS_DIR}/16-preguntar.png`,
      fullPage: true,
    });
  }
  await citation.click();
  await expect(page).toHaveURL(/\/documentos\/.*\?doc=doc-004&page=\d+/);
  await expect(
    page.getByRole("dialog").getByText("Catálogo de productos 2026").first(),
  ).toBeVisible();
});
