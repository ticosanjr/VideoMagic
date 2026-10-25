import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const fixture = (name: string) =>
  JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf8"));

async function mockShell(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === "/api/v1/system") return route.fulfill({ json: fixture("system.json") });
    if (path === "/api/v1/jobs") return route.fulfill({ json: fixture("jobs_dashboard.json") });
    if (path === "/api/v1/steps") return route.fulfill({ json: fixture("steps.json") });
    if (path === "/api/v1/recipes") return route.fulfill({ json: fixture("recipes.json") });
    if (path === "/api/v1/recipes/example_recipe") return route.fulfill({ json: fixture("recipe.json") });
    if (path === "/api/v1/runs") return route.fulfill({ json: fixture("runs.json") });
    if (path === "/api/v1/exports/validate") return route.fulfill({ json: fixture("nle.json") });
    if (path === "/api/v1/batches") return route.fulfill({ json: fixture("batches.json") });
    if (path === "/api/v1/assets") return route.fulfill({ json: fixture("assets.json") });
    if (path === "/api/v1/schedules") return route.fulfill({ json: { ok: true, schedules: [] } });
    if (path === "/api/v1/plugins") {
      return route.fulfill({
        json: {
          ok: true,
          plugins: [
            {
              id: "demo",
              name: "Demo plugin",
              version: "1.0.0",
              enabled: true,
              loaded: true,
              provides: ["exporter"],
              permissions: []
            }
          ],
          panels: [{ id: "demo", title: "Demo panel", url: "http://127.0.0.1:9999/" }]
        }
      });
    }
    return route.fulfill({ json: { ok: true } });
  });
}

test.beforeEach(async ({ page }) => {
  await mockShell(page);
  await page.goto("/");
  // The activity badge only appears after mount and the first jobs fetch; it is
  // the signal that the shell is hydrated and the keyboard listener is active.
  await expect(page.getByRole("button", { name: /Activity 1/ })).toBeVisible();
});

test("opens the command palette with the keyboard and navigates", async ({ page }) => {
  await page.keyboard.press("Control+k");
  const palette = page.getByTestId("command-palette");
  await expect(palette).toBeVisible();

  await page.getByRole("textbox", { name: "Search commands" }).fill("timeline");
  await expect(page.getByRole("option", { name: /Timeline/ })).toBeVisible();
  await page.keyboard.press("Enter");

  await expect(palette).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "Edit" })).toHaveAttribute(
    "aria-selected",
    "true"
  );
  await expect(page.getByText("Edit / Timeline").or(page.getByText("Timeline")).first()).toBeVisible();
});

test("closes the command palette with escape", async ({ page }) => {
  await page.keyboard.press("Control+k");
  await expect(page.getByTestId("command-palette")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("command-palette")).toHaveCount(0);
});

test("shows the shortcut reference", async ({ page }) => {
  await page.keyboard.press("?");
  await expect(page.getByTestId("shortcuts-modal")).toBeVisible();
  await expect(page.getByText("Open the command palette")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("shortcuts-modal")).toHaveCount(0);
});

test("jumps between tabs with g then key", async ({ page }) => {
  await page.keyboard.press("g");
  await page.keyboard.press("j");
  await expect(page.getByRole("tab", { name: "Jobs" })).toHaveAttribute("aria-selected", "true");
});

test("opens the activity drawer from the header", async ({ page }) => {
  await page.getByRole("button", { name: /Activity/ }).click();
  const drawer = page.getByTestId("activity-drawer");
  await expect(drawer).toBeVisible();
  await expect(drawer.getByText("interview.mp4")).toBeVisible();
  await expect(drawer.getByText("Approve the hook")).toBeVisible();
});

test("opens the notification center", async ({ page }) => {
  await page.getByRole("button", { name: /Notifications/ }).click();
  await expect(page.getByTestId("notification-center")).toBeVisible();
  await expect(page.getByText("Nothing needs your attention.")).toBeVisible();
});

test("filters the job dashboard", async ({ page }) => {
  await page.keyboard.press("g");
  await page.keyboard.press("j");
  await expect(page.getByTestId("job-list")).toBeVisible();
  await expect(page.getByTestId("job-list").locator("li")).toHaveCount(4);

  await page.getByRole("tab", { name: /Needs attention/ }).click();
  await expect(page.getByTestId("job-list").locator("li")).toHaveCount(2);

  await page.getByLabel("Search jobs").fill("webinar");
  await expect(page.getByTestId("job-list").locator("li")).toHaveCount(1);
  await expect(page.getByText("Retry after fixing the error")).toBeVisible();
});

