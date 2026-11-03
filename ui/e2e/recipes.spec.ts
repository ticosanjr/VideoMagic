import { expect, test, type Page } from "@playwright/test";
import { readFileSync } from "node:fs";

const fixture = (name: string) =>
  JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf8"));

async function openMore(page: Page) {
  await page.getByTestId("recipe-more").click();
  await expect(page.getByTestId("recipe-more-menu")).toBeVisible();
}

async function mockApi(page: Page) {
  await page.route("**/api/v1/**", async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    if (path === "/api/v1/system") return route.fulfill({ json: fixture("system.json") });
    if (path === "/api/v1/jobs") return route.fulfill({ json: fixture("jobs.json") });
    if (path === "/api/v1/steps") return route.fulfill({ json: fixture("steps.json") });
    if (path === "/api/v1/recipes") return route.fulfill({ json: fixture("recipes.json") });
    if (path === "/api/v1/recipes/example_recipe") return route.fulfill({ json: fixture("recipe.json") });
    if (path === "/api/v1/recipes/example_recipe/history") {
      return route.fulfill({
        json: {
          ok: true,
          history: [
            { version: "123", name: "Old recipe", description: "", step_count: 1 }
          ]
        }
      });
    }
    if (path === "/api/v1/recipes/example_recipe/history/123") {
      const recipe = structuredClone(fixture("recipe.json"));
      recipe.recipe.name = "Old recipe";
      recipe.recipe.steps = [recipe.recipe.steps[0]];
      return route.fulfill({ json: { ok: true, recipe: recipe.recipe } });
    }
    if (path === "/api/v1/node-presets") {
      return route.fulfill({
        json: {
          ok: true,
          presets: [
            {
              id: "builtin:audio.vad:gentle",
              step_type: "audio.vad",
              name: "Gentle",
              params: { min_silence_ms: 550 },
              favorite: false,
              builtin: true,
              created_at: ""
            },
            {
              id: "builtin:audio.vad:aggressive",
              step_type: "audio.vad",
              name: "Aggressive",
              params: { min_silence_ms: 240 },
              favorite: true,
              builtin: true,
              created_at: ""
            },
            {
              id: "builtin:edit.timeline:j-cut",
              step_type: "edit.timeline",
              name: "J-cut",
              params: { cut_mode: "j_cut" },
              favorite: false,
              builtin: true,
              created_at: ""
            }
          ]
        }
      });
    }
    if (path === "/api/v1/node-options") {
      return route.fulfill({
        json: { ok: true, providers: { asr: [], tts: [] }, services: [], models: [] }
      });
    }
    if (path === "/api/v1/runs") return route.fulfill({ json: fixture("runs.json") });
    if (path === "/api/v1/exports/validate") return route.fulfill({ json: fixture("nle.json") });
    if (path === "/api/v1/batches") return route.fulfill({ json: fixture("batches.json") });
    if (path === "/api/v1/assets") return route.fulfill({ json: fixture("assets.json") });
    if (path === "/api/v1/schedules") return route.fulfill({ json: { ok: true, schedules: [] } });
    return route.fulfill({ json: { ok: true } });
  });
}

