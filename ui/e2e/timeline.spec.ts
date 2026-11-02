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
  audio: [
    { id: "v1", start_sec: 0, end_sec: 3, source_in_sec: 10.5, source_out_sec: 13.5 },
    { id: "v2", start_sec: 3, end_sec: 8, source_in_sec: 40, source_out_sec: 45 }
  ],
  captions: [
    { id: 0, start_sec: 0.2, end_sec: 1.4, text: "First caption", speaker: 0 },
    { id: 1, start_sec: 1.5, end_sec: 2.8, text: "Second caption", speaker: 0 }
  ],
  shorts: [],
  broll: { "Short one": [{ path: "/tmp/broll-a.mp4" }, { path: "/tmp/broll-b.mp4" }] },
  broll_approval: { "Short one": { approved: [0], order: [0, 1] } },
  preview_url: "/api/v1/jobs/job-1/preview/file"
};

async function mockApi(page: Page, overlayPosts: Array<Record<string, unknown>> = []) {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === "/api/v1/assets") {
      return route.fulfill({
        json: {
          ok: true,
          assets: [
            {
              id: "asset-1",
              name: "logo.png",
              kind: "image",
              path: "/tmp/logo.png",
              tags: [],
              added_at: "2026-10-24T00:00:00Z"
            }
          ]
        }
      });
    }
    if (path === "/api/v1/jobs/job-1/timeline/overlays") {
      overlayPosts.push(JSON.parse(route.request().postData() ?? "{}"));
      return route.fulfill({
        json: {
          ok: true,
          overlays: [
            {
              overlay_id: "o1",
              asset_id: "asset-1",
              path: "/tmp/logo.png",
              start_frame: 0,
              duration_frames: 90,
              position_x: 0.5,
              position_y: 0.5,
              width_ratio: 0.25,
              opacity: 1,
              kind: "image"
            }
          ]
        }
      });
    }
    if (path === "/api/v1/system") return route.fulfill({ json: system });
    if (path === "/api/v1/jobs") return route.fulfill({ json: { ok: true, jobs: [job] } });
    if (path === "/api/v1/jobs/job-1/timeline") {
      if (route.request().method() === "PATCH") {
        return route.fulfill({ json: { ok: true, revision: 4, can_undo: true, can_redo: false, warning: "Re-run export." } });
      }
      return route.fulfill({ json: timeline });
    }
    if (path === "/api/v1/jobs/job-1/timeline/waveform") {
      const buckets = Number(url.searchParams.get("buckets") ?? "60");
      return route.fulfill({
        json: {
          ok: true,
          bucket_sec: 0.05,
          start_sec: 0,
          end_sec: 3,
          peaks: Array.from({ length: buckets }, (_value, index) =>
            Math.abs(Math.sin(index / 3))
          )
        }
      });
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

test("shows full backend render error details", async ({ page }) => {
  await page.route("**/api/v1/jobs/job-1/render", (route) =>
    route.fulfill({
      status: 202,
      json: { ok: true, render: { job_id: "job-1", status: "queued", percent: 0 } }
    })
  );
  await page.route("**/api/v1/jobs/job-1/render/status", (route) =>
    route.fulfill({
      json: {
        job_id: "job-1",
        status: "failed",
        percent: 100,
        message: "Render failed",
        error: "ffmpeg was killed by SIGKILL",
        error_details: {
          code: "ingest_failed",
          message: "ffmpeg was killed by SIGKILL",
          command: "ffmpeg -i source.mp4",
          returncode: -9,
          signal: 9
        }
      }
    })
  );

  await page.getByRole("button", { name: "Render MP4" }).click();

  const banner = page.getByTestId("timeline-error");
  await expect(banner).toContainText("ffmpeg was killed by SIGKILL");
  await expect(banner).toContainText("returncode: -9");
  await expect(banner).toContainText("signal: 9");
  await expect(banner).toContainText("ffmpeg -i source.mp4");
});

test("puts the preview above the timeline canvas", async ({ page }) => {
  const preview = page.getByTestId("timeline-preview");
  const canvas = page.getByTestId("timeline-canvas");
  await expect(preview).toBeVisible();
  await expect(canvas).toBeVisible();
  const previewBox = await preview.boundingBox();
  const canvasBox = await canvas.boundingBox();
  expect(previewBox?.y ?? 0).toBeLessThan(canvasBox?.y ?? 0);
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

test("requests real waveform peaks for every audio clip", async ({ page }) => {
  const requests: string[] = [];
  page.on("request", (request) => {
    if (request.url().includes("/timeline/waveform")) requests.push(request.url());
  });

  await page.reload();
  await expect(page.getByTestId("timeline-canvas")).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "Auto preview" })).toBeVisible();

  await expect.poll(() => requests.length).toBeGreaterThan(0);
  expect(requests[0]).toContain("buckets=");
  await expect.poll(() => requests.some((url) => url.includes("start=10.5"))).toBe(true);
  await expect.poll(() => requests.some((url) => url.includes("start=40"))).toBe(true);
});

