import { expect, test, type Page } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { existsSync, mkdirSync, readFileSync } from "node:fs";

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
  source_duration_sec: 10,
  live_eligible: false,
  live_reason: "test fixture",
  inactive: [],
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

test("uses the mobile list fallback for clip selection", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 900 });
  const mobile = page.getByTestId("timeline-mobile");
  await expect(mobile).toBeVisible();
  await expect(mobile).toContainText("v1");
  await expect(mobile).toContainText("v2");
  await mobile.getByRole("button", { name: "Inspect" }).first().click();
  await expect(page.getByText("Selected clip")).toBeVisible();
  await expect(page).toHaveScreenshot("timeline-mobile.png", {
    animations: "disabled",
    maxDiffPixelRatio: 0.02
  });
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

test("puts the preview above the timeline", async ({ page }) => {
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
  const headers = page.getByTestId("timeline-track-headers");
  await expect(headers.getByRole("button", { name: "Hide V1 · VIDEO" })).toBeVisible();
  await expect(headers.getByRole("button", { name: "Mute A1 · DIALOGUE" })).toBeVisible();
});

test("splits at the official playhead in normal and Recut views", async ({ page }) => {
  const patches: Array<Record<string, unknown>> = [];
  page.on("request", (request) => {
    if (request.method() === "PATCH" && request.url().endsWith("/timeline")) {
      patches.push(JSON.parse(request.postData() ?? "{}"));
    }
  });
  const canvas = page.getByTestId("timeline-canvas");
  await canvas.scrollIntoViewIfNeeded();
  await canvas.click({ position: { x: 96 + 140, y: 60 } });
  const split = page.getByRole("button", { name: "Split" });
  await expect(split).toBeEnabled();
  await split.click();
  await expect.poll(() => patches.length).toBeGreaterThan(0);
  expect(patches.at(-1)).toMatchObject({ clip_id: "v1", action: "split" });

  await page.getByRole("button", { name: "Recut" }).click();
  await page.getByTestId("recut-active-v1").click();
  await page.keyboard.press("s");
  await expect.poll(() => patches.length).toBeGreaterThan(1);
  expect(patches.at(-1)).toMatchObject({ clip_id: "v1", action: "split" });
});

test("fit selection zooms to the selected clip", async ({ page }) => {
  const canvas = page.getByTestId("timeline-canvas");
  await canvas.scrollIntoViewIfNeeded();
  await canvas.click({ position: { x: 96 + 140, y: 60 } });
  const zoom = page.getByTestId("timeline-zoom");
  const before = Number(await zoom.inputValue());
  await page.getByRole("button", { name: "Fit selection" }).click();
  await expect.poll(async () => Number(await zoom.inputValue())).toBeGreaterThan(before);
});

test("opens the timeline while a recipe is still exporting", async ({ page }) => {
  await page.route("**/api/v1/jobs", (route) =>
    route.fulfill({
      json: {
        ok: true,
        jobs: [
          {
            ...job,
            status: "running",
            progress: 80,
            stage: "export",
            message: "Exporting resolve",
            timeline_ready: true
          }
        ]
      }
    })
  );
  await page.reload();
  await expect(page.getByTestId("timeline-canvas")).toBeVisible();
  await expect(page.getByText(/rev 3/)).toBeVisible();
});


test("clicking the timeline moves the playhead and the timeline stays fixed", async ({ page }) => {
  const canvas = page.getByTestId("timeline-canvas");
  await canvas.scrollIntoViewIfNeeded();
  const before = await canvas.boundingBox();
  await canvas.click({ position: { x: 96 + 80 * 2, y: 60 } });
  await expect(page.getByTestId("timeline-timecode")).not.toContainText("00:00:00");
  const after = await canvas.boundingBox();
  expect(Math.abs((before?.y ?? 0) - (after?.y ?? 0))).toBeLessThan(2);
});

