import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const fixture = (name: string) =>
  JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf8"));

const pyprojectVersion =
  /^version = "([^"]+)"/m
    .exec(readFileSync(new URL("../../pyproject.toml", import.meta.url), "utf8"))
    ?.[1] ?? "0.0.0";

async function mockShell(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === "/api/v1/system") {
      return route.fulfill({
        json: { ...fixture("system.json"), version: pyprojectVersion }
      });
    }
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

async function mockProviders(page: Page) {
  await page.route("**/api/v1/capabilities**", (route) =>
    route.fulfill({
      json: { ok: true, external_services_allowed: false, capabilities: [] }
    })
  );
  await page.route("**/api/v1/providers", (route) =>
    route.fulfill({
      json: { ok: true, providers: [], fallbacks: {}, secret_backend: "file:0600" }
    })
  );
  await page.route("**/api/v1/voice-clone/status", (route) =>
    route.fulfill({ json: { ok: true, available: false } })
  );
  await page.route("**/api/v1/voice-clone/profiles", (route) =>
    route.fulfill({ json: { ok: true, profiles: [] } })
  );
}

test.beforeEach(async ({ page }) => {
  await mockShell(page);
  await page.goto("/");
  // The activity badge only appears after mount and the first jobs fetch; it is
  // the signal that the shell is hydrated and the keyboard listener is active.
  await expect(page.getByRole("button", { name: /Activity 1/ })).toBeVisible({ timeout: 20_000 });
});

test("shows backend errors globally with details", async ({ page }) => {
  await page.route("**/api/v1/jobs*", (route) =>
    route.fulfill({
      status: 500,
      json: {
        detail: {
          code: "db_down",
          message: "database exploded",
          stderr: "trace line"
        }
      }
    })
  );
  await page.goto("/#jobs");
  await page.getByTestId("jobs-refresh").click();
  await page.getByTitle("Notification center (N)").click();
  const center = page.getByTestId("notification-center");
  await expect(center).toContainText("database exploded");
  await expect(center).toContainText("db_down");
  await expect(center).toContainText("trace line");
});

test("shows a provider validation error inline instead of silently failing", async ({
  page
}) => {
  await mockProviders(page);
  await page.goto("/#providers");
  await page.getByLabel("Secret env").fill("sk-literal-key");
  await page.getByRole("button", { name: "Test connection" }).click();
  await expect(
    page.getByText("Secret env must be a variable name like DEEPSEEK_API_KEY, not the API key.")
  ).toBeVisible();
});

