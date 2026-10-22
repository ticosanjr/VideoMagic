import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const fixture = (name: string) =>
  JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf8"));

async function mockApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === "/api/v1/system") return route.fulfill({ json: fixture("system.json") });
    if (path === "/api/v1/jobs") return route.fulfill({ json: fixture("jobs.json") });
    if (path === "/api/v1/steps") return route.fulfill({ json: fixture("steps.json") });
    if (path === "/api/v1/recipes") return route.fulfill({ json: fixture("recipes.json") });
    if (path === "/api/v1/recipes/example_recipe") return route.fulfill({ json: fixture("recipe.json") });
    if (path === "/api/v1/runs") return route.fulfill({ json: fixture("runs.json") });
    if (path === "/api/v1/exports/validate") return route.fulfill({ json: fixture("nle.json") });
    return route.fulfill({ json: { ok: true } });
  });
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Recipe builder" })).toBeVisible();
  await expect(page.getByTestId("step-edit.timeline")).toBeVisible();
});

test("loads the recipe graph and edits transition parameters", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Recipe builder" })).toBeVisible();
  await expect(page.getByTestId("step-edit.timeline")).toBeVisible();
  await page.getByTestId("step-edit.timeline").click();
  await expect(page.getByTestId("transition-frames")).toBeVisible();
  await page.getByTestId("transition-frames").fill("12");
  await page.getByTestId("transition-type").selectOption("fade_to_black");
  const json = await page.getByTestId("step-params-json").inputValue();
  expect(json).toContain('"transition_frames": 12');
  expect(json).toContain('"transition_type": "fade_to_black"');
});

test("adds a step from the JSON-backed palette", async ({ page }) => {
  await page.getByTestId("recipe-add-step").click();
  await expect(page.getByTestId("add-shorts.render")).toBeVisible();
  await page.getByTestId("add-shorts.render").click();
  await expect(page.getByTestId("step-shorts.render")).toBeVisible();
});

test("exposes the second split-screen source control", async ({ page }) => {
  await page.getByTestId("recipe-add-step").click();
  await page.getByTestId("add-shorts.render").click();
  await page.getByTestId("step-shorts.render").click();
  await expect(page.getByPlaceholder("/path/to/second-angle.mp4")).toBeVisible();
});

test("edits a schema-derived field", async ({ page }) => {
  await page.getByTestId("step-ingest").click();
  await expect(page.getByTestId("schema-extract_pcm")).toBeVisible();
  await page.getByTestId("schema-extract_pcm").uncheck();
  const json = await page.getByTestId("step-params-json").inputValue();
  expect(json).toContain('"extract_pcm": false');
});

test("validates NLE exports from the UI", async ({ page }) => {
  await page.getByPlaceholder("/media/output").fill("/tmp/out");
  await page.getByTestId("nle-validate").click();
  await expect(page.getByTestId("nle-report")).toBeVisible();
  await expect(page.getByText("NLE export validation")).toBeVisible();
  await expect(page.getByText("affine_filters: 2")).toBeVisible();
});

test("opens persisted run history and shows failures", async ({ page }) => {
  await page.getByPlaceholder("/media/output").fill("/tmp/out");
  await page.getByTestId("recipe-runs").click();
  await expect(page.getByTestId("run-history")).toBeVisible();
  await expect(page.getByText("failed")).toBeVisible();
  await expect(page.getByText("succeeded")).toBeVisible();
  await expect(page.getByText("ingest_failed")).toHaveCount(0);
});
