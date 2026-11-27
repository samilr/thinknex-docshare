import { expect, test } from "@playwright/test";

const PASSWORD = process.env.DEMO_USERS_PASSWORD ?? "Demo-pass-2026";

test("se recupera de un chunk eliminado por un despliegue nuevo", async ({ page }) => {
  await page.goto("/login");
  await page.getByLabel("Email").fill("ana@thinknex.example");
  await page.getByLabel("Contraseña").fill(PASSWORD);
  await page.getByRole("button", { name: "Ingresar" }).click();
  await expect(page.getByText(/^Hola, /)).toBeVisible();

  let failed = 0;
  await page.route(/\/assets\/ExplorerPage-.*\.js$/, async (route) => {
    if (failed === 0) {
      failed += 1;
      await route.fulfill({ status: 404, body: "Not Found" });
    } else {
      await route.continue();
    }
  });

  await page.getByRole("link", { name: "Documentos" }).click();
  await expect(page.getByText("Bibliotecas", { exact: true })).toBeVisible();
  await expect(page.getByText("Unexpected Application Error")).toHaveCount(0);
  expect(failed).toBe(1);
});
