import { expect, test } from "@playwright/test";

const PASSWORD = process.env.DEMO_USERS_PASSWORD ?? "Demo-pass-2026";

test("el menú lateral se contrae, recuerda el estado y los botones usan la mano", async ({
  page,
}) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("ana@thinknex.example");
  await page.getByLabel("Contraseña").fill(PASSWORD);
  await page.getByRole("button", { name: "Ingresar" }).click();
  await expect(page.getByText(/^Hola, /)).toBeVisible();

  const documentos = page.getByRole("link", { name: "Documentos", exact: true });
  await expect(page.getByRole("navigation").getByText("Documentos")).toBeVisible();
  await page.getByRole("button", { name: "Contraer menú" }).click();
  await expect(page.getByRole("navigation").getByText("Documentos")).toBeHidden();
  await expect(documentos).toBeVisible();
  const navWidth = await page.getByRole("navigation").evaluate((el) => el.clientWidth);
  expect(navWidth).toBeLessThan(100);
  if (process.env.SCREENSHOTS_DIR) {
    await page.waitForTimeout(400);
    await page.screenshot({ path: `${process.env.SCREENSHOTS_DIR}/15-menu-contraido.png` });
  }

  await page.reload();
  await expect(page.getByRole("button", { name: "Expandir menú" })).toBeVisible();
  await documentos.click();
  await expect(page).toHaveURL(/\/documentos/);
  await page.getByRole("button", { name: "Expandir menú" }).click();
  await expect(page.getByRole("navigation").getByText("Documentos")).toBeVisible();

  for (const target of [
    page.getByRole("button", { name: "Contraer menú" }),
    page.getByRole("button", { name: "Menú de usuario" }),
    documentos,
  ]) {
    expect(await target.evaluate((el) => getComputedStyle(el).cursor)).toBe("pointer");
  }
});