test("explains a provider rejection and keeps the raw response in details", async ({
  page
}) => {
  await mockProviders(page);
  await page.route("**/api/v1/providers/test", (route) =>
    route.fulfill({
      json: {
        ok: false,
        status_code: 401,
        code: "auth_failed",
        message: "The provider rejected the API key (HTTP 401).",
        hint: "Check that the key is valid, not expired, and belongs to this provider.",
        provider_message: "Authentication Fails (governor)",
        secret_present: true,
        secret_source: "request",
        latency_ms: 365,
        mode: "chat",
        endpoint: "https://api.deepseek.com/v1/chat/completions"
      }
    })
  );
  await page.goto("/#providers");
  await page.getByLabel("Secret env").fill("DEEPSEEK_API_KEY");
  await page.getByLabel("Model", { exact: true }).fill("deepseek-chat");
  await page.getByLabel("Secret value").fill("sk-test");
  await page.getByRole("button", { name: "Test connection" }).click();
  await expect(
    page.getByText("The provider rejected the API key (HTTP 401).")
  ).toBeVisible();
  await expect(page.getByText("Check that the key is valid", { exact: false })).toBeVisible();
  await expect(page.getByText("API key: from this form (not saved)")).toBeVisible();
  await page.getByText("Provider response").click();
  await expect(page.getByText("Authentication Fails (governor)")).toBeVisible();
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

test("cycles the theme from the header", async ({ page }) => {
  await page.getByRole("button", { name: "Theme" }).click();
  await expect
    .poll(() =>
      page.evaluate(() => getComputedStyle(document.body).backgroundColor)
    )
    .toBe("rgb(248, 250, 252)");
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

test("force stops a running job from the activity drawer", async ({ page }) => {
  await page.getByRole("button", { name: /Activity/ }).click();
  const drawer = page.getByTestId("activity-drawer");
  const running = drawer.locator("li").filter({ hasText: "Rendering timeline" });
  const request = page.waitForRequest(
    (item) =>
      item.method() === "DELETE" &&
      item.url().includes("11111111-1111-1111-1111-111111111111")
  );
  await running.getByRole("button", { name: "Force stop" }).click();
  expect((await request).url()).toContain("force=true");
});

test("renders activity above the workspace navigation", async ({ page }) => {
  await page.getByRole("button", { name: /Activity/ }).click();
  await expect(page.getByTestId("activity-drawer")).toBeVisible();
  const inside = await page.evaluate(() => {
    const point = document.elementFromPoint(window.innerWidth - 20, 20);
    return Boolean(point?.closest('[data-testid="activity-drawer"]'));
  });
  expect(inside).toBe(true);
});

test("stops every active job from the activity drawer", async ({ page }) => {
  await page.getByRole("button", { name: /Activity/ }).click();
  const request = page.waitForRequest(
    (item) =>
      item.method() === "POST" && item.url().includes("/api/v1/jobs/cancel_all")
  );
  await page.getByTestId("activity-drawer").getByRole("button", { name: "Stop all" }).click();
  expect((await request).url()).toContain("force=true");
});

test("filters the activity drawer", async ({ page }) => {
  await page.getByRole("button", { name: /Activity/ }).click();
  const drawer = page.getByTestId("activity-drawer");
  await expect(drawer).toBeVisible();
  await drawer.getByLabel("Search activity").fill("interview");
  await expect(drawer.getByText("interview.mp4")).toBeVisible();
  await drawer.getByLabel("Search activity").fill("no-such-job");
  await expect(drawer.getByText("No activity matches this search.")).toBeVisible();
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

  await page.getByRole("button", { name: "Clear all" }).click();
  await expect(page.getByTestId("job-list").locator("li")).toHaveCount(4);
});

test("focuses the jobs search with slash and clears with escape", async ({ page }) => {
  await page.keyboard.press("/");
  await expect(page.getByRole("tab", { name: "Jobs" })).toHaveAttribute(
    "aria-selected",
    "true"
  );
  await expect(page.getByLabel("Search jobs")).toBeFocused();
  await page.keyboard.type("webinar");
  await expect(page.getByTestId("job-list").locator("li")).toHaveCount(1);
  await page.keyboard.press("Escape");
  await expect(page.getByLabel("Search jobs")).toHaveValue("");
});

test("shows recent commands in the palette", async ({ page }) => {
  await page.keyboard.press("Control+k");
  const input = page.getByRole("textbox", { name: "Search commands" });
  await input.fill("timeline");
  await page.keyboard.press("Enter");
  await expect(page.getByTestId("command-palette")).toHaveCount(0);
  await page.keyboard.press("Control+k");
  await expect(input).toHaveValue("");
  await expect(page.getByTestId("command-palette")).toContainText("Recent");
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

test("shows intelligence provider settings", async ({ page }) => {
  await page.route("**/api/v1/settings", (route) =>
    route.fulfill({
      json: {
        settings: {
          schema_version: 1,
          runtime: { host: "127.0.0.1", port: 8765, open_browser: true, log_level: "info", max_jobs: 2, history: 50, locale: "en" },
          paths: { allowed_roots: [], ffmpeg: "", ffprobe: "", cache_dir: "", models_dir: "", output_root: "", temp_dir: "" },
          models: { defaults: {}, device: "cpu", compute_type: "int8", threads: 0, hf_token_env: "HF_TOKEN" },
          automation: { scheduler_interval_seconds: 20, max_retries: 5, retry_backoff_seconds: 30, enabled: true },
          quality: { target_lufs: -16, true_peak_db: -1, vmaf_threshold: 90, proxy_height: 540 },
          ui: { theme: "dark", density: "comfortable", timeline_snap: true },
          llm: { temperature: 0, timeout_seconds: 90, max_tokens: 0, retries: 2, json_mode: true },
          speech: { engine: "auto", language: "pt", device: "cpu", compute_type: "int8", vad_filter: false, diarization_model: "pyannote" },
          tts: { provider: "openai_compatible", voice: "alloy", model: "tts-1", format: "mp3", speed: 1 },
          stock: { provider: "local", pexels_key_env: "PEXELS_API_KEY", pixabay_key_env: "PIXABAY_API_KEY", openverse_token_env: "OPENVERSE_TOKEN", asset_dir: "", youtube_fair_use_seconds: 15, youtube_max_per_video: 3, allow_fair_use: true },
          translation: { target_language: "en", source_language: "auto" },
          notifications: { enabled: true, default_channels: ["local"], base_url: "http://127.0.0.1:8765", email: {}, slack: {}, signal: {}, local: {} },
          search: { enabled: true, providers: ["local"], local_paths: [], seed_urls: [], searxng_url: "", wikipedia_language: "pt", max_results: 6, fetch_pages: 3, allow_network: false, timeout_seconds: 20, max_bytes: 2000000, cache_ttl_hours: 24 },
          intelligence: { enabled: true, provider_order: ["opencode_v2", "deepseek"], allow_network: false, budget_usd: 0, cache_enabled: true, default_timeout_seconds: 120, opencode_base_url: "", opencode_token_env: "OPENCODE_TOKEN", opencode_model: "", deepseek_base_url: "https://api.deepseek.com", deepseek_model: "deepseek-chat", deepseek_api_key_env: "DEEPSEEK_API_KEY", tasks: {} }
        },
        env: {},
        restart_required: []
      }
    })
  );
  await page.route("**/api/v1/intelligence/status", (route) =>
    route.fulfill({
      json: { ok: true, enabled: true, order: ["opencode_v2"], providers: [], telemetry: { calls: 0, estimated_cost_usd: 0 } }
    })
  );
  await page.goto("/#settings");
  await expect(page.getByRole("heading", { name: "Intelligence" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Test providers" })).toBeVisible();
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

test("opens the guide from the header and remembers dismissal", async ({ page }) => {
  const card = page.getByTestId("onboarding-card");
  const guide = page.getByRole("button", { name: "Guide" });
  const hydrated = async () => {
    await expect(page.getByTitle("Server version")).not.toContainText("connecting");
  };
  const openGuide = async () => {
    await expect(async () => {
      await guide.click();
      await expect(card).toBeVisible({ timeout: 1000 });
    }).toPass();
  };

  await hydrated();
  await expect(card).toHaveCount(0);
  await openGuide();
  await card.getByRole("button", { name: "Dismiss" }).click();
  await expect(card).toHaveCount(0);

  await page.reload();
  await hydrated();
  await expect(card).toHaveCount(0);
  await openGuide();
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

test("keeps five areas translated in pt-BR", async ({ page }) => {
  await page.route("**/api/v1/settings", (route) =>
    route.fulfill({
      json: { settings: { runtime: { locale: "pt-BR" }, ui: {} } }
    })
  );
  await page.reload();
  await expect(page.getByRole("tab", { name: "Produzir" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Construtor de receitas" })).toBeVisible();

  await page.getByRole("tab", { name: "Editar" }).click();
  await expect(page.getByRole("heading", { name: "Timeline" })).toBeVisible();

  await page.getByRole("tab", { name: "Execuções" }).click();
  await expect(page.getByRole("heading", { name: "Execuções" })).toBeVisible();

  await page.getByRole("tab", { name: "Biblioteca" }).click();
  await page.getByRole("tab", { name: "Biblioteca da marca" }).click();
  await expect(page.getByRole("heading", { name: "Biblioteca da marca" })).toBeVisible();

  await page.getByRole("tab", { name: "Configurar" }).click();
  await page.getByRole("tab", { name: "Configurações" }).click();
  await expect(page.getByRole("heading", { name: "Configurações locais" })).toBeVisible();
});

test("assistant shows a diff and applies only after approval", async ({ page }) => {
  await page.route("**/api/v1/jobs/*/assistant**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith("/assistant/history")) {
      return route.fulfill({ json: { ok: true, history: [] } });
    }
    if (url.pathname.endsWith("/assistant/approve")) {
      return route.fulfill({ json: { ok: true, results: [{ applied: true }] } });
    }
    return route.fulfill({
      json: {
        ok: true,
        message: "I will shorten the first clip.",
        actions: [
          {
            id: "a1",
            tool: "apply_timeline_edits",
            arguments: { edits: [{ clip_id: "v1", action: "trim", end_sec: 1 }] }
          }
        ],
        observations: [],
        diff: [{ clip_id: "v1", change: "modified" }],
        requires_approval: true,
        approval_id: "approval-demo",
        tokens: 120,
        cost_usd: 0.001,
        budget_usd: 0,
        remaining_usd: null
      }
    });
  });
  await page.goto("/#copilot");
  await page.getByRole("button", { name: "Agent tools" }).click();
  await page.getByRole("textbox", { name: "Instruction" }).fill("shorten it");
  await page.getByRole("button", { name: "Ask the agent" }).click();
  await expect(page.getByTestId("assistant-diff")).toContainText("v1");
  await page.getByRole("button", { name: "Approve and apply" }).click();
  await expect(page.getByText(/Approved and applied/)).toBeVisible();
});

test("keeps the recipe builder help tooltip inside the viewport", async ({ page }) => {
  await page.goto("/#recipes");
  const help = page.getByRole("button", { name: "Help: Produce" }).first();
  await help.focus();
  const tooltip = page.getByTestId("help-tooltip");
  await expect(tooltip).toBeVisible();
  const box = await tooltip.boundingBox();
  const viewport = page.viewportSize();
  expect(box).not.toBeNull();
  expect(viewport).not.toBeNull();
  if (box && viewport) {
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.y).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(viewport.width);
    expect(box.y + box.height).toBeLessThanOrEqual(viewport.height);
    const onTop = await page.evaluate(
      ({ x, y }) => {
        const node = document.elementFromPoint(x, y);
        return node?.closest('[data-testid="help-tooltip"]') !== null;
      },
      { x: box.x + box.width / 2, y: box.y + box.height / 2 }
    );
    expect(onTop).toBe(true);
  }
});


test("shows the same server and UI version", async ({ page }) => {
  await expect(page.getByTitle("Server version")).toContainText(pyprojectVersion);
  await expect(page.getByTitle("UI bundle version")).toContainText(pyprojectVersion);
  await expect(page.getByText(/are different/)).toHaveCount(0);
});

test("organizes recipes with favorites and recent filters", async ({ page }) => {
  await page.goto("/#recipes");
  await page.getByTestId("recipe-library").click();
  await expect(page.getByRole("tab", { name: /Favorites/ })).toBeVisible();
  await expect(page.getByRole("tab", { name: "Recent" })).toBeVisible();
  await expect(page.getByRole("tab", { name: "All recipes" })).toBeVisible();
  await expect(
    page.getByRole("button", { name: /^Recut Replacement Silence/ })
  ).toBeVisible();
  await page.getByRole("tab", { name: "All recipes" }).click();
  await expect(
    page.getByRole("button", { name: /Example recipe E2E recipe/ })
  ).toBeVisible();
  await page.getByRole("button", { name: /Add Example recipe to favorites/ }).click();
  await expect(page.getByText(/added to favorites/)).toBeVisible();
});
