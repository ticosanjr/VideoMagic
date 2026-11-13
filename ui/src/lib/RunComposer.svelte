<script lang="ts">
  import Button from "$lib/ui/Button.svelte";
  import Icon from "$lib/ui/Icon.svelte";
  import Modal from "$lib/ui/Modal.svelte";
  import PathPicker from "$lib/PathPicker.svelte";
  import Progress from "$lib/ui/Progress.svelte";
  import {
    errorMessage,
    getRecipe,
    getSystem,
    preflightRecipe,
    runRecipe,
    type Job,
    type PreflightReport,
    type Recipe,
    type SystemInfo
  } from "$lib/api";

  let {
    open = false,
    recipeId = "",
    onclose,
    onstarted
  }: {
    open?: boolean;
    recipeId?: string;
    onclose: () => void;
    onstarted: (job: Job) => void;
  } = $props();

  let recipe = $state<Recipe | null>(null);
  let system = $state<SystemInfo | null>(null);
  let loading = $state(false);
  let busy = $state(false);
  let error = $state("");
  let step = $state(1);
  let source = $state("");
  let output = $state("");
  let variables = $state<Record<string, unknown>>({});
  let picker = $state<"" | "source" | "output">("");
  let loadedFor = "";
  let preflight = $state<PreflightReport | null>(null);
  let preflightBusy = $state(false);
  let preflightError = $state("");

  const requiresSource = $derived(
    Boolean(recipe?.steps.some((item) => item.type === "ingest"))
  );
  const variableEntries = $derived(
    Object.entries(recipe?.variables ?? {}) as Array<
      [
        string,
        {
          type: "string" | "number" | "boolean" | "enum";
          default?: unknown;
          description?: string;
          options?: unknown[];
          required?: boolean;
        }
      ]
    >
  );
  const missingRequired = $derived(
    variableEntries
      .filter(([, spec]) => spec.required)
      .filter(([key]) => {
        const value = variables[key];
        return value === undefined || value === null || String(value).trim() === "";
      })
      .map(([key]) => key)
  );
  const preflightReady = $derived(
    preflight ? preflight.ready !== false : true
  );
  const canStart = $derived(
    Boolean(recipe) &&
      (!requiresSource || source.trim().length > 0) &&
      missingRequired.length === 0 &&
      preflightReady &&
      !preflightBusy
  );

  $effect(() => {
    if (!open || !recipeId) return;
    if (loadedFor === recipeId) return;
    loadedFor = recipeId;
    void load();
  });

  $effect(() => {
    if (!open || step !== 2 || !recipe) return;
    void loadPreflight();
  });

  async function loadPreflight() {
    if (!recipe) return;
    preflightBusy = true;
    preflightError = "";
    try {
      const report = await preflightRecipe({
        source: requiresSource ? source.trim() : "",
        output: output.trim(),
        recipe,
        variables
      });
      preflight = {
        ...report,
        ready: report.ready !== false,
        errors: report.errors ?? 0,
        warnings: report.warnings ?? 0,
        checks: report.checks ?? []
      };
    } catch (reason) {
      preflightError = errorMessage(reason);
      preflight = null;
    } finally {
      preflightBusy = false;
    }
  }

  async function load() {
    loading = true;
    error = "";
    step = 1;
    source = "";
    output = "";
    preflight = null;
    preflightError = "";
    try {
      const [loadedRecipe, loadedSystem] = await Promise.all([
        getRecipe(recipeId),
        getSystem().catch(() => null)
      ]);
      recipe = loadedRecipe;
      system = loadedSystem;
      const defaults: Record<string, unknown> = {};
      for (const [key, spec] of Object.entries(loadedRecipe.variables ?? {})) {
        defaults[key] =
          spec.default ?? (spec.type === "boolean" ? false : spec.type === "number" ? 0 : "");
      }
      variables = defaults;
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      loading = false;
    }
  }

  async function start() {
    if (!recipe || !canStart) return;
    busy = true;
    error = "";
    try {
      const job = await runRecipe({
        source: requiresSource ? source.trim() : "",
        output: output.trim(),
        recipe,
        save_recipe: false,
        resume: true,
        variables
      });
      onstarted(job);
      onclose();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  function chooseSource(path: string) {
    source = path;
    picker = "";
  }

  function chooseOutput(path: string) {
    output = path;
    picker = "";
  }
</script>

<Modal
  {open}
  title="Start a run"
  description={recipe
    ? `${recipe.name} · ${recipe.steps.length} steps`
    : "Choose the inputs and review the preflight checks."}
  width="w-[min(820px,96vw)]"
  onclose={onclose}
>
  {#snippet footer()}
    <div class="flex flex-wrap items-center justify-between gap-2">
      <p class="text-[length:var(--vf-text-xs)] text-neutral-500">
        {step === 1 ? "Step 1 of 2 · Inputs" : "Step 2 of 2 · Review"}
      </p>
      <div class="flex gap-2">
        <Button variant="secondary" onclick={onclose}>Cancel</Button>
        {#if step === 2}
          <Button variant="secondary" icon="chevron" onclick={() => (step = 1)}>Back</Button>
        {/if}
        {#if step === 1}
          <Button variant="primary" disabled={!recipe || loading} onclick={() => (step = 2)}>Next</Button>
        {:else}
          <Button
            variant="primary"
            icon="play"
            disabled={!canStart || busy}
            onclick={() => void start()}
          >{busy ? "Starting…" : "Start run"}</Button>
        {/if}
      </div>
    </div>
  {/snippet}

  {#if loading}
    <div class="flex min-h-48 items-center justify-center gap-3 text-[length:var(--vf-text-sm)] text-neutral-400">
      <Progress value={35} label="Loading recipe" />
      Loading recipe…
    </div>
  {:else if recipe}
    {#if step === 1}
      <div class="space-y-4">
        <div class="rounded-xl border border-neutral-800 bg-neutral-900/50 p-3">
          <p class="text-[length:var(--vf-text-sm)] font-medium text-neutral-100">{recipe.name}</p>
          <p class="mt-1 text-[length:var(--vf-text-xs)] leading-5 text-neutral-400">{recipe.description}</p>
          <div class="mt-2 flex flex-wrap gap-2 text-[length:var(--vf-text-2xs)] text-neutral-500">
            <span class="rounded-full border border-white/10 px-2 py-0.5">{recipe.steps.length} steps</span>
            <span class="rounded-full border border-white/10 px-2 py-0.5">{recipe.id}</span>
          </div>
        </div>

        {#if requiresSource}
          <label class="block">
            <span class="vf-label">Source clip</span>
            <span class="mt-1.5 flex gap-2">
              <input
                bind:value={source}
                placeholder="/path/to/source.mp4"
                class="min-w-0 flex-1 rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 font-mono text-[length:var(--vf-text-xs)] text-neutral-100"
              />
              <Button variant="secondary" icon="folder" onclick={() => (picker = "source")}>Choose</Button>
            </span>
          </label>
        {:else}
          <div class="rounded-xl border border-sky-400/20 bg-sky-950/20 p-3 text-[length:var(--vf-text-xs)] text-sky-100/80">
            This recipe starts from the brief. No source clip is required.
          </div>
        {/if}

        <label class="block">
          <span class="vf-label">Workspace folder <span class="normal-case tracking-normal text-neutral-500">(optional)</span></span>
          <span class="mt-1.5 flex gap-2">
            <input
              bind:value={output}
              placeholder="Defaults to the recipe workspace"
              class="min-w-0 flex-1 rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 font-mono text-[length:var(--vf-text-xs)] text-neutral-100"
            />
            <Button variant="secondary" icon="folder" onclick={() => (picker = "output")}>Choose</Button>
          </span>
        </label>

        {#if variableEntries.length}
          <div>
            <p class="vf-label">Variables</p>
            <div class="mt-2 grid gap-3 sm:grid-cols-2">
              {#each variableEntries as [key, spec]}
                <label class="block">
                  <span class="text-[length:var(--vf-text-xs)] text-neutral-300">{key}{spec.required ? " *" : ""}</span>
                  {#if spec.description}<span class="mt-0.5 block text-[length:var(--vf-text-2xs)] text-neutral-500">{spec.description}</span>{/if}
                  {#if spec.type === "boolean"}
                    <span class="mt-1.5 flex items-center gap-2 text-[length:var(--vf-text-xs)] text-neutral-200">
                      <input type="checkbox" checked={Boolean(variables[key])} onchange={(event) => (variables[key] = event.currentTarget.checked)} class="h-4 w-4" />
                      Enabled
                    </span>
                  {:else if spec.type === "enum"}
                    <select bind:value={variables[key]} class="mt-1.5 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-[length:var(--vf-text-xs)] text-neutral-100">
                      {#each spec.options ?? [] as option}<option value={String(option)}>{String(option)}</option>{/each}
                    </select>
                  {:else}
                    <input
                      type={spec.type === "number" ? "number" : "text"}
                      bind:value={variables[key]}
                      class="mt-1.5 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-[length:var(--vf-text-xs)] text-neutral-100"
                    />
                  {/if}
                </label>
              {/each}
            </div>
          </div>
        {/if}
      </div>
    {:else}
      <div class="space-y-4">
        <div class="rounded-xl border border-neutral-800 bg-neutral-900/50 p-4">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <Icon name={preflight?.ready === false ? "close" : system?.ffmpeg ? "check" : "close"} size={16} class={preflight?.ready === false || !system?.ffmpeg ? "text-rose-300" : "text-emerald-300"} />
              <p class="text-[length:var(--vf-text-sm)] font-medium text-neutral-100">Preflight</p>
              {#if preflight}
                <span class="rounded-full border border-white/10 px-2 py-0.5 text-[length:var(--vf-text-2xs)] text-neutral-400">
                  {preflight.errors} error(s) · {preflight.warnings} warning(s)
                </span>
              {/if}
            </div>
            <button
              type="button"
              onclick={() => void loadPreflight()}
              disabled={preflightBusy}
              class="rounded-lg border border-neutral-700 px-2.5 py-1 text-[length:var(--vf-text-2xs)] text-neutral-300 disabled:opacity-40"
            >{preflightBusy ? "Checking…" : "Re-run checks"}</button>
          </div>
          {#if preflight}
            <ul class="mt-3 space-y-2 text-[length:var(--vf-text-xs)] text-neutral-300">
              {#each preflight.checks as check (check.id)}
                <li class="flex items-start gap-2">
                  <Icon
                    name={check.status === "error" ? "close" : check.status === "warning" ? "info" : "check"}
                    size={13}
                    class={`mt-0.5 ${check.status === "error" ? "text-rose-300" : check.status === "warning" ? "text-amber-300" : "text-emerald-300"}`}
                  />
                  <span class="min-w-0">
                    <span class="block text-neutral-200">{check.label}</span>
                    {#if check.detail}<span class="mt-0.5 block text-[length:var(--vf-text-2xs)] text-neutral-500">{check.detail}</span>{/if}
                    {#if check.fix && check.status !== "ok"}<span class="mt-0.5 block text-[length:var(--vf-text-2xs)] text-neutral-400">{check.fix}</span>{/if}
                  </span>
                </li>
              {/each}
            </ul>
          {:else}
            <ul class="mt-3 space-y-2 text-[length:var(--vf-text-xs)] text-neutral-300">
              <li class="flex items-center gap-2">
                <Icon name={system?.ffmpeg ? "check" : "close"} size={13} class={system?.ffmpeg ? "text-emerald-300" : "text-rose-300"} />
                {system?.ffmpeg ? "FFmpeg is ready" : "FFmpeg is missing"}
              </li>
              {#if requiresSource}
                <li class="flex items-center gap-2">
                  <Icon name={source.trim() ? "check" : "close"} size={13} class={source.trim() ? "text-emerald-300" : "text-rose-300"} />
                  {source.trim() ? "Source clip selected" : "Choose a source clip"}
                </li>
              {/if}
              {#if missingRequired.length}
                <li class="flex items-center gap-2 text-rose-200">
                  <Icon name="close" size={13} />
                  Missing required variables: {missingRequired.join(", ")}
                </li>
              {/if}
              <li class="flex items-center gap-2 text-neutral-400">
                <Icon name="folder" size={13} />
                Output: {output.trim() || "recipe workspace default"}
              </li>
            </ul>
          {/if}
          {#if preflightError}
            <p class="mt-2 rounded-lg border border-amber-500/30 bg-amber-950/30 px-2 py-1 text-[length:var(--vf-text-2xs)] text-amber-200">
              Could not run the full preflight: {preflightError}. Local checks still apply.
            </p>
          {/if}
        </div>

        <div class="rounded-xl border border-neutral-800 bg-neutral-900/50 p-4">
          <p class="vf-label">Run summary</p>
          <dl class="mt-3 grid gap-2 text-[length:var(--vf-text-xs)] sm:grid-cols-2">
            <div class="flex justify-between gap-3"><dt class="text-neutral-500">Recipe</dt><dd class="truncate text-neutral-200">{recipe.name}</dd></div>
            <div class="flex justify-between gap-3"><dt class="text-neutral-500">Steps</dt><dd class="text-neutral-200">{recipe.steps.length}</dd></div>
            <div class="flex justify-between gap-3"><dt class="text-neutral-500">Source</dt><dd class="truncate text-neutral-200">{requiresSource ? source.trim() || "missing" : "script-first"}</dd></div>
            <div class="flex justify-between gap-3"><dt class="text-neutral-500">Output</dt><dd class="truncate text-neutral-200">{output.trim() || "default"}</dd></div>
          </dl>
        </div>
      </div>
    {/if}

    {#if error}
      <p class="mt-3 rounded-lg border border-rose-500/30 bg-rose-950/30 px-3 py-2 text-[length:var(--vf-text-xs)] text-rose-200">{error}</p>
    {/if}
  {:else}
    <p class="rounded-xl border border-rose-500/30 bg-rose-950/30 px-3 py-2 text-[length:var(--vf-text-xs)] text-rose-200">{error || "Recipe not found."}</p>
  {/if}
</Modal>

<PathPicker
  open={Boolean(picker)}
  mode={picker === "output" ? "directory" : "file"}
  title={picker === "output" ? "Choose the workspace folder" : "Choose the source clip"}
  extensions={picker === "output" ? [] : [".mp4", ".mov", ".mkv", ".webm", ".m4v"]}
  initialPath={picker === "output" ? output : source}
  onclose={() => (picker = "")}
  onselect={(path) => (picker === "output" ? chooseOutput(path) : chooseSource(path))}
/>
