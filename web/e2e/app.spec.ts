import {expect, test} from "@playwright/test";

test("carga el buscador y el estado inicial", async ({page}) => {
  await page.goto("/");
  await expect(page.getByRole("heading", {level: 1})).toContainText("Quién ingresó");
  await expect(page.getByLabel("Nombre o documento")).toBeVisible();
  await page.getByLabel("Nombre o documento").fill("Ana");
  await expect(page.getByText(/Sin resultados para/)).toBeVisible();
});

test("refluye sin scroll horizontal a 320px", async ({page}) => {
  await page.setViewportSize({width: 320, height: 800});
  await page.goto("/");
  const dimensions = await page.evaluate(() => ({scroll: document.documentElement.scrollWidth, client: document.documentElement.clientWidth}));
  expect(dimensions.scroll).toBeLessThanOrEqual(dimensions.client);
});

