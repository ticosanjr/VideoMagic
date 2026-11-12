import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const fixture = (name: string) =>
  JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf8"));

const syntheticRecipe = {
  schema_version: 1,
  id: "synthetic_code_studio",
  name: "Synthetic Code Studio",
  description: "Script-first pipeline",
  llm: {
    provider: "none",
    base_url: null,
    model: "",
    api_key_env: "VIDEOWFLOW_LLM_API_KEY",
    timeout_seconds: 90
  },
  steps: [
    {
      id: "brief",
      type: "human.input",
      needs: [],
      enabled: true,
      params: {
        gate_id: "brief",
        questions: [{ id: "topic", label: "Topic" }]
      }
    }
  ]
};

const recutRecipe = {
  ...syntheticRecipe,
  id: "recut_replacement",
  name: "Recut Replacement",
  steps: [
    {
      id: "ingest",
      type: "ingest",
      needs: [],
      enabled: true,
      params: {}
    }
  ]
};

async function mockApi(page: Page) {
  const jobs = fixture("jobs.json");
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/system") return route.fulfill({ json: fixture("system.json") });
    if (path === "/api/v1/jobs") return route.fulfill({ json: jobs });
    if (path === "/api/v1/recipes") {
      const payload = fixture("recipes.json");
      return route.fulfill({
        json: {
          ok: true,
          recipes: [
            ...payload.recipes,
            {
              id: "synthetic_code_studio",
              name: "Synthetic Code Studio",
              description: "Script-first pipeline",
              source: "builtin",
              favorite: true,
              last_used_at: "",
              use_count: 0,
              tags: []
            }
          ]
        }
      });
    }
    if (path === "/api/v1/steps") return route.fulfill({ json: fixture("steps.json") });
    if (path === "/api/v1/node-presets") return route.fulfill({ json: { ok: true, presets: [] } });
    if (path === "/api/v1/node-options") {
      return route.fulfill({
        json: { ok: true, providers: { asr: [], tts: [] }, services: [], models: [] }
      });
    }
    if (path === "/api/v1/recipes/recut_replacement") {
      return route.fulfill({ json: { ok: true, recipe: recutRecipe } });
    }
    if (path === "/api/v1/recipes/synthetic_code_studio") {
      return route.fulfill({ json: { ok: true, recipe: syntheticRecipe } });
    }
    if (path === "/api/v1/hilt/pending") {
      return route.fulfill({
        json: {
          ok: true,
          interactions: [
            {
              job_id: "job-lamera",
              job_status: "waiting_approval",
              job_message: "Research review",
              interaction: {
                interaction_id: "interaction-1",
                job_id: "job-lamera",
                recipe_id: "lamera_video_edit",
                step_id: "research_review",
                gate_id: "research_review",
                kind: "approval",
                title: "Research approved",
                description: "Review the dossier",
                approve_label: "Approve",
                reject_label: "Reject",
                questions: [],
                files: [],
                artifacts: [],
                channels: ["local"],
                status: "pending",
                created_at: new Date().toISOString(),
                expires_at: "",
                reminder_at: "",
                token_required: false,
                response_url: "",
                files_url: ""
              }
            }
          ]
        }
      });
    }
    if (path === "/api/v1/recipes/run") {
      return route.fulfill({ json: { ok: true, job: jobs.jobs[0] } });
    }
    return route.fulfill({ json: { ok: true } });
  });
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await expect(page.getByTestId("produce-home")).toBeVisible({ timeout: 20_000 });
});

test("shows favorites, pending gates, and the recipe library", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Start from a favorite" })).toBeVisible();
  await expect(page.getByText("Recut Replacement").first()).toBeVisible();
  await expect(page.getByText("Research approved")).toBeVisible();
  await expect(page.getByTestId("recipe-library-home")).toBeVisible();
});

test("starts a favorite with a source clip", async ({ page }) => {
  const card = page.locator("article").filter({ hasText: "Recut Replacement" }).first();
  await card.getByRole("button", { name: "New run" }).click();
  await expect(page.getByRole("dialog", { name: "Start a run" })).toBeVisible();
  await page.getByPlaceholder("/path/to/source.mp4").fill("/tmp/source.mp4");
  await page.getByRole("button", { name: "Next" }).click();
  await expect(page.getByText("Preflight")).toBeVisible();

  const requestPromise = page.waitForRequest(
    (request) =>
      request.url().endsWith("/api/v1/recipes/run") &&
      request.method() === "POST"
  );
  await page.getByRole("button", { name: "Start run" }).click();
  const body = (await requestPromise).postDataJSON() as Record<string, unknown>;
  expect(body.source).toBe("/tmp/source.mp4");
  expect((body.recipe as { id: string }).id).toBe("recut_replacement");
});

test("starts a script-first favorite without a source", async ({ page }) => {
  const card = page.locator("article").filter({ hasText: "Synthetic Code Studio" }).first();
  await card.getByRole("button", { name: "New run" }).click();
  await expect(page.getByRole("dialog", { name: "Start a run" })).toBeVisible();
  await expect(
    page.getByText("This recipe starts from the brief. No source clip is required.")
  ).toBeVisible();
  await expect(page.getByPlaceholder("/path/to/source.mp4")).toHaveCount(0);
  await page.getByRole("button", { name: "Next" }).click();
  await page.getByRole("button", { name: "Start run" }).click();
});


test("opens the graph builder on the requested favorite", async ({ page }) => {
  const card = page.locator("article").filter({ hasText: "Recut Replacement" }).first();
  await card.getByRole("button", { name: "Edit graph" }).click();
  await expect(page.getByRole("heading", { name: "Recipe builder" })).toBeVisible();
  await expect(page.getByTestId("recipe-library")).toContainText("Recut Replacement");
});
