# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: recipes.spec.ts >> opens the asset library tab
- Location: e2e/recipes.spec.ts:116:1

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByTestId('step-edit.timeline')
Expected: visible
Timeout: 5000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" getByTestId('step-edit.timeline') with timeout 5000ms
  - waiting for getByTestId('step-edit.timeline')

```

```yaml
- heading "500" [level=1]
- paragraph: Internal Error
```

# Test source

```ts
  1   | import { expect, test, type Page } from "@playwright/test";
  2   | import { readFileSync } from "node:fs";
  3   | 
  4   | const fixture = (name: string) =>
  5   |   JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url), "utf8"));
  6   | 
  7   | async function mockApi(page: Page) {
  8   |   await page.route("**/api/v1/**", async (route) => {
  9   |     const url = new URL(route.request().url());
  10  |     const path = url.pathname;
  11  |     if (path === "/api/v1/system") return route.fulfill({ json: fixture("system.json") });
  12  |     if (path === "/api/v1/jobs") return route.fulfill({ json: fixture("jobs.json") });
  13  |     if (path === "/api/v1/steps") return route.fulfill({ json: fixture("steps.json") });
  14  |     if (path === "/api/v1/recipes") return route.fulfill({ json: fixture("recipes.json") });
  15  |     if (path === "/api/v1/recipes/example_recipe") return route.fulfill({ json: fixture("recipe.json") });
  16  |     if (path === "/api/v1/runs") return route.fulfill({ json: fixture("runs.json") });
  17  |     if (path === "/api/v1/exports/validate") return route.fulfill({ json: fixture("nle.json") });
  18  |     if (path === "/api/v1/batches") return route.fulfill({ json: fixture("batches.json") });
  19  |     if (path === "/api/v1/assets") return route.fulfill({ json: fixture("assets.json") });
  20  |     return route.fulfill({ json: { ok: true } });
  21  |   });
  22  | }
  23  | 
  24  | test.beforeEach(async ({ page }) => {
  25  |   await mockApi(page);
  26  |   await page.goto("/");
  27  |   await expect(page.getByRole("heading", { name: "Recipe builder" })).toBeVisible();
> 28  |   await expect(page.getByTestId("step-edit.timeline")).toBeVisible();
      |                                                        ^ Error: expect(locator).toBeVisible() failed
  29  | });
  30  | 
  31  | test("loads saved node layout and inline fields", async ({ page }) => {
  32  |   await expect(page.getByTestId("field-transition_frames")).toBeVisible();
  33  |   await expect(page.getByTestId("step-pin-edit.timeline")).toBeVisible();
  34  | });
  35  | 
  36  | test("edits a field directly inside the node", async ({ page }) => {
  37  |   await page.getByTestId("step-ingest").click();
  38  |   await expect(page.getByTestId("field-extract_pcm")).toBeVisible();
  39  |   await page.getByTestId("field-extract_pcm").uncheck();
  40  |   await expect(page.getByTestId("step-params-json")).toHaveValue(/"extract_pcm": false/);
  41  | });
  42  | 
  43  | test("edits an array field as JSON", async ({ page }) => {
  44  |   await page.getByTestId("step-ingest").click();
  45  |   const field = page.getByTestId("field-notes");
  46  |   await expect(field).toBeVisible();
  47  |   await field.fill('["one", "two"]');
  48  |   await expect(page.getByTestId("step-params-json")).toHaveValue(/"notes": \[/);
  49  | });
  50  | 
  51  | test("undoes a structural edit", async ({ page }) => {
  52  |   await page.getByTestId("recipe-add-step").click();
  53  |   await page.getByTestId("add-shorts.render").click();
  54  |   await expect(page.getByTestId("step-shorts.render")).toBeVisible();
  55  |   await page.getByRole("button", { name: "Undo" }).click();
  56  |   await expect(page.getByTestId("step-shorts.render")).toHaveCount(0);
  57  | });
  58  | 
  59  | test("loads the recipe graph and edits transition parameters", async ({ page }) => {
  60  |   await expect(page.getByRole("heading", { name: "Recipe builder" })).toBeVisible();
  61  |   await expect(page.getByTestId("step-edit.timeline")).toBeVisible();
  62  |   await page.getByTestId("step-edit.timeline").click();
  63  |   await expect(page.getByTestId("transition-frames")).toBeVisible();
  64  |   await page.getByTestId("transition-frames").fill("12");
  65  |   await page.getByTestId("transition-type").selectOption("fade_to_black");
  66  |   const json = await page.getByTestId("step-params-json").inputValue();
  67  |   expect(json).toContain('"transition_frames": 12');
  68  |   expect(json).toContain('"transition_type": "fade_to_black"');
  69  | });
  70  | 
  71  | test("adds a step from the JSON-backed palette", async ({ page }) => {
  72  |   await page.getByTestId("recipe-add-step").click();
  73  |   await expect(page.getByTestId("add-shorts.render")).toBeVisible();
  74  |   await page.getByTestId("add-shorts.render").click();
  75  |   await expect(page.getByTestId("step-shorts.render")).toBeVisible();
  76  | });
  77  | 
  78  | test("exposes the second split-screen source control", async ({ page }) => {
  79  |   await page.getByTestId("recipe-add-step").click();
  80  |   await page.getByTestId("add-shorts.render").click();
  81  |   await page.getByTestId("step-shorts.render").click();
  82  |   await expect(page.getByPlaceholder("/path/to/second-angle.mp4")).toBeVisible();
  83  | });
  84  | 
  85  | test("edits a schema-derived field", async ({ page }) => {
  86  |   await page.getByTestId("step-ingest").click();
  87  |   await expect(page.getByTestId("schema-extract_pcm")).toBeVisible();
  88  |   await page.getByTestId("schema-extract_pcm").uncheck();
  89  |   const json = await page.getByTestId("step-params-json").inputValue();
  90  |   expect(json).toContain('"extract_pcm": false');
  91  | });
  92  | 
  93  | test("validates NLE exports from the UI", async ({ page }) => {
  94  |   await page.getByPlaceholder("/media/output").fill("/tmp/out");
  95  |   await page.getByTestId("nle-validate").click();
  96  |   await expect(page.getByTestId("nle-report")).toBeVisible();
  97  |   await expect(page.getByText("NLE export validation")).toBeVisible();
  98  |   await expect(page.getByText("affine_filters: 2")).toBeVisible();
  99  | });
  100 | 
  101 | test("opens persisted batch history", async ({ page }) => {
  102 |   await page.getByRole("button", { name: "Batch" }).click();
  103 |   await expect(page.getByText("Persisted batches")).toBeVisible();
  104 |   await expect(page.getByText(/11111111/)).toBeVisible();
  105 | });
  106 | 
  107 | test("cycles node width from the node header", async ({ page }) => {
  108 |   await page.getByTestId("step-ingest").click();
  109 |   const node = page.getByTestId("step-ingest");
  110 |   const before = await node.boundingBox();
  111 |   await page.getByTestId("step-width-ingest").click();
  112 |   const after = await node.boundingBox();
  113 |   expect(after?.width).not.toBe(before?.width);
  114 | });
  115 | 
  116 | test("opens the asset library tab", async ({ page }) => {
  117 |   await page.getByRole("tab", { name: "Assets" }).click();
  118 |   await expect(page.getByRole("heading", { name: "Asset library" })).toBeVisible();
  119 |   await expect(page.getByText("No assets yet")).toBeVisible();
  120 | });
  121 | 
  122 | test("opens the timeline tab", async ({ page }) => {
  123 |   await page.getByRole("tab", { name: "Timeline" }).click();
  124 |   await expect(page.getByRole("heading", { name: "Timeline" })).toBeVisible();
  125 |   await expect(page.getByText("Run a recipe to populate the timeline.")).toBeVisible();
  126 | });
  127 | 
  128 | test("opens persisted run history and shows failures", async ({ page }) => {
```