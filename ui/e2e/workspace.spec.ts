import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const fixture = (name: string) =>
  JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf8"));

const jobId = "job-workspace-1";
const interaction = {
  interaction_id: "interaction-workspace-1",
  job_id: jobId,
  recipe_id: "lamera_video_edit",
  step_id: "research_review",
  gate_id: "research_review",
  kind: "approval",
  title: "Research approved",
  description: "Review the dossier before the script.",
  summary: "Check every source and remove weak claims.",
  checklist: ["Sources attached", "No unsupported claims"],
  severity: "warning",
  next_step: "Script generation",
  group: "research",
  approve_label: "Approve",
  reject_label: "Reject",
  questions: [],
  files: [],
  artifacts: [
    {
      id: "dossier",
      label: "Research dossier",
      path: "research/master.json",
      kind: "json",
      description: "Consolidated dossier",
      exists: true,
      size_bytes: 1200,
      download_url: "/api/v1/jobs/job-workspace-1/interactions/interaction-workspace-1/artifacts/dossier"
    }
  ],
  channels: ["local"],
  status: "pending",
  created_at: "2026-11-12T10:00:00+00:00",
  expires_at: "2026-11-19T10:00:00+00:00",
  reminder_at: "",
  token_required: false,
  response_url: "",
  files_url: ""
};

const job = {
  ...fixture("jobs_dashboard.json").jobs[0],
  job_id: jobId,
  status: "waiting_approval",
  progress: 35,
  stage: "research_review",
  message: "Research review",
  interaction,
  result: {
    ok: true,
    recipe_id: "lamera_video_edit",
    artifacts: { "research/master.json": "/out/research/master.json" },
    step_runs: []
  }
};

const recipe = {
  ...fixture("recipe.json").recipe,
  id: "lamera_video_edit",
  name: "Lamera Video Edit",
  steps: [
    { id: "research_review", type: "human.gate", needs: [], enabled: true, params: {} }
  ],
  ui: {
    version: 1,
    viewport: { x: 0, y: 0, zoom: 1 },
    nodes: {},
    groups: [
      {
        id: "research",
        label: "1 · Research",
        description: "Research and script",
        color: "#38bdf8",
        x: 0,
        y: 0,
        width: 400,
        height: 160,
        nodes: ["research_review"]
      }
    ]
  }
};

async function mockApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/system") return route.fulfill({ json: fixture("system.json") });
    if (path === "/api/v1/jobs") return route.fulfill({ json: { ok: true, jobs: [job] } });
    if (path === `/api/v1/jobs/${jobId}`) return route.fulfill({ json: { ok: true, job } });
    if (path === `/api/v1/jobs/${jobId}/logs`) {
      return route.fulfill({
        json: {
          ok: true,
          logs: [
            {
              timestamp: "2026-11-12T10:01:00+00:00",
              level: "info",
              module: "research",
              message: "Research dossier ready"
            }
          ]
        }
      });
    }
    if (path === `/api/v1/jobs/${jobId}/interactions`) {
      return route.fulfill({ json: { ok: true, interactions: [interaction] } });
    }
    if (path === "/api/v1/recipes") return route.fulfill({ json: fixture("recipes.json") });
    if (path === "/api/v1/recipes/lamera_video_edit") {
      return route.fulfill({ json: { ok: true, recipe } });
    }
    if (path === "/api/v1/hilt/pending") {
      return route.fulfill({
        json: {
          ok: true,
          interactions: [
            {
              job_id: jobId,
              job_status: "waiting_approval",
              job_message: "Research review",
              interaction
            }
          ]
        }
      });
    }
    if (path === `/api/v1/jobs/${jobId}/interactions/${interaction.interaction_id}/respond`) {
      return route.fulfill({ json: { ok: true, job: { ...job, status: "running", interaction: null } } });
    }
    return route.fulfill({ json: { ok: true } });
  });
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
});

test("opens the global HITL inbox and the run workspace", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("produce-home")).toBeVisible({ timeout: 20_000 });
  await page.getByTestId("needs-you").click();
  const inbox = page.getByTestId("hitl-inbox");
  await expect(inbox).toBeVisible();
  await expect(inbox.getByText("Research approved")).toBeVisible();
  await inbox.getByText("Research approved").click();
  await expect(page.getByTestId("recipe-workspace")).toBeVisible();
  await expect(page.getByText("Research approved")).toBeVisible();
  await expect(page.getByRole("button", { name: "Approve" })).toBeVisible();
});

test("renders the workspace directly from a run hash", async ({ page }) => {
  await page.goto(`/#run/${jobId}`);
  await expect(page.getByTestId("recipe-workspace")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Lamera Video Edit")).toBeVisible();
  await expect(page.getByText("1 · Research", { exact: true })).toBeVisible();
  await page.getByRole("tab", { name: "Artifacts" }).click();
  await expect(page.getByText("research/master.json").first()).toBeVisible();
  await page.getByRole("tab", { name: "Logs" }).click();
  await expect(page.getByText("Research dossier ready")).toBeVisible();
  await page.getByRole("tab", { name: "History" }).click();
  await expect(page.getByText("Research approved").first()).toBeVisible();
});
