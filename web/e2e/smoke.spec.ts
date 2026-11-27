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

  const finalName = fileName.replace(".pdf", "-final");
  await page.getByRole("button", { name: `Acciones de ${fileName.replace(".pdf", "")}` }).click();
  await page.getByRole("menuitem", { name: "Editar" }).click();
  await page.getByRole("textbox", { name: "Nombre" }).fill(finalName);
  await page.getByRole("button", { name: "Guardar", exact: true }).click();
  await expect(page.getByText(finalName, { exact: true })).toBeVisible();

  await page.getByText(finalName, { exact: true }).click();
  const panel = page.getByRole("dialog");
  await expect(panel.locator('iframe[title="Vista previa del documento"]')).toBeVisible();
  await shot(page, "04-visor");
  await panel.getByRole("tab", { name: /Actividad/ }).click();
  await expect(panel.getByText(`«${fileName}» → «${finalName}.pdf»`)).toBeVisible();
  await panel.getByRole("tab", { name: /Vista previa/ }).click();
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
  await page.getByRole("link", { name: "Envíos", exact: true }).click();
  await expect(page.getByRole("row", { name: /Pedro Auditor/ }).first()).toBeVisible();
  await shot(page, "07-envios");
  await logout(page);

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
  await recipientPage.keyboard.type(otp);
  await expect(recipientPage.getByRole("img", { name: "Página 1" })).toBeVisible();
  await shot(recipientPage, "09b-visor-destinatario");
  const download = recipientPage.waitForEvent("download");
  await recipientPage.getByRole("button", { name: "Descargar" }).click();
  expect((await download).suggestedFilename()).toMatch(/\.pdf$/);
  await recipientPage.close();

  await page.getByRole("link", { name: "Usuarios", exact: true }).click();
  await expect(page.getByText("carla@thinknex.example")).toBeVisible();
  await shot(page, "10-usuarios");

  await page.getByRole("link", { name: "Políticas" }).click();
  await expect(page.getByText("Datos personales a externos")).toBeVisible();
  await shot(page, "10b-politicas");
  await page.getByRole("link", { name: "Documentos" }).click();
  await page.getByRole("link", { name: /^Comercial/ }).click();
  await page.getByText("Certificados", { exact: true }).click();
  await page.getByRole("button", { name: `Acciones de ${finalName}` }).click();
  await expect(page.getByRole("menuitem", { name: "Compartir" })).toBeVisible();
  await page.getByRole("menuitem", { name: "Eliminar" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Eliminar" }).click();
  await expect(page.getByText(/Archivo eliminado y 1 envío\(s\) revocado\(s\)/)).toBeVisible();
  await expect(page.getByText(finalName, { exact: true })).toHaveCount(0);
  await logout(page);

  await login(page, "carla@thinknex.example", PASSWORD);
  await page.getByRole("link", { name: "Auditoría", exact: true }).click();
  await expect(page.getByText("Cadena de auditoría íntegra")).toBeVisible();
  await page.getByRole("combobox", { name: "Evento" }).click();
  await page.getByRole("option", { name: "Archivo subido" }).click();
  await expect(page.getByRole("table").getByText("Archivo subido").first()).toBeVisible();
  await shot(page, "11-auditoria");
  await expect(page.getByRole("link", { name: "Documentos" })).toHaveCount(0);
});
