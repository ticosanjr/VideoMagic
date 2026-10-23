import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const system = JSON.parse(readFileSync(new URL("./fixtures/system.json", import.meta.url), "utf8"));

const job = {
  job_id: "job-1",
  status: "succeeded",
  progress: 100,
  stage: "done",
  message: "Finished",
  source: "/tmp/source.mp4",
  output: "/tmp/out",
  options: {},
  result: {
    ok: true,
    recipe_id: "youtube_talking_head",
    artifacts: {},
    shorts: [],
    broll_plan: { "Short one": [{ path: "/tmp/broll-a.mp4" }, { path: "/tmp/broll-b.mp4" }] }
  },
  error: null,
  created_at: "2026-10-23T10:00:00Z",
  started_at: "2026-10-23T10:00:00Z",
  finished_at: "2026-10-23T10:00:10Z",
  duration_ms: 10000,
  log_count: 0,
  stages: [],
  step_progress: {}
};

const timeline = {
  ok: true,
  job_id: "job-1",
  revision: 3,
  can_undo: true,
  can_redo: false,
  fps: 25,
  duration_sec: 8,
  video: [
    { id: "v1", start_sec: 0, end_sec: 3, source_in_frame: 0, source_out_frame: 75, zoom: 1, keyframes: 0, transition: "crossfade" },
    { id: "v2", start_sec: 3, end_sec: 8, source_in_frame: 75, source_out_frame: 200, zoom: 1.1, keyframes: 2, transition: null }
  ],
  audio: [{ id: "v1", start_sec: 0, end_sec: 3 }, { id: "v2", start_sec: 3, end_sec: 8 }],
  captions: [
    { id: 0, start_sec: 0.2, end_sec: 1.4, text: "First caption", speaker: 0 },
    { id: 1, start_sec: 1.5, end_sec: 2.8, text: "Second caption", speaker: 0 }
  ],
  shorts: [],
  broll: { "Short one": [{ path: "/tmp/broll-a.mp4" }, { path: "/tmp/broll-b.mp4" }] },
  broll_approval: { "Short one": { approved: [0], order: [0, 1] } },
  preview_url: "/api/v1/jobs/job-1/preview/file"
};

async function mockApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === "/api/v1/system") return route.fulfill({ json: system });
    if (path === "/api/v1/jobs") return route.fulfill({ json: { ok: true, jobs: [job] } });
    if (path === "/api/v1/jobs/job-1/timeline") {
      if (route.request().method() === "PATCH") {
        return route.fulfill({ json: { ok: true, revision: 4, can_undo: true, can_redo: false, warning: "Re-run export." } });
      }
      return route.fulfill({ json: timeline });
    }
    if (path === "/api/v1/jobs/job-1/timeline/undo") {
      return route.fulfill({ json: { ok: true, revision: 3, can_undo: true, can_redo: true } });
    }
    if (path === "/api/v1/providers") return route.fulfill({ json: { ok: true, providers: [], fallbacks: {} } });
    return route.fulfill({ json: { ok: true } });
  });
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.goto("/#timeline");
  await expect(page.getByRole("heading", { name: "Timeline", exact: true })).toBeVisible();
});

test("renders the canvas timeline and edit controls", async ({ page }) => {
  await expect(page.getByTestId("timeline-canvas")).toBeVisible();
  await expect(page.getByTestId("timeline-timecode")).toContainText("00:00:00");
  await expect(page.getByRole("button", { name: "Split" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Undo" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "Redo" })).toBeDisabled();
});

test("exposes B-roll approval controls", async ({ page }) => {
  const section = page.locator("section", { hasText: "B-roll approval" });
  await expect(section).toBeVisible();
  await expect(section.getByText("Short one")).toBeVisible();
  await expect(section.getByText("1/2")).toBeVisible();
});

test("puts failures in a top banner", async ({ page }) => {
  await page.unroute("**/api/v1/**");
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/system") return route.fulfill({ json: system });
    if (path === "/api/v1/jobs") return route.fulfill({ json: { ok: true, jobs: [job] } });
    if (path === "/api/v1/jobs/job-1/timeline") {
      return route.fulfill({
        status: 422,
        json: { detail: { ok: false, code: "timeline_invalid", message: "Split point must be inside the clip." } }
      });
    }
    return route.fulfill({ json: { ok: true } });
  });
  await page.reload();
  const banner = page.getByTestId("timeline-error");
  await expect(banner).toBeVisible();
  await expect(banner).toContainText("timeline_invalid");
});