test.beforeEach(async ({ page }) => {
  await mockApi(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Recipe builder" })).toBeVisible();
  await expect(page.getByTestId("step-edit.timeline")).toBeVisible({ timeout: 10000 });
});

test("loads saved node layout and inline fields", async ({ page }) => {
  await expect(page.getByTestId("field-transition_frames")).toBeVisible();
  await expect(page.getByTestId("step-pin-edit.timeline")).toBeVisible();
});

test("inspects a node output from the latest run", async ({ page }) => {
  const job = {
    job_id: "job-1",
    status: "succeeded",
    progress: 100,
    stage: "done",
    message: "Finished",
    source: "/tmp/source.mp4",
    output: "/tmp/out",
    options: {},
    created_at: "2026-11-03T10:00:00Z",
    result: {
      ok: true,
      step_runs: [{ id: "retakes", type: "retakes.cull", status: "executed" }]
    }
  };
  await page.route("**/api/v1/jobs?**", (route) =>
    route.fulfill({ json: { ok: true, jobs: [job] } })
  );
  await page.route("**/api/v1/jobs/job-1/steps/retakes/outputs", (route) =>
    route.fulfill({
      json: {
        ok: true,
        step_id: "retakes",
        type: "retakes.cull",
        status: "executed",
        fingerprint: "fp",
        elapsed_ms: 4,
        ports: [
          {
            id: "discarded",
            label: "Discarded",
            type: "integer_list",
            hash: "h",
            size_bytes: 12,
            has_value: true
          }
        ],
        files: [],
        artifacts: []
      }
    })
  );
  await page.route("**/api/v1/jobs/job-1/steps/retakes/outputs/discarded", (route) =>
    route.fulfill({
      json: {
        ok: true,
        step_id: "retakes",
        port: { id: "discarded", label: "Discarded", type: "integer_list", value: [3, 7] }
      }
    })
  );
  await page.reload();
  await expect(page.getByRole("heading", { name: "Recipe builder" })).toBeVisible();
  await expect(async () => {
    await page.getByTestId("recipe-step-outputs").click();
    await expect(page.getByRole("dialog", { name: "Step outputs" })).toBeVisible({
      timeout: 1000
    });
  }).toPass();
  await expect(page.getByTestId("step-output-json")).toContainText("7");
});

test("edits a field directly inside the node", async ({ page }) => {
  await page.getByTestId("step-ingest").click();
  await expect(page.getByTestId("field-extract_pcm")).toBeVisible();
  await page.getByTestId("field-extract_pcm").uncheck();
  await expect(page.getByTestId("step-params-json")).toHaveValue(/"extract_pcm": false/);
});

test("edits an array field as JSON", async ({ page }) => {
  await page.getByTestId("step-ingest").click();
  const field = page.getByTestId("field-notes");
  await expect(field).toBeVisible();
  await field.fill('["one", "two"]');
  await expect(page.getByTestId("step-params-json")).toHaveValue(/"notes": \[/);
});

test("undoes a structural edit", async ({ page }) => {
  await page.getByTestId("recipe-add-step").click();
  await page.getByTestId("add-shorts.render").click();
  await expect(page.getByTestId("step-shorts.render")).toBeVisible();
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByTestId("step-shorts.render")).toHaveCount(0);
});

test("loads the recipe graph and edits transition parameters", async ({ page }) => {
  await expect(page.getByRole("heading", { name: "Recipe builder" })).toBeVisible();
  await expect(page.getByTestId("step-edit.timeline")).toBeVisible();
  await page
    .getByTestId("step-edit.timeline")
    .getByText("Build timeline")
    .click();
  await expect(page.getByTestId("inspector-field-transition_frames")).toBeVisible();
  await page.getByTestId("inspector-field-transition_frames").fill("12");
  await page.getByTestId("inspector-field-transition_type").selectOption("fade_to_black");
  const json = await page.getByTestId("step-params-json").inputValue();
  expect(json).toContain('"transition_frames": 12');
  expect(json).toContain('"transition_type": "fade_to_black"');
});

test("adds a step from the JSON-backed palette", async ({ page }) => {
  await page.getByTestId("recipe-add-step").click();
  await expect(page.getByTestId("add-shorts.render")).toBeVisible();
  await page.getByTestId("add-shorts.render").click();
  await expect(page.getByTestId("step-shorts.render")).toBeVisible();
});

test("exposes the second split-screen source control", async ({ page }) => {
  await page.getByTestId("recipe-add-step").click();
  await page.getByTestId("add-shorts.render").click();
  await expect(page.getByTestId("inspector-field-second_source_path")).toBeVisible();
  await expect(page.getByTestId("inspector-field-second_source_path")).toHaveAttribute(
    "placeholder",
    "/path/to/second-angle.mp4"
  );
});

test("edits a schema-derived field", async ({ page }) => {
  await page.getByTestId("step-ingest").click();
  await expect(page.getByTestId("inspector-field-extract_pcm")).toBeVisible();
  await page.getByTestId("inspector-field-extract_pcm").uncheck();
  const json = await page.getByTestId("step-params-json").inputValue();
  expect(json).toContain('"extract_pcm": false');
});

test("shows field help, resizes the inspector, and dims non-matching nodes", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("videoflow.inspectorWidth", "560"));
  await page.reload();
  await page.getByTestId("step-audio.vad").getByText("Voice detection").click();
  const help = page
    .getByTestId("inspector-config")
    .getByRole("button", { name: "Help: Minimum silence" });
  await help.hover();
  await expect(
    page.getByText("Minimum silence before the timeline starts a new cut.").first()
  ).toBeVisible();

  const search = page.getByLabel("Find node");
  await search.fill("timeline");
  await expect(page.getByTestId("step-audio.vad")).toHaveClass(/opacity-25/);
  await expect(page.getByTestId("step-edit.timeline")).not.toHaveClass(/opacity-25/);
});

