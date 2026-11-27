import { readFileSync } from "node:fs";
import { expect, type Page, test } from "@playwright/test";

const PASSWORD = process.env.DEMO_USERS_PASSWORD ?? "Demo-pass-2026";
const ADMIN_EMAIL = process.env.BOOTSTRAP_ADMIN_EMAIL ?? "admin@thinknex.example";
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

test("flujo completo: compartir, recibir, ver, descargar y auditar", async ({ page, context }) => {
  const recipient = `auditor-${Date.now()}@auditora.example`;

  // 1. Ana navega la biblioteca, sube un archivo, lo abre y lo comparte desde su panel
  await login(page, "ana@thinknex.example", PASSWORD);
  await shot(page, "01-dashboard-ana");
  await page.getByRole("link", { name: "Documentos" }).click();
  await page.getByRole("link", { name: /^Comercial/ }).click();
  await page.getByText("Certificados", { exact: true }).click();
  await expect(page.getByRole("link", { name: "Comercial", exact: true })).toBeVisible();
  await shot(page, "02-explorador");

  const fileName = `acta-${Date.now()}.pdf`;
  await page.getByRole("button", { name: "Subir", exact: true }).click();
  const uploadDialog = page.getByRole("dialog");
  await uploadDialog.locator('input[type="file"]').setInputFiles({
    name: fileName,
    mimeType: "application/pdf",
    buffer: readFileSync(new URL("./fixtures/acta-reunion.pdf", import.meta.url)),
  });
  await uploadDialog.getByRole("button", { name: "Subir", exact: true }).click();
  await expect(uploadDialog.getByText(/Contiene datos personales: RUT/)).toBeVisible();
  await shot(page, "03-subida");
  await uploadDialog.getByRole("button", { name: "Cerrar" }).click();

  await page.getByText(fileName.replace(".pdf", ""), { exact: true }).click();
  const panel = page.getByRole("dialog");
  await expect(panel.locator('iframe[title="Vista previa del documento"]')).toBeVisible();
  await shot(page, "04-visor");
  await panel.getByRole("button", { name: "Compartir" }).first().click();

  const wizard = page.getByRole("dialog").filter({ hasText: "Revisar seguridad" });
  await wizard.getByLabel("Nombre del destinatario").fill("Pedro Auditor");
  await wizard.getByLabel("Email del destinatario").fill(recipient);
  await wizard.getByLabel(/Motivo/).fill("Envío del acta al cliente");
  await wizard.getByRole("button", { name: "Revisar seguridad" }).click();
  const dialog = page.getByRole("dialog").filter({ hasText: "Revisión de seguridad" });
  await expect(dialog.getByText("Requiere confirmación")).toBeVisible();
  await dialog.getByLabel(/confirmo que corresponde compartir/).check();
  await shot(page, "05-revision-seguridad");
  await dialog.getByRole("button", { name: "Compartir", exact: true }).click();
  await expect(dialog.getByText(/Enlace enviado a Pedro Auditor/)).toBeVisible();
  await dialog.getByRole("button", { name: "Listo" }).click();

  await panel.getByRole("tab", { name: /Acceso/ }).click();
  await expect(panel.getByText("Pedro Auditor")).toBeVisible();
  await shot(page, "06-personas-con-acceso");
  await page.keyboard.press("Escape");
  await page.getByRole("link", { name: "Envíos" }).click();
  await expect(page.getByRole("row", { name: /Pedro Auditor/ }).first()).toBeVisible();
  await shot(page, "07-envios");
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
  await shot(page, "08-bandeja");

  const recipientPage = await context.browser()!.newPage();
  await recipientPage.goto(href!);
  await expect(recipientPage.getByText(/compartió un documento contigo/)).toBeVisible();
  await recipientPage.getByRole("button", { name: "Enviarme el código" }).click();
  await expect(recipientPage.getByRole("button", { name: "Verificar y abrir" })).toBeVisible();
  await shot(recipientPage, "09-destinatario");

  await page.reload();
  await page.getByPlaceholder("Filtrar por destinatario…").fill(recipient);
  await expect(page.locator(".mantine-Card-root")).toHaveCount(2);
  const otpButton = page.getByRole("button", { name: /Copiar código \d{6}/ }).first();
  const otp = (await otpButton.textContent())!.match(/\d{6}/)![0];

  await recipientPage.getByRole("textbox").first().click();
  await recipientPage.keyboard.type(otp); // al completar los 6 dígitos se verifica solo
  await expect(recipientPage.getByRole("img", { name: "Página 1" })).toBeVisible();
  await shot(recipientPage, "09b-visor-destinatario");
  const download = recipientPage.waitForEvent("download");
  await recipientPage.getByRole("button", { name: "Descargar" }).click();
  expect((await download).suggestedFilename()).toMatch(/\.pdf$/);
  await recipientPage.close();

  await page.getByRole("link", { name: "Usuarios" }).click();
  await expect(page.getByText("carla@thinknex.example")).toBeVisible();
  await shot(page, "10-usuarios");
  await logout(page);

  // 3. Carla (AUDITOR) verifica la trazabilidad
  await login(page, "carla@thinknex.example", PASSWORD);
  await page.getByRole("link", { name: "Auditoría" }).click();
  await expect(page.getByText("Cadena de auditoría íntegra")).toBeVisible();
  await page.getByRole("combobox", { name: "Evento" }).click();
  await page.getByRole("option", { name: "Archivo subido" }).click();
  await expect(page.getByRole("table").getByText("Archivo subido").first()).toBeVisible();
  await shot(page, "11-auditoria");
  await expect(page.getByRole("link", { name: "Documentos" })).toHaveCount(0);
});