test("next segment and wheel zoom work from the timeline", async ({ page }) => {
  await page.getByRole("button", { name: "Next segment" }).click();
  await expect(page.getByTestId("timeline-timecode")).toContainText("00:03");
  const zoom = page.getByTestId("timeline-zoom");
  const before = Number(await zoom.inputValue());
  const canvas = page.getByTestId("timeline-canvas");
  const box = await canvas.boundingBox();
  await page.mouse.move((box?.x ?? 0) + 200, (box?.y ?? 0) + 120);
  await page.mouse.wheel(0, -120);
  await expect.poll(async () => Number(await zoom.inputValue())).toBeGreaterThan(before);
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


test("does not reload deliverables for a timeline edit", async ({ page }) => {
  const deliverableRequests: string[] = [];
  page.on("request", (request) => {
    const url = new URL(request.url());
    if (
      url.pathname.endsWith("/review") ||
      url.pathname.endsWith("/thumbnails") ||
      url.pathname.endsWith("/thumbnails/metrics") ||
      url.pathname.endsWith("/review/comments") ||
      url.pathname === "/api/v1/assets"
    ) {
      deliverableRequests.push(url.pathname);
    }
  });

  await page.reload();
  await expect(page.getByTestId("timeline-canvas")).toBeVisible();
  const before = deliverableRequests.length;

  const canvas = page.getByTestId("timeline-canvas");
  await canvas.click({ position: { x: 150, y: 80 } });
  await page.getByRole("button", { name: "Move", exact: true }).click();
  await expect(page.getByText(/Timeline revision/)).toBeVisible();

  expect(deliverableRequests.length).toBe(before);
});


test("shows inactive segments in the Recut view", async ({ page }) => {
  const inactiveTimeline = {
    ...timeline,
    duration_sec: 3,
    source_duration_sec: 8,
    video: [timeline.video[0]],
    audio: [{ ...timeline.audio[0], source_in_sec: 0, source_out_sec: 3 }],
    inactive: [
      {
        id: "v2",
        reason: "retake",
        video_start_sec: 3,
        video_end_sec: 8,
        audio_start_sec: 3,
        audio_end_sec: 8
      }
    ]
  };
  const actions: string[] = [];
  await page.route("**/api/v1/jobs/job-1/timeline", async (route) => {
    if (route.request().method() === "PATCH") {
      actions.push(JSON.parse(route.request().postData() ?? "{}").action);
      return route.fulfill({
        json: { ok: true, revision: 4, can_undo: true, can_redo: false, warning: "" }
      });
    }
    return route.fulfill({ json: inactiveTimeline });
  });

  await page.reload();
  const recut = page.getByRole("button", { name: "Recut", exact: true });
  await expect(async () => {
    await recut.click();
    await expect(page.getByTestId("recut-canvas")).toBeVisible({ timeout: 1000 });
  }).toPass();

  await expect(page.getByTestId("recut-active-v1")).toHaveClass(/bg-sky-500/);
  await expect(page.getByTestId("recut-inactive-v2")).toHaveClass(/bg-rose-500/);
  await page.getByTestId("recut-inactive-v2").click();
  await expect(page.getByTestId("recut-selection")).toContainText("retake");

  await page.getByRole("button", { name: "Activate", exact: true }).click();
  await expect.poll(() => actions).toContain("activate");
});

test("persists the Recut view choice", async ({ page }) => {
  const recut = page.getByRole("button", { name: "Recut", exact: true });
  await recut.click();
  await expect(page.getByTestId("recut-canvas")).toBeVisible();
  await page.reload();
  await expect(page.getByTestId("recut-canvas")).toBeVisible();
});


test("edits an inactive cut boundary from the Recut inspector", async ({ page }) => {
  const inactiveTimeline = {
    ...timeline,
    duration_sec: 3,
    source_duration_sec: 8,
    video: [timeline.video[0]],
    audio: [{ ...timeline.audio[0], source_in_sec: 0, source_out_sec: 3 }],
    inactive: [
      {
        id: "v2",
        reason: "silence",
        video_start_sec: 3,
        video_end_sec: 8,
        audio_start_sec: 3,
        audio_end_sec: 8
      }
    ]
  };
  const payloads: Array<Record<string, unknown>> = [];
  await page.route("**/api/v1/jobs/job-1/timeline", async (route) => {
    if (route.request().method() === "PATCH") {
      payloads.push(JSON.parse(route.request().postData() ?? "{}"));
      return route.fulfill({
        json: { ok: true, revision: 4, can_undo: true, can_redo: false, warning: "" }
      });
    }
    return route.fulfill({ json: inactiveTimeline });
  });

  await page.reload();
  const recut = page.getByRole("button", { name: "Recut", exact: true });
  await expect(async () => {
    await recut.click();
    await expect(page.getByTestId("recut-canvas")).toBeVisible({ timeout: 1000 });
  }).toPass();

  await page.getByTestId("recut-inactive-v2").click();
  await expect(page.getByTestId("recut-selection")).toContainText("silence");
  await page.getByTestId("recut-start").fill("3.5");
  await page.getByTestId("recut-end").fill("8");
  await page.getByRole("button", { name: "Apply cut", exact: true }).click();

  await expect.poll(() => payloads.map((item) => item.action)).toContain("recut");
  expect(payloads.at(-1)).toMatchObject({
    clip_id: "v2",
    action: "recut",
    start_sec: 3.5,
    end_sec: 8
  });
});


test("shows live playback for hard-cut timelines and falls back otherwise", async ({ page }) => {
  const liveTimeline = {
    ...timeline,
    duration_sec: 5,
    source_duration_sec: 8,
    live_eligible: true,
    live_reason: "hard cuts only",
    inactive: [
      {
        id: "v2",
        reason: "silence",
        video_start_sec: 3,
        video_end_sec: 8,
        audio_start_sec: 3,
        audio_end_sec: 8
      }
    ],
    video: [timeline.video[0]]
  };
  await page.route("**/api/v1/jobs/job-1/timeline", (route) =>
    route.fulfill({ json: liveTimeline })
  );
  await page.reload();
  const recut = page.getByRole("button", { name: "Recut", exact: true });
  await expect(async () => {
    await recut.click();
    await expect(page.getByTestId("live-player")).toBeVisible({ timeout: 1000 });
  }).toPass();

  await expect(page.getByTestId("live-player")).toBeVisible();
  await expect(page.getByRole("button", { name: "Play", exact: true })).toBeVisible();
});


test("composes live titles and overlays over the source", async ({ page }) => {
  const composed = {
    ...timeline,
    duration_sec: 3,
    source_duration_sec: 8,
    live_eligible: true,
    live_reason: "transitions, overlays, and titles are live",
    video: [
      {
        ...timeline.video[0],
        transition: "crossfade",
        transition_frames: 10,
        transition_audio: true
      }
    ],
    audio: [{ ...timeline.audio[0], source_in_sec: 0, source_out_sec: 3 }],
    overlays: [
      {
        overlay_id: "o1",
        asset_id: "asset-1",
        path: "/tmp/logo.png",
        start_frame: 0,
        duration_frames: 75,
        position_x: 0.2,
        position_y: 0.8,
        width_ratio: 0.3,
        opacity: 0.8,
        kind: "image"
      }
    ],
    titles: [
      {
        start_sec: 0,
        end_sec: 2,
        text: "Intro title",
        style: "title"
      },
      {
        start_sec: 0,
        end_sec: 2,
        text: "Speaker 1",
        style: "lower_third"
      }
    ]
  };
  await page.route("**/api/v1/jobs/job-1/timeline", (route) =>
    route.fulfill({ json: composed })
  );
  await page.reload();
  const recut = page.getByRole("button", { name: "Recut", exact: true });
  await expect(async () => {
    await recut.click();
    await expect(page.getByTestId("live-composite")).toBeVisible({ timeout: 1000 });
  }).toPass();

  await expect(page.getByTestId("live-titles")).toContainText("Intro title");
  await expect(page.getByTestId("live-titles")).toContainText("Speaker 1");
  await expect(page.getByTestId("live-overlays").locator("img")).toHaveCount(1);
});


function playbackFixture(): string | null {
  const directory = new URL("./fixtures/", import.meta.url);
  const path = new URL("playback.webm", directory).pathname;
  if (existsSync(path)) return path;
  try {
    mkdirSync(directory, { recursive: true });
    execFileSync(
      "ffmpeg",
      [
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        "color=c=#1f2937:s=160x90:d=5",
        "-f",
        "lavfi",
        "-i",
        "sine=frequency=440:duration=5",
        "-c:v",
        "libvpx",
        "-b:v",
        "120k",
        "-c:a",
        "libvorbis",
        "-shortest",
        path
      ],
      { stdio: "ignore", timeout: 30000 }
    );
    return path;
  } catch {
    return null;
  }
}

test("plays from the official playhead after a timeline seek", async ({ page }) => {
  const fixture = playbackFixture();
  test.skip(!fixture, "ffmpeg with libvpx is unavailable");
  const liveTimeline = {
    ...timeline,
    duration_sec: 5,
    source_duration_sec: 5,
    live_eligible: true,
    live_reason: "webm fixture",
    inactive: [],
    video: [
      {
        ...timeline.video[0],
        start_sec: 0,
        end_sec: 5,
        source_in_frame: 0,
        source_out_frame: 125,
        source_start_sec: 0,
        source_end_sec: 5
      }
    ],
    audio: [
      {
        ...timeline.audio[0],
        start_sec: 0,
        end_sec: 5,
        source_in_sec: 0,
        source_out_sec: 5
      }
    ]
  };
  await page.route("**/api/v1/jobs/job-1/timeline", (route) =>
    route.fulfill({ json: liveTimeline })
  );
  await page.route("**/api/v1/jobs/job-1/source/file", (route) =>
    route.fulfill({
      status: 200,
      contentType: "video/webm",
      body: readFileSync(fixture!)
    })
  );
  await page.reload();
  await expect(page.getByTestId("live-player")).toBeVisible();
  const canvas = page.getByTestId("timeline-canvas");
  await canvas.scrollIntoViewIfNeeded();
  await canvas.click({ position: { x: 96 + 140, y: 60 } });
  await expect(page.getByTestId("timeline-timecode")).toContainText("00:02");
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await expect
    .poll(
      async () =>
        page.evaluate(() => {
          const video = document.querySelector(
            '[data-testid="live-video-a"]'
          ) as HTMLVideoElement | null;
          return video?.currentTime ?? 0;
        }),
      { timeout: 5000 }
    )
    .toBeGreaterThan(1.5);
  await page.getByRole("button", { name: "Pause", exact: true }).click();
});

test("keeps the Konva stage within browser canvas limits for long media", async ({ page }) => {
  const longTimeline = {
    ...timeline,
    duration_sec: 1200,
    source_duration_sec: 1200,
    video: [
      {
        ...timeline.video[0],
        start_sec: 0,
        end_sec: 1200,
        source_in_frame: 0,
        source_out_frame: 30000,
        source_start_sec: 0,
        source_end_sec: 1200
      }
    ],
    audio: [
      {
        ...timeline.audio[0],
        start_sec: 0,
        end_sec: 1200,
        source_in_sec: 0,
        source_out_sec: 1200
      }
    ]
  };
  await page.route("**/api/v1/jobs/job-1/timeline", (route) =>
    route.fulfill({ json: longTimeline })
  );
  await page.reload();
  const canvas = page.getByTestId("timeline-canvas");
  await expect(canvas).toBeVisible();
  const sizes = await canvas.evaluate((element) => {
    const stageCanvas = element.querySelector("canvas") as HTMLCanvasElement | null;
    const scroller = element.querySelector(
      '[data-testid="timeline-scroller"]'
    ) as HTMLElement | null;
    return {
      canvasWidth: stageCanvas?.width ?? 0,
      contentWidth: scroller?.scrollWidth ?? 0
    };
  });
  expect(sizes.canvasWidth).toBeGreaterThan(300);
  expect(sizes.canvasWidth).toBeLessThan(8000);
  expect(sizes.contentWidth).toBeGreaterThan(80000);
});

test("keeps the live player at the official cursor across parent updates", async ({ page }) => {
  const fixture = playbackFixture();
  test.skip(!fixture, "ffmpeg with libvpx is unavailable");
  const twoPartTimeline = {
    ...timeline,
    duration_sec: 4,
    source_duration_sec: 5,
    live_eligible: true,
    live_reason: "webm fixture",
    inactive: [],
    video: [
      {
        ...timeline.video[0],
        id: "v1",
        start_sec: 0,
        end_sec: 2,
        source_in_frame: 0,
        source_out_frame: 50,
        source_start_sec: 0,
        source_end_sec: 2
      },
      {
        ...timeline.video[1],
        id: "v2",
        start_sec: 2,
        end_sec: 4,
        source_in_frame: 75,
        source_out_frame: 125,
        source_start_sec: 3,
        source_end_sec: 5
      }
    ],
    audio: [
      {
        ...timeline.audio[0],
        id: "v1",
        start_sec: 0,
        end_sec: 2,
        source_in_sec: 0,
        source_out_sec: 2
      },
      {
        ...timeline.audio[1],
        id: "v2",
        start_sec: 2,
        end_sec: 4,
        source_in_sec: 3,
        source_out_sec: 5
      }
    ]
  };
  await page.route("**/api/v1/jobs/job-1/timeline", (route) =>
    route.fulfill({ json: twoPartTimeline })
  );
  await page.route("**/api/v1/jobs/job-1/source/file", (route) =>
    route.fulfill({
      status: 200,
      contentType: "video/webm",
      body: readFileSync(fixture!)
    })
  );
  await page.reload();
  await expect(page.getByTestId("live-player")).toBeVisible();
  const labels = () =>
    page.evaluate(() =>
      Array.from(document.querySelectorAll("span"))
        .map((span) => span.textContent ?? "")
        .filter((text) => text.startsWith("source ") || text.startsWith("output "))
    );
  const initial = await labels();
  const canvas = page.getByTestId("timeline-canvas");
  await canvas.scrollIntoViewIfNeeded();
  await canvas.click({ position: { x: 96 + 70, y: 60 } });
  await expect(page.getByTestId("timeline-timecode")).toContainText("00:01");
  await expect.poll(async () => (await labels())[1]).not.toBe(initial[1]);
  await page.getByRole("button", { name: "Next segment" }).click();
  await expect.poll(labels).toEqual(["source 3.00s", "output 2.00s"]);
  await expect(page.getByTestId("timeline-timecode")).toContainText("00:02");
});

test("shows source, edited, and removed durations and inspector tabs", async ({ page }) => {
  const durations = page.getByTestId("preview-durations");
  await expect(durations).toContainText("Source total");
  await expect(durations).toContainText("Edited");
  await expect(durations).toContainText("Removed");
  const canvas = page.getByTestId("timeline-canvas");
  await canvas.scrollIntoViewIfNeeded();
  await canvas.click({ position: { x: 96 + 140, y: 60 } });
  await page.getByRole("tab", { name: "Effects" }).click();
  await expect(page.getByTestId("timeline-effects")).toContainText("Clip effects");
  await page.getByRole("tab", { name: "Inspect" }).click();
  await expect(page.getByText("Selected clip", { exact: true })).toBeVisible();
});

test("resizes the preview and persists the follow toggle", async ({ page }) => {
  const preview = page.getByTestId("timeline-preview");
  await preview.scrollIntoViewIfNeeded();
  const before = await preview.boundingBox();
  const heightHandle = page.getByTestId("preview-height-resize");
  const handle = await heightHandle.boundingBox();
  await page.mouse.move((handle?.x ?? 0) + 20, (handle?.y ?? 0) + 2);
  await page.mouse.down();
  await page.mouse.move((handle?.x ?? 0) + 20, (handle?.y ?? 0) + 90, { steps: 5 });
  await page.mouse.up();
  await expect.poll(async () => (await preview.boundingBox())?.height ?? 0).toBeGreaterThan(
    (before?.height ?? 0) + 40
  );
  expect(await page.evaluate(() => localStorage.getItem("videoflow.previewHeight"))).not.toBeNull();

  const follow = page.getByTestId("follow-playhead");
  await expect(follow).toBeChecked();
  await follow.click();
  await expect(follow).not.toBeChecked();
  expect(await page.evaluate(() => localStorage.getItem("videoflow.followPlayhead"))).toBe("false");
  await page.reload();
  await expect(page.getByTestId("follow-playhead")).not.toBeChecked();
});

test("plays a real browser-compatible source and pauses", async ({ page }) => {
  const fixture = playbackFixture();
  test.skip(!fixture, "ffmpeg with libvpx is unavailable");
  const liveTimeline = {
    ...timeline,
    duration_sec: 5,
    source_duration_sec: 5,
    live_eligible: true,
    live_reason: "webm fixture",
    inactive: [],
    video: [
      {
        ...timeline.video[0],
        start_sec: 0,
        end_sec: 5,
        source_in_frame: 0,
        source_out_frame: 125,
        source_start_sec: 0,
        source_end_sec: 5
      }
    ],
    audio: [
      {
        ...timeline.audio[0],
        start_sec: 0,
        end_sec: 5,
        source_in_sec: 0,
        source_out_sec: 5
      }
    ]
  };
  await page.route("**/api/v1/jobs/job-1/timeline", (route) =>
    route.fulfill({ json: liveTimeline })
  );
  await page.route("**/api/v1/jobs/job-1/source/file", (route) =>
    route.fulfill({
      status: 200,
      contentType: "video/webm",
      body: readFileSync(fixture!)
    })
  );
  await page.reload();
  await expect(page.getByTestId("live-player")).toBeVisible();
  await page.getByRole("button", { name: "Play", exact: true }).click();
  await page.waitForTimeout(1000);
  await expect
    .poll(async () => page.getByTestId("timeline-timecode").innerText(), {
      timeout: 5000
    })
    .not.toBe("00:00:00");
  await page.getByRole("button", { name: "Pause", exact: true }).click();
});