test("compares a recipe version with the current graph", async ({ page }) => {
  await openMore(page);
  await page.getByRole("menuitem", { name: /Version history/ }).click();
  await expect(page.getByRole("dialog", { name: "Recipe history" })).toBeVisible();
  await page.getByRole("button", { name: "Compare" }).click();
  await expect(page.getByRole("dialog", { name: "Version comparison" })).toBeVisible();
  await expect(page.getByText(/Name: "Old recipe"/)).toBeVisible();
  await expect(page.getByText(/Added step:/).first()).toBeVisible();
});

test("shows full parity fields, outputs, and presets in the inspector", async ({ page }) => {
  await page.getByTestId("step-audio.vad").getByText("Voice detection").click();
  const slider = page.getByTestId("inspector-field-min_silence_ms");
  await expect(slider).toHaveJSProperty("type", "range");
  await expect(page.getByTestId("inspector-presets-audio.vad")).toContainText("Aggressive");
  await page
    .getByTestId("inspector-presets-audio.vad")
    .getByRole("button", { name: "Aggressive", exact: true })
    .click();
  await expect(page.getByTestId("step-params-json")).toHaveValue(/"min_silence_ms": 240/);

  await page.getByLabel("Close inspector").click();
  await page.getByTestId("step-edit.timeline").getByText("Build timeline").click();
  await expect(page.getByTestId("inspector-outputs-edit.timeline")).toContainText(
    "Timeline state"
  );
  await expect(page.getByTestId("inspector-field-transition_frames")).toBeVisible();
});

