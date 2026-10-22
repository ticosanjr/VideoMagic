<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import {
    Background,
    Controls,
    MiniMap,
    SvelteFlow,
    type Connection,
    type Edge,
    type Node
  } from "@xyflow/svelte";
  import StepNode from "$lib/nodes/StepNode.svelte";
  import PathPicker from "$lib/PathPicker.svelte";
  import {
    errorMessage,
    getJob,
    getRecipe,
    listRecipes,
    listRecipeSteps,
    runRecipe,
    saveRecipe,
    validateRecipe,
    type Job,
    type Recipe,
    type RecipeSummary,
    type StepManifest
  } from "$lib/api";

  let {
    source = "",
    output = ""
  }: {
    source?: string;
    output?: string;
  } = $props();

  type NodeData = { title: string; type: string; params: Record<string, unknown> };

  const nodeTypes = { step: StepNode };
  let steps = $state<StepManifest[]>([]);
  let recipes = $state<RecipeSummary[]>([]);
  let nodes = $state<Node[]>([]);
  let edges = $state<Edge[]>([]);
  let selectedId = $state<string | null>(null);
  let recipeId = $state("my_recipe");
  let recipeName = $state("My recipe");
  let recipeDescription = $state("");
  let llm = $state<Recipe["llm"]>({
    provider: "none",
    base_url: null,
    model: "",
    api_key_env: "VIDEOWFLOW_LLM_API_KEY",
    timeout_seconds: 90
  });
  let inputSource = $state("");
  let inputOutput = $state("");
  let picker = $state<"source" | "output" | null>(null);
  let paramText = $state("{}");
  let paramError = $state("");
  let lastSelected = "";
  let status = $state("");
  let error = $state("");
  let validation = $state<string[]>([]);
  let job = $state<Job | null>(null);
  let busy = $state(false);
  let poll: ReturnType<typeof setInterval> | undefined;

  $effect(() => {
    inputSource = source;
    inputOutput = output;
  });

  $effect(() => {
    const id = selectedId;
    if (!id || id === lastSelected) return;
    lastSelected = id;
    const node = nodes.find((item) => item.id === id);
    if (node) {
      const data = nodeData(node);
      paramText = JSON.stringify(data.params ?? {}, null, 2);
      paramError = "";
    }
  });

  onMount(() => {
    void (async () => {
      try {
        steps = await listRecipeSteps();
        recipes = await listRecipes();
        const first = recipes[0];
        if (first) await loadRecipe(first.id);
      } catch (reason) {
        error = errorMessage(reason);
      }
    })();
  });

  onDestroy(() => clearInterval(poll));

  function nodeData(node: Node): NodeData {
    return node.data as unknown as NodeData;
  }

  function manifestFor(type: string): StepManifest | undefined {
    return steps.find((step) => step.type === type);
  }

  function defaultsFor(manifest: StepManifest | undefined): Record<string, unknown> {
    const schema = (manifest?.params_schema ?? {}) as {
      properties?: Record<string, { default?: unknown }>;
    };
    const defaults: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(schema.properties ?? {})) {
      if (value && Object.hasOwn(value, "default")) defaults[key] = value.default;
    }
    return defaults;
  }

  function levels(recipe: Recipe): Record<string, number> {
    const byId = new Map(recipe.steps.map((step) => [step.id, step]));
    const memo: Record<string, number> = {};
    const visiting = new Set<string>();
    function level(id: string): number {
      if (memo[id] !== undefined) return memo[id];
      if (visiting.has(id)) return 0;
      visiting.add(id);
      const step = byId.get(id);
      const value = Math.max(0, ...(step?.needs ?? []).map((need) => level(need) + 1));
      visiting.delete(id);
      memo[id] = value;
      return value;
    }
    for (const step of recipe.steps) level(step.id);
    return memo;
  }

  function graphFromRecipe(recipe: Recipe) {
    recipeId = recipe.id;
    recipeName = recipe.name;
    recipeDescription = recipe.description;
    llm = recipe.llm;
    const depth = levels(recipe);
    const rows: Record<number, number> = {};
    const next = recipe.steps.map((step) => {
      const column = depth[step.id] ?? 0;
      const row = rows[column] ?? 0;
      rows[column] = row + 1;
      const manifest = manifestFor(step.type);
      return {
        id: step.id,
        type: "step",
        position: { x: 60 + column * 280, y: 60 + row * 150 },
        data: {
          title: manifest?.title ?? step.type,
          type: step.type,
          params: step.params
        }
      } satisfies Node;
    });
    nodes = next;
    edges = recipe.steps.flatMap((step) =>
      step.needs.map((need) => ({
        id: `${need}->${step.id}`,
        source: need,
        target: step.id,
        animated: true
      }))
    );
    selectedId = null;
    lastSelected = "";
    paramText = "{}";
  }

  async function loadRecipe(id: string) {
    error = "";
    status = "";
    try {
      graphFromRecipe(await getRecipe(id));
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  function recipeFromGraph(): Recipe {
    return {
      schema_version: 1,
      id: recipeId.trim(),
      name: recipeName.trim() || "Untitled recipe",
      description: recipeDescription,
      llm,
      steps: nodes.map((node) => {
        const data = nodeData(node);
        return {
          id: node.id,
          type: data.type,
          needs: edges.filter((edge) => edge.target === node.id).map((edge) => edge.source),
          enabled: true,
          params: data.params ?? {}
        };
      })
    };
  }

  function addStep(type: string) {
    const manifest = manifestFor(type);
    if (!manifest) return;
    let suffix = 1;
    let id = type.replace(/[^a-zA-Z0-9_.-]/g, "_");
    while (nodes.some((node) => node.id === id)) {
      suffix += 1;
      id = `${type.replace(/[^a-zA-Z0-9_.-]/g, "_")}_${suffix}`;
    }
    nodes = [
      ...nodes,
      {
        id,
        type: "step",
        position: { x: 80 + (nodes.length % 4) * 240, y: 100 + Math.floor(nodes.length / 4) * 140 },
        data: {
          title: manifest.title,
          type,
          params: defaultsFor(manifest)
        }
      } satisfies Node
    ];
    selectedId = id;
  }

  function removeSelected() {
    if (!selectedId) return;
    const id = selectedId;
    nodes = nodes.filter((node) => node.id !== id);
    edges = edges.filter((edge) => edge.source !== id && edge.target !== id);
    selectedId = null;
    lastSelected = "";
    paramText = "{}";
  }

  function onConnect(connection: Connection) {
    if (!connection.source || !connection.target) return;
    if (connection.source === connection.target) return;
    if (
      edges.some(
        (edge) => edge.source === connection.source && edge.target === connection.target
      )
    ) {
      return;
    }
    edges = [
      ...edges,
      {
        id: `${connection.source}->${connection.target}`,
        source: connection.source,
        target: connection.target,
        animated: true
      }
    ];
  }

  function updateParams(value: string) {
    paramText = value;
    if (!selectedId) return;
    try {
      const parsed = JSON.parse(value);
      if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
        throw new Error("Parameters must be a JSON object");
      }
      nodes = nodes.map((node) =>
        node.id === selectedId
          ? { ...node, data: { ...nodeData(node), params: parsed } }
          : node
      );
      paramError = "";
    } catch (reason) {
      paramError = reason instanceof Error ? reason.message : String(reason);
    }
  }

  async function validate() {
    error = "";
    status = "";
    validation = [];
    try {
      const result = await validateRecipe(recipeFromGraph());
      validation = result.order;
      status = `Valid DAG: ${result.order.join(" → ")}`;
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function save() {
    error = "";
    status = "";
    try {
      await saveRecipe(recipeFromGraph());
      status = `Recipe ${recipeId} saved in the VideoFlow home directory.`;
      recipes = await listRecipes();
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function execute() {
    error = "";
    status = "";
    if (!inputSource.trim() || !inputOutput.trim()) {
      error = "Choose a source file and an output directory first.";
      return;
    }
    busy = true;
    try {
      const recipe = recipeFromGraph();
      await validateRecipe(recipe);
      job = await runRecipe({
        source: inputSource.trim(),
        output: inputOutput.trim(),
        recipe,
        save_recipe: true
      });
      watch(job.job_id);
      status = `Job ${job.job_id} started.`;
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  function watch(jobId: string) {
    clearInterval(poll);
    poll = setInterval(async () => {
      try {
        job = await getJob(jobId);
        if (["succeeded", "failed", "cancelled"].includes(job.status)) {
          clearInterval(poll);
        }
      } catch (reason) {
        error = errorMessage(reason);
        clearInterval(poll);
      }
    }, 800);
  }

  function choose(path: string) {
    if (picker === "source") inputSource = path;
    if (picker === "output") inputOutput = path;
    picker = null;
  }

  function downloadRecipe() {
    const blob = new Blob([JSON.stringify(recipeFromGraph(), null, 2) + "\n"], {
      type: "application/json"
    });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `${recipeId || "recipe"}.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }
</script>

<div class="space-y-3">
  <section class="overflow-hidden rounded-2xl border border-neutral-800 bg-neutral-900/50">
    <div class="flex flex-wrap items-center justify-between gap-3 border-b border-neutral-800 px-4 py-3">
      <div>
        <h2 class="text-sm font-semibold text-white">Recipe builder</h2>
        <p class="mt-0.5 text-[11px] text-neutral-500">
          Connect steps into a DAG. The engine executes dependencies in order; nothing is uploaded.
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2 text-xs">
        <select
          value={recipeId}
          onchange={(event) => void loadRecipe(event.currentTarget.value)}
          class="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-200"
          aria-label="Load recipe"
        >
          {#each recipes as recipe}
            <option value={recipe.id}>{recipe.name}</option>
          {/each}
        </select>
        <button type="button" onclick={downloadRecipe} class="rounded-lg border border-neutral-700 px-2.5 py-1.5 text-neutral-300 hover:border-sky-500">
          Download JSON
        </button>
        <button type="button" onclick={() => void save()} class="rounded-lg border border-neutral-700 px-2.5 py-1.5 text-neutral-300 hover:border-sky-500">
          Save
        </button>
        <button type="button" onclick={() => void validate()} class="rounded-lg border border-neutral-700 px-2.5 py-1.5 text-neutral-300 hover:border-sky-500">
          Validate
        </button>
        <button
          type="button"
          onclick={() => void execute()}
          disabled={busy}
          class="rounded-lg bg-sky-500 px-3 py-1.5 font-medium text-neutral-950 hover:bg-sky-400 disabled:opacity-50"
        >
          {busy ? "Starting…" : "Run recipe"}
        </button>
      </div>
    </div>

    <div class="grid gap-3 p-4 lg:grid-cols-[minmax(0,1fr)_300px]">
      <div>
        <div class="mb-2 grid gap-2 sm:grid-cols-2">
          <label class="block text-[10px] uppercase tracking-wide text-neutral-500">
            Input file
            <span class="mt-1 flex gap-1">
              <input bind:value={inputSource} placeholder="/media/source.mp4" class="min-w-0 flex-1 rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[11px] text-neutral-200" />
              <button type="button" onclick={() => (picker = "source")} class="rounded-lg border border-neutral-700 px-2 text-[11px] text-neutral-300">…</button>
            </span>
          </label>
          <label class="block text-[10px] uppercase tracking-wide text-neutral-500">
            Output directory
            <span class="mt-1 flex gap-1">
              <input bind:value={inputOutput} placeholder="/media/output" class="min-w-0 flex-1 rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[11px] text-neutral-200" />
              <button type="button" onclick={() => (picker = "output")} class="rounded-lg border border-neutral-700 px-2 text-[11px] text-neutral-300">…</button>
            </span>
          </label>
        </div>
        <div class="h-[480px] overflow-hidden rounded-xl border border-neutral-800 bg-neutral-950">
          <SvelteFlow
            bind:nodes
            bind:edges
            {nodeTypes}
            fitView
            minZoom={0.2}
            maxZoom={1.6}
            colorMode="dark"
            onconnect={onConnect}
            onnodeclick={({ node }) => (selectedId = node.id)}
          >
            <Background gap={20} size={1} />
            <Controls />
            <MiniMap pannable zoomable />
          </SvelteFlow>
        </div>
      </div>

      <aside class="space-y-3">
        <div class="rounded-xl border border-neutral-800 bg-neutral-950/60 p-3">
          <p class="text-[10px] uppercase tracking-wide text-neutral-500">Recipe identity</p>
          <label class="mt-2 block text-[10px] text-neutral-500">
            ID
            <input bind:value={recipeId} class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[11px] text-neutral-200" />
          </label>
          <label class="mt-2 block text-[10px] text-neutral-500">
            Name
            <input bind:value={recipeName} class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-200" />
          </label>
          <label class="mt-2 block text-[10px] text-neutral-500">
            Description
            <textarea bind:value={recipeDescription} rows="2" class="mt-1 w-full resize-y rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-200"></textarea>
          </label>
        </div>

        <div class="rounded-xl border border-neutral-800 bg-neutral-950/60 p-3">
          <div class="flex items-center justify-between">
            <p class="text-[10px] uppercase tracking-wide text-neutral-500">Selected step</p>
            <button type="button" onclick={removeSelected} disabled={!selectedId} class="text-[10px] text-rose-300 disabled:opacity-30">Remove</button>
          </div>
          {#if selectedId}
            <p class="mt-1 font-mono text-[11px] text-sky-300">{selectedId}</p>
            <p class="mt-1 text-[10px] text-neutral-500">Edit parameters as JSON. Invalid JSON is not saved to the node.</p>
            <textarea
              value={paramText}
              oninput={(event) => updateParams(event.currentTarget.value)}
              rows="10"
              spellcheck="false"
              class="mt-2 w-full resize-y rounded-lg border border-neutral-700 bg-neutral-950 p-2 font-mono text-[10px] text-neutral-200"
            ></textarea>
            {#if paramError}<p class="mt-1 text-[10px] text-rose-300">{paramError}</p>{/if}
          {:else}
            <p class="mt-2 text-[11px] text-neutral-500">Click a node to edit its parameters, or add a step below.</p>
          {/if}
        </div>

        <div class="rounded-xl border border-neutral-800 bg-neutral-950/60 p-3">
          <p class="text-[10px] uppercase tracking-wide text-neutral-500">Add step</p>
          <div class="mt-2 grid gap-1.5">
            {#each steps as step}
              <button
                type="button"
                onclick={() => addStep(step.type)}
                class="rounded-lg border border-neutral-800 px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:border-sky-500/60 hover:text-sky-200"
                title={step.description}
              >
                <span class="block">{step.title}</span>
                <span class="font-mono text-[9px] text-neutral-600">{step.type}</span>
              </button>
            {/each}
          </div>
        </div>

        <div class="rounded-xl border border-neutral-800 bg-neutral-950/60 p-3">
          <p class="text-[10px] uppercase tracking-wide text-neutral-500">LLM router</p>
          <select bind:value={llm.provider} class="mt-2 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-200">
            <option value="none">None (local-only)</option>
            <option value="openai_compatible">OpenAI-compatible</option>
            <option value="opencode">OpenCode CLI (opt-in)</option>
          </select>
          {#if llm.provider !== "none"}
            <input bind:value={llm.model} placeholder="model name" class="mt-2 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-200" />
            <input bind:value={llm.base_url} placeholder="http://localhost:11434/v1" class="mt-2 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-200" />
            <input bind:value={llm.api_key_env} placeholder="API key env var" class="mt-2 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-200" />
          {/if}
          <p class="mt-2 text-[9px] leading-4 text-neutral-600">
            Secrets stay in environment variables. The recipe stores only the variable name.
          </p>
        </div>
      </aside>
    </div>
  </section>

  {#if error}
    <div class="rounded-2xl border border-rose-500/30 bg-rose-950/30 px-4 py-3 text-xs text-rose-200">{error}</div>
  {/if}
  {#if status}
    <div class="rounded-2xl border border-emerald-500/20 bg-emerald-950/20 px-4 py-3 text-xs text-emerald-200">{status}</div>
  {/if}

  {#if job}
    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p class="text-[10px] uppercase tracking-wide text-neutral-500">Recipe job</p>
          <p class="mt-1 font-mono text-xs text-neutral-300">{job.job_id}</p>
        </div>
        <span class="rounded-full border border-neutral-700 px-2.5 py-1 text-[10px] uppercase text-neutral-300">{job.status}</span>
      </div>
      <div class="mt-3 h-2 overflow-hidden rounded-full bg-neutral-800">
        <div class="h-full rounded-full bg-sky-400 transition-all" style={`width: ${job.progress}%`}></div>
      </div>
      <p class="mt-2 text-[11px] text-neutral-400">{job.stage}: {job.message} · {job.progress}%</p>
      {#if job.error}
        <p class="mt-2 rounded-lg border border-rose-500/20 bg-rose-950/30 p-2 text-[11px] text-rose-200">{job.error.message}</p>
      {/if}
      {#if job.result?.artifacts}
        <div class="mt-3 grid gap-1.5 sm:grid-cols-2">
          {#each Object.entries(job.result.artifacts) as [target, path]}
            <div class="rounded-lg border border-neutral-800 bg-neutral-950/60 p-2 text-[10px]">
              <span class="uppercase text-neutral-500">{target}</span>
              <span class="mt-0.5 block break-all font-mono text-emerald-300">{path}</span>
            </div>
          {/each}
        </div>
      {/if}
      {#if job.result?.warnings?.length}
        <ul class="mt-3 space-y-1 text-[10px] text-amber-200">
          {#each job.result.warnings as warning}<li>{warning}</li>{/each}
        </ul>
      {/if}
    </section>
  {/if}

  {#if picker}
    <PathPicker
      open={true}
      mode={picker === "source" ? "file" : "directory"}
      title={picker === "source" ? "Choose source video" : "Choose output directory"}
      initialPath={picker === "source" ? inputSource : inputOutput}
      onclose={() => (picker = null)}
      onselect={(path) => choose(path)}
    />
  {/if}
</div>
