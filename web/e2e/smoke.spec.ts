import { expect, type Page, test } from "@playwright/test";

const PASSWORD = process.env.DEMO_USERS_PASSWORD ?? "Demo-pass-2026";
const ADMIN_EMAIL = process.env.BOOTSTRAP_ADMIN_EMAIL ?? "admin@demo-corp.example";
const ADMIN_PASSWORD = process.env.BOOTSTRAP_ADMIN_PASSWORD ?? "Admin-demo-2026";
const SHOTS = process.env.SCREENSHOTS_DIR;

async function shot(page: Page, name: string) {
  if (SHOTS) await page.screenshot({ path: `${SHOTS}/${name}.png`, fullPage: true });
}

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel("Email").fill(email);
  await page.getByLabel("Contraseña").fill(password);
  await page.getByRole("button", { name: "Ingresar" }).click();
  await expect(page.getByText(/^Hola, /)).toBeVisible();
  await expect(page.getByText(email).first()).toBeVisible();
}

async function logout(page: Page) {
  await page.getByRole("button", { name: "Menú de usuario" }).click();
  await page.getByRole("menuitem", { name: "Cerrar sesión" }).click();
  await expect(page.getByRole("button", { name: "Ingresar" })).toBeVisible();
}

test("flujo completo: compartir, recibir, descargar y auditar", async ({ page, context }) => {
  const recipient = `auditor-${Date.now()}@auditora.example`;

  // 1. Ana comparte doc-003 por email
  await login(page, "ana@demo-corp.example", PASSWORD);
  await shot(page, "01-dashboard-ana");
  await page.getByRole("link", { name: "Documentos" }).click();
  await shot(page, "02-documentos");
  await page
    .getByRole("row", { name: /doc-003/ })
    .getByRole("button", { name: "Compartir" })
    .click();
  await page.getByLabel("Nombre del destinatario").fill("Pedro Auditor");
  await page.getByLabel("Email del destinatario").fill(recipient);
  await page.getByLabel(/Motivo/).fill("Auditoría externa Q3");
  await page.getByRole("button", { name: "Revisar seguridad" }).click();
  await expect(page.getByText("Permitido")).toBeVisible();
  await shot(page, "03-revision-seguridad");
  const dialog = page.getByRole("dialog");
  await dialog.getByRole("button", { name: "Compartir", exact: true }).click();
  await expect(dialog.getByText(/Enlace enviado a Pedro Auditor/)).toBeVisible();
  await dialog.getByRole("button", { name: "Listo" }).click();
  await page.getByRole("link", { name: "Envíos" }).click();
  await expect(page.getByRole("row", { name: /Pedro Auditor/ }).first()).toBeVisible();
  await shot(page, "04-envios");
  await logout(page);

  // 2. El ADMIN ve el mensaje en la bandeja simulada y abre el enlace como destinatario
  await login(page, ADMIN_EMAIL, ADMIN_PASSWORD);
  await page.getByRole("link", { name: "Bandeja simulada" }).click();
  await page.getByPlaceholder("Filtrar por destinatario…").fill(recipient);
  await expect(page.locator(".mantine-Card-root")).toHaveCount(1);
  const linkCard = page.locator(".mantine-Card-root", { hasText: "Enlace" }).first();
  const href = await linkCard
    .getByRole("link", { name: "Abrir como destinatario" })
    .getAttribute("href");
  expect(href).toContain("/s/");
  await shot(page, "05-bandeja");

  const recipientPage = await context.browser()!.newPage();
  await recipientPage.goto(href!);
  await expect(recipientPage.getByText(/compartió un documento contigo/)).toBeVisible();
  await recipientPage.getByRole("button", { name: "Enviar código" }).click();
  await expect(recipientPage.getByText(/Código enviado/)).toBeVisible();
  await shot(recipientPage, "06-destinatario");

  await page.reload();
  await page.getByPlaceholder("Filtrar por destinatario…").fill(recipient);
  await expect(page.locator(".mantine-Card-root")).toHaveCount(2);
  const otpButton = page.getByRole("button", { name: /Copiar código \d{6}/ }).first();
  const otp = (await otpButton.textContent())!.match(/\d{6}/)![0];

  await recipientPage.getByLabel("Código de 6 dígitos").fill(otp);
  const download = recipientPage.waitForEvent("download");
  await recipientPage.getByRole("button", { name: "Verificar y descargar" }).click();
  expect((await download).suggestedFilename()).toMatch(/\.pdf$/);
  await recipientPage.close();

  await page.getByRole("link", { name: "Usuarios" }).click();
  await expect(page.getByText("carla@demo-corp.example")).toBeVisible();
  await shot(page, "07-usuarios");
  await logout(page);

  // 3. Carla (AUDITOR) verifica la trazabilidad
  await login(page, "carla@demo-corp.example", PASSWORD);
  await page.getByRole("link", { name: "Auditoría" }).click();
  await expect(page.getByText("Cadena de auditoría íntegra")).toBeVisible();
  await page.getByLabel("Documento").fill("doc-003");
  await expect(page.getByRole("table").getByText("Inicio de sesión")).toHaveCount(0);
  await expect(page.getByText("Documento descargado").first()).toBeVisible();
  await shot(page, "08-auditoria");
  await expect(page.getByRole("link", { name: "Documentos" })).toHaveCount(0);
});