test("autosaves inspector edits", async ({ page }) => {
  const saves: string[] = [];
  page.on("request", (request) => {
    if (request.method() === "PUT" && request.url().includes("/api/v1/recipes/")) {
      saves.push(request.url());
    }
  });
  await page.getByTestId("step-audio.vad").getByText("Voice detection").click();
  await page.getByTestId("inspector-field-min_silence_ms").evaluate((element) => {
    const input = element as HTMLInputElement;
    input.value = "550";
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await expect.poll(() => saves.length).toBeGreaterThan(0);
});

test("confirms inspector removal and can undo it", async ({ page }) => {
  await page.getByTestId("step-audio.vad").getByText("Voice detection").click();
  const remove = page.getByTestId("inspector-remove");
  await remove.click();
  await expect(remove).toHaveText("Confirm remove");
  await remove.click();
  await expect(page.getByTestId("step-audio.vad")).toHaveCount(0);
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByTestId("step-audio.vad")).toBeVisible();
});

test("undoes an inspector field edit", async ({ page }) => {
  await page.getByTestId("step-audio.vad").getByText("Voice detection").click();
  await page.getByTestId("inspector-field-min_silence_ms").evaluate((element) => {
    const input = element as HTMLInputElement;
    input.value = "550";
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await expect(page.getByTestId("step-params-json")).toHaveValue(/"min_silence_ms": 550/);
  await page.getByRole("button", { name: "Undo" }).click();
  await expect(page.getByTestId("step-params-json")).toHaveValue(/"min_silence_ms": 350/);
});

test("blocks Run on inline validation errors", async ({ page }) => {
  await page.getByTestId("step-audio.vad").getByText("Voice detection").click();
  await page
    .getByTestId("step-params-json")
    .fill('{"min_silence_ms": -1, "engine": "auto"}');
  await expect(page.getByTestId("step-audio.vad")).toContainText("⚠ 1");
  await page.getByTestId("recipe-run").click();
  await expect(page.getByText(/Fix 1 field error/)).toBeVisible();
});

test("validates NLE exports from the UI", async ({ page }) => {
  await openMore(page);
  await page.getByTestId("nle-validate").click();
  await page.getByTestId("workspace-output").fill("/tmp/out");
  await page.getByTestId("workspace-continue").click();
  await expect(page.getByTestId("nle-report")).toBeVisible();
  await expect(page.getByText("NLE export validation")).toBeVisible();
  await expect(page.getByText("affine_filters: 2")).toBeVisible();
});

test("opens persisted batch history", async ({ page }) => {
  await openMore(page);
  await page.getByRole("menuitem", { name: /Batch history/ }).click();
  await expect(page.getByText("Persisted batches")).toBeVisible();
  await expect(page.getByText(/11111111/)).toBeVisible();
});

test("cycles node width from the node header", async ({ page }) => {
  await page.getByTestId("step-ingest").click();
  const node = page.getByTestId("step-ingest");
  const before = await node.boundingBox();
  await page.getByTestId("step-width-ingest").click();
  const after = await node.boundingBox();
  expect(after?.width).not.toBe(before?.width);
});

test("disables and re-enables a node from its header", async ({ page }) => {
  const node = page.getByTestId("step-edit.timeline");
  await page.getByTestId("step-enabled-edit.timeline").click();
  await expect(node).toContainText("disabled");
  await page.getByTestId("step-enabled-edit.timeline").click();
  await expect(node).not.toContainText("disabled");
});

test("opens the recipe template gallery", async ({ page }) => {
  await page.getByTestId("recipe-library").click();
  const dialog = page.getByRole("dialog", { name: "Recipe library" });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText("Example recipe")).toBeVisible();
});

test("opens the media library tab", async ({ page }) => {
  await page.getByRole("tab", { name: "Library" }).click();
  await page.getByRole("tab", { name: "Media" }).click();
  await expect(page.getByRole("heading", { name: "Media" })).toBeVisible();
  await expect(page.getByText("No assets yet")).toBeVisible();
});

test("opens the schedules tab", async ({ page }) => {
  await page.getByRole("tab", { name: "Runs" }).click();
  await page.getByRole("tab", { name: "Schedules" }).click();
  await expect(page.getByRole("heading", { name: "Schedules" })).toBeVisible();
  await expect(page.getByText("No schedules yet.")).toBeVisible();
});

test("opens the timeline tab", async ({ page }) => {
  await page.getByRole("tab", { name: "Edit" }).click();
  await expect(page.getByRole("heading", { name: "Timeline" })).toBeVisible();
  await expect(page.getByText("Run a recipe to populate the timeline.")).toBeVisible();
});

test("opens persisted run history and shows failures", async ({ page }) => {
  await page.getByTestId("recipe-runs").click();
  await page.getByTestId("workspace-output").fill("/tmp/out");
  await page.getByTestId("workspace-continue").click();
  await expect(page.getByTestId("run-history")).toBeVisible();
  await expect(page.getByText("failed")).toBeVisible();
  await expect(page.getByText("succeeded")).toBeVisible();
  await expect(page.getByText("ingest_failed")).toHaveCount(0);
});

async function navIsCovered(page: Page) {
  const nav = page.getByRole("navigation", { name: "Workspace areas" });
  const box = await nav.boundingBox();
  if (!box) return false;
  return page.evaluate(
    ({ x, y }) => {
      const node = document.elementFromPoint(x, y);
      return node !== null && node.closest('[role="dialog"], [role="presentation"]') !== null;
    },
    { x: box.x + 24, y: box.y + 20 }
  );
}

test("keeps the JSON editor above the area navigation", async ({ page }) => {
  await page.getByTestId("recipe-json").click();
  await expect(page.getByRole("dialog", { name: "JSON editor" })).toBeVisible();
  expect(await navIsCovered(page)).toBe(true);
});

test("keeps the wire dialog above the area navigation", async ({ page }) => {
  await page.getByTestId("step-edit.timeline").getByText("Build timeline").click();
  await page.getByRole("button", { name: "Wiring" }).click();
  await expect(page.getByRole("dialog", { name: "Wire ports" })).toBeVisible();
  expect(await navIsCovered(page)).toBe(true);
});

test("shows every wire port and disables incompatible ones", async ({ page }) => {
  await page.getByTestId("step-edit.timeline").getByText("Build timeline").click();
  await page.getByRole("button", { name: "Wiring" }).click();
  const dialog = page.getByRole("dialog", { name: "Wire ports" });
  await expect(dialog).toBeVisible();
  await expect(page.getByTestId("wire-output-speech")).toBeVisible();
  await expect(page.getByTestId("wire-input-speech")).toBeVisible();

  await page.getByText(/Incompatible outputs/).click();
  await expect(page.getByTestId("wire-output-incompatible-engine")).toBeDisabled();
  await page.getByText(/Incompatible inputs/).click();
  await expect(page.getByTestId("wire-input-incompatible-transcript")).toBeDisabled();
});

test("shows typed ports and the wired edge label", async ({ page }) => {
  await expect(page.getByText("speech → speech")).toBeVisible();
  await page
    .getByTestId("step-edit.timeline")
    .getByText("Build timeline")
    .click();
  await expect(page.getByTestId("inputs-edit.timeline")).toContainText("Speech spans");
  await expect(page.getByTestId("outputs-edit.timeline")).toContainText("Timeline state");
});

test("uses sliders, presets, and cut-mode controls inside the node", async ({ page }) => {
  await page
    .getByTestId("step-audio.vad")
    .getByText("Voice detection")
    .click();
  const slider = page.getByTestId("field-min_silence_ms");
  await expect(slider).toHaveJSProperty("type", "range");
  await page
    .getByTestId("step-audio.vad")
    .getByRole("button", { name: "Aggressive" })
    .first()
    .click();
  const params = await page.getByTestId("step-params-json").inputValue();
  expect(params).toContain('"min_silence_ms": 240');
  await page.getByLabel("Close inspector").click();
  await page
    .getByTestId("step-edit.timeline")
    .getByText("Build timeline")
    .click();
  await page.getByLabel("Close inspector").click();
  await page
    .getByTestId("step-edit.timeline")
    .getByRole("button", { name: "J-cut", exact: true })
    .click();
  await page
    .getByTestId("step-edit.timeline")
    .getByText("Build timeline")
    .click();
  const timeline = await page.getByTestId("step-params-json").inputValue();
  expect(timeline).toContain('"cut_mode": "j_cut"');
});

test("rewires an input from the inspector without dragging", async ({ page }) => {
  await page
    .getByTestId("step-edit.timeline")
    .getByText("Build timeline")
    .click();
  const input = page.getByTestId("inspector-inputs").locator("select").first();
  await expect(input).toHaveValue("vad.speech");
  await input.selectOption("");
  await expect(page.getByText("speech → speech")).toHaveCount(0);
  await input.selectOption("vad.speech");
  await expect(page.getByText("speech → speech")).toBeVisible();
});

test("chooses media and a file output folder inside nodes", async ({ page }) => {
  await page.getByTestId("step-ingest").getByText("Ingest media").click();
  const media = page
    .getByTestId("step-ingest")
    .getByPlaceholder("/media/source.mp4");
  await media.fill("/tmp/source.mp4");
  await page.getByTestId("recipe-json").click();
  const recipe = await page.getByTestId("recipe-json-text").inputValue();
  expect(recipe).toContain('"source": "/tmp/source.mp4"');
  await page.getByLabel("Close JSON editor").click();

  await page.getByTestId("recipe-add-step").click();
  await page.getByTestId("add-export.nle").click();
  await page.getByLabel("Close inspector").click();
  const output = page.getByTestId("step-export.nle");
  await output.getByTestId("output-mode").selectOption("folder");
  await expect(output.getByTestId("output-mode")).toHaveValue("folder");
  await output.getByTestId("output-dir").fill("/tmp/final-cut");
  await page.getByTestId("recipe-json").click();
  const full = await page.getByTestId("recipe-json-text").inputValue();
  expect(full).toContain('"output_mode": "folder"');
  expect(full).toContain('"output_dir": "/tmp/final-cut"');
});
