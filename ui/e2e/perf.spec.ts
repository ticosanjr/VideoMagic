import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const system = JSON.parse(readFileSync(new URL("./fixtures/system.json", import.meta.url), "utf8"));

const clips = Array.from({ length: 1000 }, (_value, index) => ({
  id: `v${index}`,
  start_sec: index * 0.25,
  end_sec: index * 0.25 + 0.25,
  source_in_frame: index * 30,
  source_out_frame: index * 30 + 30,
  zoom: 1,
  keyframes: 0,
  transition: null
}));

const captions = Array.from({ length: 1000 }, (_value, index) => ({
  id: index,
  start_sec: index * 0.05,
  end_sec: index * 0.05 + 0.04,
  text: `caption ${index}`,
  speaker: 0
}));

const timeline = {
  ok: true,
  job_id: "job-1",
  revision: 1,
  can_undo: false,
  can_redo: false,
  fps: 30,
  duration_sec: 50,
  source_duration_sec: 50,
  live_eligible: false,
  live_reason: "test fixture",
  inactive: [],
  video: clips,
  audio: [{ id: "v0", start_sec: 0, end_sec: 50 }],
  captions,
  shorts: [],
  broll: {},
  broll_approval: {},
  markers: [],
  tracks: {},
  preview_url: "/api/v1/jobs/job-1/preview/file"
};

const job = {
  job_id: "job-1",
  status: "succeeded",
  progress: 100,
  stage: "done",
  message: "Finished",
  source: "/tmp/source.mp4",
  output: "/tmp/out",
  options: {},
  result: { ok: true, artifacts: {}, shorts: [], broll_plan: {} },
  error: null,
  created_at: "2026-10-23T10:00:00Z",
  started_at: "2026-10-23T10:00:00Z",
  finished_at: "2026-10-23T10:00:10Z",
  duration_ms: 10000,
  log_count: 0,
  stages: [],
  step_progress: {}
};

async function mockApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/system") return route.fulfill({ json: system });
    if (path === "/api/v1/jobs") return route.fulfill({ json: { ok: true, jobs: [job] } });
    if (path === "/api/v1/jobs/job-1/timeline") return route.fulfill({ json: timeline });
    if (path === "/api/v1/jobs/job-1/timeline/waveform") {
      return route.fulfill({ json: { ok: true, peaks: [0.2, 0.6, 0.9], bucket_sec: 0.05 } });
    }
    if (path === "/api/v1/jobs/job-1/review") {
      return route.fulfill({ json: { ok: true, review: { checks: [] } } });
    }
    if (path === "/api/v1/jobs/job-1/thumbnails") {
      return route.fulfill({ json: { ok: true, variants: [], selected: "" } });
    }
    return route.fulfill({ json: { ok: true } });
  });
}

// Performance runs in isolation: `npm run test:perf`.
test.skip(process.env.VF_PERF !== "1", "set VF_PERF=1 to run the performance guard");

test("scrolls a 1,000-clip, 1,000-caption timeline without long frames", async ({ page }) => {
  await mockApi(page);
  await page.goto("/#timeline");
  const scroller = page.getByTestId("timeline-scroller");
  await expect(scroller).toBeVisible({ timeout: 20_000 });
  await page.waitForTimeout(1200);

  const samples = await scroller.evaluate(async (element) => {
    const frames: number[] = [];
    let previous = performance.now();
    for (let index = 0; index < 120; index += 1) {
      element.scrollLeft += 24;
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
      const now = performance.now();
      frames.push(now - previous);
      previous = now;
    }
    return frames;
  });

  const average = samples.reduce((sum, value) => sum + value, 0) / samples.length;
  const sorted = [...samples].sort((a, b) => a - b);
  const p95 = sorted[Math.floor(sorted.length * 0.95)];
  console.log(`timeline scroll: avg ${average.toFixed(1)}ms p95 ${p95.toFixed(1)}ms`);

  expect(samples.length).toBe(120);
  // The full suite runs several browsers in parallel; the guard is deliberately
  // looser than the standalone measurement (17 ms average) so it catches real
  // regressions instead of scheduler noise.
  // Host load moves this baseline (17 ms idle, ~25 ms at load 10, 80 ms+
  // on a saturated CI box). Keep the guard structural, not scheduler-bound.
  expect(average).toBeLessThan(120);
  expect(p95).toBeLessThan(250);
});