test("sends If-Match with the loaded timeline revision", async ({ page }) => {
  let ifMatch = "";
  await page.route("**/api/v1/jobs/job-1/timeline", async (route) => {
    if (route.request().method() === "PATCH") {
      ifMatch = route.request().headers()["if-match"] ?? "";
      return route.fulfill({
        json: { ok: true, revision: 4, can_undo: true, can_redo: false, warning: "Re-run export." }
      });
    }
    return route.fulfill({ json: timeline });
  });

  const canvas = page.getByTestId("timeline-canvas");
  await canvas.click({ position: { x: 150, y: 80 } });
  await page.getByRole("button", { name: "Move", exact: true }).click();

  await expect.poll(() => ifMatch).toBe('"timeline-3"');
});

test("reuses a current preview and an existing render", async ({ page }) => {
  await page.route("**/api/v1/jobs/job-1/preview/status", (route) =>
    route.fulfill({
      json: {
        ok: true,
        job_id: "job-1",
        status: "ready",
        percent: 100,
        revision: 3,
        ready: true
      }
    })
  );
  await page.route("**/api/v1/jobs/job-1/render/status", (route) =>
    route.fulfill({
      json: { ok: true, job_id: "job-1", status: "ready", percent: 100, ready: true }
    })
  );

  await page.reload();
  await expect(page.getByTestId("timeline-canvas")).toBeVisible();
  await expect(page.locator("video")).toBeVisible();
  await expect(page.getByRole("link", { name: "Download" })).toBeVisible();
});

test("marks the preview as outdated after an edit", async ({ page }) => {
  const canvas = page.getByTestId("timeline-canvas");
  await expect(canvas).toBeVisible();
  await canvas.click({ position: { x: 150, y: 80 } });
  await page.getByRole("button", { name: "Move", exact: true }).click();

  await expect(page.getByText("preview outdated")).toBeVisible();
});


test("drags a library asset onto the timeline as an overlay", async ({ page }) => {
  const posts: Array<Record<string, unknown>> = [];
  await page.route("**/api/v1/assets", (route) =>
    route.fulfill({
      json: {
        ok: true,
        assets: [
          {
            id: "asset-1",
            name: "logo.png",
            kind: "image",
            path: "/tmp/logo.png",
            tags: [],
            added_at: "2026-10-24T00:00:00Z"
          }
        ]
      }
    })
  );
  await page.route("**/api/v1/jobs/job-1/timeline/overlays", (route) => {
    posts.push(JSON.parse(route.request().postData() ?? "{}"));
    return route.fulfill({
      json: { ok: true, overlays: [] }
    });
  });
  await page.goto("/#timeline");
  const rail = page.getByTestId("asset-rail");
  await expect(rail.getByText("logo.png")).toBeVisible();
  await page.waitForTimeout(800);

  await page.evaluate(() => {
    const chip = document.querySelector('[data-testid="asset-rail"] [draggable="true"]');
    const target = document.querySelector('[data-testid="timeline-scroller"]');
    if (!chip || !target) throw new Error("drag endpoints missing");
    const data = new DataTransfer();
    chip.dispatchEvent(new DragEvent("dragstart", { dataTransfer: data, bubbles: true }));
    const rect = target.getBoundingClientRect();
    const options = {
      dataTransfer: data,
      bubbles: true,
      clientX: rect.left + 320,
      clientY: rect.top + 60
    };
    target.dispatchEvent(new DragEvent("dragover", options));
    target.dispatchEvent(new DragEvent("drop", options));
  });

  await expect.poll(() => posts.length).toBeGreaterThan(0);
  expect(posts[0]["asset_id"]).toBe("asset-1");
  expect(posts[0]["path"]).toBe("/tmp/logo.png");
  expect(Number(posts[0]["start_sec"])).toBeGreaterThanOrEqual(0);
});