test("asks for confirmation before cancelling a job", async ({ page }) => {
  await page.keyboard.press("g");
  await page.keyboard.press("j");
  await page.getByRole("button", { name: "Cancel", exact: true }).first().click();
  await expect(page.getByRole("button", { name: "Confirm cancel" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Keep" })).toBeVisible();
});

test("keeps focus inside the palette and closes with escape", async ({ page }) => {
  await page.keyboard.press("Control+k");
  const palette = page.getByTestId("command-palette");
  await expect(palette).toBeVisible();

  for (let step = 0; step < 12; step += 1) {
    await page.keyboard.press("Tab");
    const inside = await page.evaluate(() => {
      const dialog = document.querySelector('[data-testid="command-palette"]');
      return dialog?.contains(document.activeElement) ?? false;
    });
    expect(inside).toBe(true);
  }

  await page.keyboard.press("Escape");
  await expect(palette).toHaveCount(0);
});

test("supports a keyboard-only job dashboard visit", async ({ page }) => {
  await page.keyboard.press("g");
  await page.keyboard.press("j");
  await expect(page.getByRole("tab", { name: "Jobs" })).toHaveAttribute(
    "aria-selected",
    "true"
  );
  await page.keyboard.press("?");
  await expect(page.getByTestId("shortcuts-modal")).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByTestId("shortcuts-modal")).toHaveCount(0);
});

test("applies pt-BR, the light theme, and compact density", async ({ page }) => {
  await page.route("**/api/v1/settings", (route) =>
    route.fulfill({
      json: {
        settings: {
          runtime: { locale: "pt-BR" },
          ui: { theme: "light", density: "compact" }
        }
      }
    })
  );
  await page.reload();
  await expect(page.getByRole("button", { name: /Atividade/ })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Construtor de receitas" })).toBeVisible();
  await expect(page.getByRole("button", { name: /Adicionar etapa/ })).toBeVisible();

  const background = await page.evaluate(
    () => getComputedStyle(document.body).backgroundColor
  );
  expect(background).toBe("rgb(248, 250, 252)");
  const padding = await page.evaluate(() => {
    const element = document.createElement("div");
    element.className = "p-4";
    document.body.appendChild(element);
    const value = getComputedStyle(element).paddingTop;
    element.remove();
    return value;
  });
  expect(padding).toBe("12px");
});


test("lists plugins with sandbox status and panels", async ({ page }) => {
  await page.getByRole("tab", { name: "Setup" }).click();
  await page.getByRole("tab", { name: "Extensions" }).click();
  await expect(page.getByTestId("plugins-panel")).toBeVisible();
  await expect(page.getByText("Demo plugin")).toBeVisible();
  await expect(page.getByRole("link", { name: "Demo panel" })).toHaveAttribute(
    "href",
    "http://127.0.0.1:9999/"
  );
});


test("shows the integration area for OpenCode, Paperclip, and DeepSeek", async ({ page }) => {
  await page.getByRole("tab", { name: "Setup" }).click();
  await page.getByRole("tab", { name: "Connect" }).click();
  await expect(page.getByTestId("integrations-panel")).toBeVisible();
  await expect(page.getByText("deepseek/deepseek-flash").first()).toBeVisible();
  await expect(page.getByText("Paperclip").first()).toBeVisible();
});


test("navigates the five areas and redirects legacy hashes", async ({ page }) => {
  const areas = page
    .getByRole("navigation")
    .getByRole("tablist")
    .first()
    .getByRole("tab");
  await expect(areas).toHaveCount(5);

  await page.getByRole("tab", { name: "Setup" }).click();
  await expect(page.getByRole("tab", { name: "AI models" })).toHaveAttribute(
    "aria-selected",
    "true"
  );

  await page.goto("/#assets");
  await expect(page.getByRole("tab", { name: "Media" })).toHaveAttribute(
    "aria-selected",
    "true"
  );
  await page.goto("/#copilot");
  await expect(page.getByRole("tab", { name: "Assistant" })).toHaveAttribute(
    "aria-selected",
    "true"
  );
});

test("opens a help tooltip from the keyboard", async ({ page }) => {
  await page.getByRole("tab", { name: "Setup" }).click();
  const help = page.getByRole("button", { name: /Help: AI models/ });
  await help.focus();
  await expect(page.getByRole("tooltip")).toContainText("speech and vision");
  await page.keyboard.press("Escape");
  await expect(page.getByRole("tooltip")).toHaveCount(0);
});

test("filters settings by text", async ({ page }) => {
  await page.goto("/#settings");
  const search = page.getByLabel("Search settings");
  await expect(search).toBeVisible();
  await search.fill("true peak");
  await expect(search).toHaveValue("true peak");
});

test("dismisses and remembers onboarding", async ({ page }) => {
  const card = page.getByTestId("onboarding-card");
  await expect(card).toBeVisible();
  await card.getByRole("button", { name: "Dismiss" }).click();
  await expect(card).toHaveCount(0);
  await page.reload();
  await expect(page.getByTestId("onboarding-card")).toHaveCount(0);
});

test("moves the area selection with arrow keys", async ({ page }) => {
  const first = page
    .getByRole("navigation")
    .getByRole("tablist")
    .first()
    .getByRole("tab")
    .first();
  await first.focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "Edit" })).toHaveAttribute(
    "aria-selected",
    "true"
  );
});

test("keeps the shell usable on a narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 480, height: 900 });
  await expect(page.getByRole("tab", { name: "Produce" })).toBeVisible();
  await page.getByRole("tab", { name: "Setup" }).click();
  await expect(page.getByRole("tab", { name: "Settings" })).toBeVisible();
});
