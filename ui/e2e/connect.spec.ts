import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const fixture = (name: string) =>
  JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf8"));

async function mockConnect(page: Page) {
  let bootstrapBody: Record<string, unknown> | null = null;
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/system") return route.fulfill({ json: fixture("system.json") });
    if (path === "/api/v1/jobs") return route.fulfill({ json: { ok: true, jobs: [] } });
    if (path === "/api/v1/system/opencode/workflows") {
      return route.fulfill({ json: { ok: true, workflows: [] } });
    }
    if (path === "/api/v1/styles") {
      return route.fulfill({
        json: {
          ok: true,
          styles: [
            {
              style_id: "canal-paula-reels",
              name: "Canal Paula — Reels",
              aspect_ratio: "9:16",
              summary: "Cortes rápidos",
              file_path: "/styles/canal-paula-reels.md",
              updated_at: "2026-11-16T21:00:00Z"
            },
            {
              style_id: "canal-rafael-tech",
              name: "Canal Rafael — Tech",
              aspect_ratio: "16:9",
              summary: "Tech longform",
              file_path: "/styles/canal-rafael-tech.md",
              updated_at: "2026-11-16T21:00:00Z"
            }
          ]
        }
      });
    }
    if (
      path === "/api/v1/system/bootstrap/opencode" &&
      route.request().method() === "POST"
    ) {
      bootstrapBody = JSON.parse(route.request().postData() ?? "{}");
      return route.fulfill({
        json: {
          ok: true,
          status: "ok",
          target_dir: "/tmp/opencode-studio",
          created_files: [
            "/tmp/opencode-studio/opencode.json",
            "/tmp/opencode-studio/AGENTS.md"
          ],
          skipped_files: [],
          copied_styles: ["canal-paula-reels", "canal-rafael-tech"],
          mcp_servers: ["core"],
          launch_command: 'cd "/tmp/opencode-studio" && opencode',
          sample_project: { ok: true, project_id: "sample" },
          registered_root: true,
          warnings: []
        }
      });
    }
    return route.fulfill({ json: { ok: true } });
  });
  return () => bootstrapBody;
}

test("prepares an OpenCode workspace from Setup → Connect", async ({ page }) => {
  const body = await mockConnect(page);
  await page.goto("/#connect");

  await expect(page.getByTestId("opencode-studio-card")).toBeVisible();
  await expect(page.getByText("canal-paula-reels")).toBeVisible();

  await page.getByTestId("opencode-target").fill("/tmp/opencode-studio");
  await page.getByTestId("opencode-profile").selectOption("core");
  await page.getByLabel("Include 10s sample project").check();
  await page.getByTestId("opencode-bootstrap").click();

  await expect(page.getByTestId("opencode-result")).toBeVisible();
  await expect(page.getByTestId("opencode-launch")).toContainText(
    'cd "/tmp/opencode-studio" && opencode'
  );
  await expect(page.getByText("2 file(s) created")).toBeVisible();
  await expect(page.getByText("Sample 10s project ready")).toBeVisible();

  expect(body()).toMatchObject({
    target_dir: "/tmp/opencode-studio",
    mcp_profile: "core",
    include_sample_project: true
  });
});
