import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const fixture = (name: string) =>
  JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf8"));

const uiVersion = JSON.parse(
  readFileSync(new URL("../package.json", import.meta.url), "utf8")
).version as string;

async function mockShell(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/system") {
      return route.fulfill({ json: { ...fixture("system.json"), version: uiVersion } });
    }
    if (path === "/api/v1/jobs") return route.fulfill({ json: fixture("jobs_dashboard.json") });
    if (path === "/api/v1/steps") return route.fulfill({ json: fixture("steps.json") });
    if (path === "/api/v1/recipes") return route.fulfill({ json: fixture("recipes.json") });
    if (path === "/api/v1/recipes/example_recipe") return route.fulfill({ json: fixture("recipe.json") });
    if (path === "/api/v1/runs") return route.fulfill({ json: fixture("runs.json") });
    if (path === "/api/v1/assets") return route.fulfill({ json: fixture("assets.json") });
    if (path === "/api/v1/schedules") return route.fulfill({ json: { ok: true, schedules: [] } });
    return route.fulfill({ json: { ok: true } });
  });
}

test("has no serious or critical WCAG A/AA violations", async ({ page }) => {
  await mockShell(page);
  await page.goto("/");
  await expect(page.getByRole("button", { name: /Activity 1/ })).toBeVisible();

  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
    .analyze();
  const blocking = results.violations.filter(
    (item) => item.impact === "serious" || item.impact === "critical"
  );
  expect(
    blocking.map((item) => ({
      id: item.id,
      impact: item.impact,
      nodes: item.nodes.map((node) => node.target)
    }))
  ).toEqual([]);
});

test("keeps the shell visually stable", async ({ page }) => {
  await mockShell(page);
  await page.goto("/");
  await expect(page.getByRole("button", { name: /Activity 1/ })).toBeVisible();
  await expect(page).toHaveScreenshot("shell.png", {
    animations: "disabled",
    maxDiffPixelRatio: 0.02,
    mask: [page.getByTitle("Server version"), page.getByTitle("UI bundle version")]
  });
});
