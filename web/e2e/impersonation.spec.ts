import { expect, test } from "@playwright/test";

const ADMIN_EMAIL = process.env.BOOTSTRAP_ADMIN_EMAIL ?? "admin@thinknex.example";
const ADMIN_PASSWORD = process.env.BOOTSTRAP_ADMIN_PASSWORD ?? "Admin-demo-2026";

test("el administrador actúa como otro usuario y vuelve a su cuenta", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill(ADMIN_EMAIL);
  await page.getByLabel("Contraseña").fill(ADMIN_PASSWORD);
  await page.getByRole("button", { name: "Ingresar" }).click();
  await expect(page.getByText(/^Hola, /)).toBeVisible();

  await page.getByRole("link", { name: "Usuarios", exact: true }).click();
  await page.getByRole("button", { name: "Acciones para ana@thinknex.example" }).click();
  await page.getByRole("menuitem", { name: "Actuar como este usuario" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Actuar como" }).click();

  await expect(page.getByText("Estás actuando como Ana Rojas (Emisor)")).toBeVisible();
  await expect(page.getByText("Hola, Ana")).toBeVisible();
  if (process.env.SCREENSHOTS_DIR) {
    await page.waitForTimeout(800);
    await page.screenshot({ path: `${process.env.SCREENSHOTS_DIR}/14-actuando-como.png` });
  }
  await expect(page.getByRole("link", { name: "Usuarios", exact: true })).toHaveCount(0);
  await page.getByRole("link", { name: "Envíos", exact: true }).click();
  await expect(page.getByText("Estás actuando como Ana Rojas (Emisor)")).toBeVisible();

  await page.reload();
  await expect(page.getByText("Estás actuando como Ana Rojas (Emisor)")).toBeVisible();

  await page.getByRole("button", { name: "Volver a mi cuenta" }).click();
  await expect(page.getByRole("link", { name: "Usuarios", exact: true })).toBeVisible();
  await expect(page.getByText(/actuando como/i)).toHaveCount(0);

  await page.getByRole("link", { name: "Auditoría", exact: true }).click();
  await page.getByRole("combobox", { name: "Evento" }).click();
  await page.getByRole("option", { name: "Inicio de actuación como usuario" }).click();
  await expect(page.getByText("Como ana@thinknex.example").first()).toBeVisible();
});
