import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const fixture = (name: string) =>
  JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf8"));

const gpuStatus = {
  ok: true,
  status: {
    ok: true,
    mode: "auto",
    worker_url: "http://192.168.1.45:8766",
    execution_node: "remote_gpu:worker-1",
    available: true,
    worker_id: "worker-1",
    hostname: "gpu-host",
    ip_local: "192.168.1.45",
    port: 8766,
    gpu_name: "RTX 3060",
    vram_free_mb: 4096,
    vram_total_mb: 12288,
    vram_used_mb: 8192,
    gpu_utilization: 12,
    temperature_c: 44,
    capabilities: ["asr", "render_nvenc"],
    models: [],
    queue_depth: 0,
    message: "",
    fallback_local: true,
    shared_mount_enabled: false,
    shared_linux_path: "",
    shared_windows_path: "",
    discovery_enabled: true,
    capabilities_enabled: { asr: true, render_nvenc: true }
  }
};

async function mockGpu(page: Page) {
  const calls: Record<string, unknown> = {};
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    const method = route.request().method();
    if (path === "/api/v1/system") return route.fulfill({ json: fixture("system.json") });
    if (path === "/api/v1/jobs") return route.fulfill({ json: { ok: true, jobs: [] } });
    if (path === "/api/v1/interactions") {
      return route.fulfill({ json: { ok: true, interactions: [] } });
    }
    if (path === "/api/v1/gpu/status") return route.fulfill({ json: gpuStatus });
    if (path === "/api/v1/gpu/discovery") {
      return route.fulfill({
        json: {
          ok: true,
          enabled: true,
          workers: [
            {
              worker_id: "worker-1",
              hostname: "gpu-host",
              ip_local: "192.168.1.45",
              port: 8766,
              url: "http://192.168.1.45:8766",
              gpu_name: "RTX 3060",
              vram_total_mb: 12288,
              vram_free_mb: 4096,
              status: "idle",
              queue_depth: 0,
              capabilities: ["asr"],
              version: "3.4.0",
              seen_at: Date.now() / 1000
            }
          ]
        }
      });
    }
    if (path === "/api/v1/gpu/connect" && method === "POST") {
      calls.connect = JSON.parse(route.request().postData() ?? "{}");
      return route.fulfill({
        json: { ok: true, connected: true, status: gpuStatus.status }
      });
    }
    if (path === "/api/v1/gpu/settings" && method === "PATCH") {
      calls.patch = JSON.parse(route.request().postData() ?? "{}");
      return route.fulfill({
        json: { ok: true, gpu: {}, status: gpuStatus.status }
      });
    }
    if (path === "/api/v1/gpu/benchmark" && method === "POST") {
      calls.benchmark = true;
      return route.fulfill({
        json: { ok: true, kind: "connectivity", latency_ms: 18, speedup: null, worker: {} }
      });
    }
    if (path === "/api/v1/gpu-worker/package" && method === "POST") {
      calls.kit = true;
      return route.fulfill({
        status: 200,
        headers: { "content-type": "application/zip" },
        body: Buffer.from("PK")
      });
    }
    return route.fulfill({ json: { ok: true } });
  });
  return calls;
}

test("pairs, benchmarks, and configures GPU acceleration", async ({ page }) => {
  const calls = await mockGpu(page);
  await page.goto("/#gpu");

  await expect(page.getByTestId("gpu-panel")).toBeVisible();
  await expect(page.getByTestId("gpu-status-line")).toContainText("RTX 3060");
  await expect(page.getByTestId("gpu-status-pill")).toContainText("GPU: RTX 3060");

  await page.getByTestId("gpu-discover").click();
  await expect(page.getByTestId("gpu-discovered-list")).toContainText("gpu-host");

  await page.getByText("Advanced pairing").click();
  await page.getByTestId("gpu-manual-url").fill("http://192.168.1.45:8766");
  await page.getByTestId("gpu-manual-token").fill("secret-token");
  await page.getByTestId("gpu-connect").click();
  await expect(page.getByTestId("gpu-notice")).toContainText("Worker connected");
  expect(calls.connect).toMatchObject({
    worker_url: "http://192.168.1.45:8766",
    token: "secret-token"
  });

  await page.getByTestId("gpu-benchmark").click();
  await expect(page.getByTestId("gpu-benchmark-result")).toContainText("18 ms");
  expect(calls.benchmark).toBe(true);

  await page.getByTestId("gpu-cap-asr").uncheck();
  await expect.poll(() => calls.patch).toMatchObject({ capabilities: { asr: false } });

  await page.getByTestId("gpu-download-kit").click();
  await expect.poll(() => calls.kit).toBe(true);
});

test("switches the pill between automatic and local modes", async ({ page }) => {
  const calls = await mockGpu(page);
  await page.goto("/#gpu");
  await expect(page.getByTestId("gpu-status-pill")).toContainText("RTX 3060");
  await page.getByTestId("gpu-status-pill").click();
  await expect(page.getByTestId("gpu-popover")).toBeVisible();
  await page.getByTestId("gpu-mode-local").click();
  await expect.poll(() => calls.patch).toMatchObject({ mode: "local_only" });
  await page.getByTestId("gpu-open-settings").click();
  await expect(page.getByTestId("gpu-panel")).toBeVisible();
});
