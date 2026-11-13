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

const syntheticJob = {
  ...job,
  job_id: "job-synthetic",
  status: "succeeded",
  progress: 100,
  stage: "export_master",
  message: "Master ready",
  interaction: null,
  result: {
    ok: true,
    recipe_id: "synthetic_code_studio",
    artifacts: {
      script_json: "/out/script/script.json",
      factcheck: "/out/factcheck/report.json",
      storyboard_units: "/out/storyboard/units.json",
      motion_manifest: "/out/motion/render-manifest.json"
    },
    step_runs: []
  }
};

const footageJob = {
  ...job,
  job_id: "job-footage",
  status: "succeeded",
  progress: 100,
  stage: "export_video",
  message: "Video ready",
  interaction: null,
  result: {
    ok: true,
    recipe_id: "footage_intelligence_edit",
    artifacts: {
      vision_ocr: "/out/vision/ocr.json",
      vision_tracks: "/out/vision/tracks.json",
      motion_callouts: "/out/motion/callouts.json",
      qa_frames: "/out/qa/frames.json",
      assets_licenses: "/out/assets/ledger.json"
    },
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
    if (path === "/api/v1/recipes/synthetic_code_studio") {
      return route.fulfill({
        json: {
          ok: true,
          recipe: { ...recipe, id: "synthetic_code_studio", name: "Synthetic Code Studio" }
        }
      });
    }
    if (path === "/api/v1/recipes/footage_intelligence_edit") {
      return route.fulfill({
        json: {
          ok: true,
          recipe: { ...recipe, id: "footage_intelligence_edit", name: "Footage Intelligence Edit" }
        }
      });
    }
    if (path === "/api/v1/jobs/job-synthetic") {
      return route.fulfill({ json: { ok: true, job: syntheticJob } });
    }
    if (path === "/api/v1/jobs/job-footage") {
      return route.fulfill({ json: { ok: true, job: footageJob } });
    }
    if (path.startsWith("/api/v1/jobs/job-synthetic/logs") || path.startsWith("/api/v1/jobs/job-footage/logs")) {
      return route.fulfill({ json: { ok: true, logs: [] } });
    }
    if (path.endsWith("/interactions")) {
      return route.fulfill({ json: { ok: true, interactions: [] } });
    }
    if (path.endsWith("/artifacts/script_json")) {
      return route.fulfill({ json: { sections: [{ title: "Opening", narration: "Hello world", visual: "Title card" }] } });
    }
    if (path.endsWith("/artifacts/factcheck")) {
      return route.fulfill({ json: { claims: [], unsupported_count: 0 } });
    }
    if (path.endsWith("/artifacts/storyboard_units")) {
      return route.fulfill({ json: { units: [{ unit_id: "UNIT-0001", title: "Opening", start_sec: 0, end_sec: 4, layout: "full_screen" }] } });
    }
    if (path.endsWith("/artifacts/motion_manifest")) {
      return route.fulfill({ json: { scenes: [{ scene_id: "SCENE-0001", title: "Opening", duration_sec: 4 }] } });
    }
    if (path.endsWith("/artifacts/motion_scenes")) {
      if (route.request().method() === "PATCH") {
        return route.fulfill({
          json: {
            ok: true,
            artifact: "motion_scenes",
            path: "/out/motion/scenes.json",
            note: "Plan saved. Re-run the affected step or render to apply it."
          }
        });
      }
      return route.fulfill({
        json: {
          scenes: [
            { scene_id: "SCENE-0001", title: "Opening", narration: "Hello", duration_sec: 4 }
          ]
        }
      });
    }
    if (path.endsWith("/artifacts/vision_ocr")) {
      return route.fulfill({ json: { frames: [{ frame: "frame-00001.png", time_sec: 0, boxes: [{ text: "Hello" }] }] } });
    }
    if (path.endsWith("/artifacts/vision_tracks")) {
      return route.fulfill({ json: { tracks: [{ text: "Hello", start_sec: 0, points: [{ time: 0, x: 10, y: 10 }] }] } });
    }
    if (path.endsWith("/artifacts/motion_callouts")) {
      if (route.request().method() === "PATCH") {
        return route.fulfill({
          json: {
            ok: true,
            artifact: "motion_callouts",
            path: "/out/motion/callouts.json",
            note: "Plan saved. Re-run the affected step or render to apply it."
          }
        });
      }
      return route.fulfill({ json: { callouts: [{ text: "Hello", start_sec: 0, duration_sec: 3, position_x: 0.1, position_y: 0.7 }] } });
    }
    if (path.endsWith("/artifacts/qa_frames")) {
      return route.fulfill({ json: { issues: [], critical_count: 0 } });
    }
    if (path.endsWith("/artifacts/assets_licenses")) {
      return route.fulfill({ json: { entries: [{ asset: "clip.mp4" }] } });
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
    if (path === "/api/v1/hilt/approve") {
      return route.fulfill({
        json: {
          ok: true,
          approved: [
            {
              job_id: jobId,
              interaction_id: interaction.interaction_id,
              status: "approved"
            }
          ],
          failed: []
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

test("bulk approves selected gates from the inbox", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("produce-home")).toBeVisible({ timeout: 20_000 });
  await page.getByTestId("needs-you").click();
  const inbox = page.getByTestId("hitl-inbox");
  await inbox.getByLabel("Select Research approved").check();
  const requestPromise = page.waitForRequest(
    (request) =>
      request.url().endsWith("/api/v1/hilt/approve") &&
      request.method() === "POST"
  );
  await inbox.getByRole("button", { name: /Approve selected/ }).click();
  const body = (await requestPromise).postDataJSON() as {
    items: Array<{ interaction_id: string }>;
  };
  expect(body.items[0].interaction_id).toBe(interaction.interaction_id);
  await expect(inbox.getByText("1 gate(s) approved.")).toBeVisible();
  await expect(page).toHaveScreenshot("hitl-inbox.png", {
    animations: "disabled",
    maxDiffPixelRatio: 0.02
  });
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


test("shows the synthetic pipeline panels", async ({ page }) => {
  await page.goto("/#run/job-synthetic");
  await expect(page.getByTestId("synthetic-overview")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Script → voice → scenes")).toBeVisible();
  await expect(page.getByText("Timed storyboard")).toBeVisible();
  await expect(page.getByText("Opening").first()).toBeVisible();

  const editor = page.getByTestId("scene-editor");
  await expect(editor).toBeVisible();
  await editor.getByLabel("Title").fill("Opening title");
  const saved = page.waitForRequest(
    (request) =>
      request.url().endsWith("/artifacts/motion_scenes") &&
      request.method() === "PATCH"
  );
  await editor.getByRole("button", { name: "Save scene plan" }).click();
  const body = (await saved).postDataJSON() as {
    payload: { scenes: Array<{ title: string }> };
  };
  expect(body.payload.scenes[0].title).toBe("Opening title");
  await expect(editor.getByText("Plan saved.")).toBeVisible();
  await expect(page).toHaveScreenshot("workspace-synthetic.png", {
    animations: "disabled",
    maxDiffPixelRatio: 0.02
  });
});

test("shows the footage pipeline panels", async ({ page }) => {
  await page.goto("/#run/job-footage");
  await expect(page.getByTestId("footage-overview")).toBeVisible({ timeout: 20_000 });
  await expect(page.getByText("Footage → anchors → delivery")).toBeVisible();
  await expect(page.getByText("Vision anchors")).toBeVisible();
  await expect(page.getByText("Callout cards")).toBeVisible();

  const editor = page.getByTestId("callout-editor");
  await expect(editor).toBeVisible();
  await editor.getByLabel("Text").fill("Updated callout");
  const saved = page.waitForRequest(
    (request) =>
      request.url().endsWith("/artifacts/motion_callouts") &&
      request.method() === "PATCH"
  );
  await editor.getByRole("button", { name: "Save callout plan" }).click();
  const body = (await saved).postDataJSON() as {
    payload: { callouts: Array<{ text: string }> };
  };
  expect(body.payload.callouts[0].text).toBe("Updated callout");
  await expect(editor.getByText("Plan saved.")).toBeVisible();
  await expect(page).toHaveScreenshot("workspace-footage.png", {
    animations: "disabled",
    maxDiffPixelRatio: 0.02
  });
});
