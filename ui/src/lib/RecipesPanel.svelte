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
  import { setPath, validateParams } from "$lib/recipeFields";
  import PathPicker from "$lib/PathPicker.svelte";
  import {
    errorMessage,
    getJob,
    getRecipe,
    jobArtifactUrl,
    shortFileUrl,
    getRunHistory,
    listJobs,
    listRecipes,
    listRecipeSteps,
    cancelBatch,
    createJobPreview,
    getBatch,
    listBatches,
    resumeBatch,
    runBatch,
    runRecipe,
    runRecipeStep,
    saveRecipe,
    validateExports,
    validateRecipe,
    type Batch,
    type Job,
    type Recipe,
    type NleValidationReport,
    type RecipeSummary,
    type RunRecord,
    type StepManifest
  } from "$lib/api";

  let {
    source = "",
    output = ""
  }: {
    source?: string;
    output?: string;
  } = $props();

  type NodeStatus =
    | "idle"
    | "queued"
    | "running"
    | "cached"
    | "executed"
    | "failed"
    | "skipped";
  type NodeData = {
    title: string;
    type: string;
    params: Record<string, unknown>;
    schema?: Record<string, unknown>;
    status?: NodeStatus;
    progress?: number;
    expanded?: boolean;
    pinned?: boolean;
    width?: number;
    onToggle?: () => void;
    onPin?: () => void;
    onPatch?: (path: string[], value: unknown) => void;
    onPickPath?: (path: string[]) => void;
    onRun?: () => void;
    onDuplicate?: () => void;
    onRemove?: () => void;
    onOpenJson?: () => void;
  };

  const nodeTypes = { step: StepNode };
  let steps = $state<StepManifest[]>([]);
  let recipes = $state<RecipeSummary[]>([]);
  let nodes = $state<Node[]>([]);
  let edges = $state<Edge[]>([]);
  let selectedId = $state<string | null>(null);
  let recipeId = $state("my_recipe");
  let recipeName = $state("My recipe");
  let recipeDescription = $state("");
  let recipeUi = $state<NonNullable<Recipe["ui"]>>({
    version: 1,
    viewport: { x: 0, y: 0, zoom: 1 },
    nodes: {}
  });
  let layoutStatus = $state("");
  let viewport = $state({ x: 0, y: 0, zoom: 1 });
  let hasSavedViewport = $state(false);
  let uiSaveTimer: ReturnType<typeof setTimeout> | undefined;
  let nodePathTarget = $state<{ nodeId: string; path: string[] } | null>(null);
  let nodePathMode = $state<"file" | "directory">("file");
  let llm = $state<Recipe["llm"]>({
    provider: "none",
    base_url: null,
    model: "",
    api_key_env: "VIDEOWFLOW_LLM_API_KEY",
    timeout_seconds: 90
  });
  let inputSource = $state("");
  let inputOutput = $state("");
  let picker = $state<
    | "source"
    | "output"
    | "batch-source"
    | "batch-output"
    | "broll"
    | "second-source"
    | "node-path"
    | null
  >(null);
  let paramText = $state("{}");
  let paramError = $state("");
  let inspectorOpen = $state(false);
  let addOpen = $state(false);
  let configOpen = $state(false);
  let jsonModal = $state<"step" | "recipe" | null>(null);
  let recipeJsonText = $state("");
  let jsonError = $state("");
  let stepQuery = $state("");
  let lastSelected = "";
  let status = $state("");
  let error = $state("");
  let validation = $state<string[]>([]);
  let job = $state<Job | null>(null);
  let busy = $state(false);
  let resume = $state(true);
  let poll: ReturnType<typeof setInterval> | undefined;
  let batchOpen = $state(false);
  let batchSourceDir = $state("");
  let batchOutputRoot = $state("");
  let batchRecursive = $state(false);
  let batchExtensions = $state("");
  let batchBusy = $state(false);
  let batch = $state<Batch | null>(null);
  let batchHistory = $state<Batch[]>([]);
  let batchPoll: ReturnType<typeof setInterval> | undefined;
  let previousJob = $state<Job | null>(null);
  let compareOpen = $state(false);
  let historyOpen = $state(false);
  let historyRuns = $state<RunRecord[]>([]);
  let historyBusy = $state(false);
  let nleOpen = $state(false);
  let nleReport = $state<NleValidationReport | null>(null);
  let nleBusy = $state(false);
  let nleError = $state("");
  let proxyUrl = $state("");
  let proxyBusy = $state(false);
  let proxyError = $state("");
  let comparison = $state<{
    current: Job;
    previous: Job;
    steps: {
      id: string;
      type: string;
      previousStatus: string;
      currentStatus: string;
      previousMs: number;
      currentMs: number;
    }[];
  } | null>(null);

  const stepOrder = [
    "ingest",
    "audio.vad",
    "transcribe",
    "audio.diarize",
    "retakes.cull",
    "edit.timeline",
    "shorts.select",
    "shorts.reframe",
    "shorts.captions",
    "broll.plan",
    "shorts.render",
    "export.nle"
  ];

  const filteredSteps = $derived(
    steps
      .filter((step) => {
        const query = stepQuery.trim().toLocaleLowerCase();
        if (!query) return true;
        return (
          step.title.toLocaleLowerCase().includes(query) ||
          step.type.toLocaleLowerCase().includes(query)
        );
      })
      .sort((left, right) => {
        const a = stepOrder.indexOf(left.type);
        const b = stepOrder.indexOf(right.type);
        return (a < 0 ? 999 : a) - (b < 0 ? 999 : b);
      })
  );

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

  onDestroy(() => {
    clearInterval(poll);
    clearInterval(batchPoll);
    clearTimeout(uiSaveTimer);
  });

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
    recipeUi = recipe.ui ?? {
      version: 1,
      viewport: { x: 0, y: 0, zoom: 1 },
      nodes: {}
    };
    hasSavedViewport = Boolean(recipe.ui?.viewport);
    viewport = { ...recipeUi.viewport };
    const depth = levels(recipe);
    const rows: Record<number, number> = {};
    const next = recipe.steps.map((step) => {
      const column = depth[step.id] ?? 0;
      const row = rows[column] ?? 0;
      rows[column] = row + 1;
      const manifest = manifestFor(step.type);
      const saved = recipeUi.nodes[step.id];
      recipeUi.nodes[step.id] = {
        x: saved?.x ?? 60 + column * 280,
        y: saved?.y ?? 60 + row * 150,
        expanded: saved?.expanded ?? false,
        pinned: saved?.pinned ?? false,
        width: saved?.width ?? 420
      };
      return {
        id: step.id,
        type: "step",
        position: { x: recipeUi.nodes[step.id].x, y: recipeUi.nodes[step.id].y },
        data: {
          title: manifest?.title ?? step.type,
          type: step.type,
          params: step.params,
          schema: manifest?.params_schema ?? {},
          status: "idle",
          progress: 0,
          expanded: recipeUi.nodes[step.id].expanded,
          pinned: recipeUi.nodes[step.id].pinned,
          width: recipeUi.nodes[step.id].width,
          onToggle: () => toggleNodeExpanded(step.id),
          onPin: () => toggleNodePinned(step.id),
          onWidth: () => cycleNodeWidth(step.id),
          onPatch: (path: string[], value: unknown) => patchNodeParams(step.id, path, value),
          onPickPath: (path: string[]) => openNodePathPicker(step.id, path),
          onRun: () => void runToHere(step.id),
          onDuplicate: () => duplicateNode(step.id),
          onRemove: () => removeNode(step.id),
          onOpenJson: () => {
            selectedId = step.id;
            openStepJson();
          }
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
    inspectorOpen = false;
    addOpen = false;
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
      ui: {
        version: 1,
        viewport,
        nodes: Object.fromEntries(
          nodes.map((node) => [
            node.id,
            {
              x: node.position.x,
              y: node.position.y,
              expanded: Boolean(nodeData(node).expanded),
              pinned: Boolean(nodeData(node).pinned),
              width: nodeData(node).width ?? 420
            }
          ])
        )
      },
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
          params: defaultsFor(manifest),
          schema: manifest.params_schema,
          status: "idle",
          progress: 0,
          expanded: true,
          pinned: false,
          width: 420,
          onToggle: () => toggleNodeExpanded(id),
          onPin: () => toggleNodePinned(id),
          onWidth: () => cycleNodeWidth(id),
          onPatch: (path: string[], value: unknown) => patchNodeParams(id, path, value),
          onPickPath: (path: string[]) => openNodePathPicker(id, path),
          onRun: () => void runToHere(id),
          onDuplicate: () => duplicateNode(id),
          onRemove: () => removeNode(id),
          onOpenJson: () => {
            selectedId = id;
            openStepJson();
          }
        }
      } satisfies Node
    ];
    recipeUi.nodes[id] = {
      x: 80 + (nodes.length % 4) * 240,
      y: 100 + Math.floor(nodes.length / 4) * 140,
      expanded: true,
      pinned: false,
      width: 420
    };
    selectedId = id;
    lastSelected = "";
    addOpen = false;
    inspectorOpen = true;
    scheduleUiSave();
  }

  function removeSelected() {
    if (selectedId) removeNode(selectedId);
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

  function selectedParams(): Record<string, unknown> {
    const node = nodes.find((item) => item.id === selectedId);
    if (!node) return {};
    return (nodeData(node).params ?? {}) as Record<string, unknown>;
  }

  function patchParams(patch: Record<string, unknown>) {
    updateParams(JSON.stringify({ ...selectedParams(), ...patch }, null, 2));
  }

  function patchCaptionStyle(key: string, value: unknown) {
    const style = (selectedParams().caption_style ?? {}) as Record<string, unknown>;
    patchParams({ caption_style: { ...style, [key]: value } });
  }

  type SchemaField = {
    key: string;
    label: string;
    kind: "boolean" | "number" | "enum" | "text";
    options: string[];
    minimum?: number;
    maximum?: number;
    step?: number;
    value: unknown;
  };

  function schemaFields(type: string): SchemaField[] {
    const manifest = manifestFor(type);
    const schema = (manifest?.params_schema ?? {}) as {
      properties?: Record<string, Record<string, unknown>>;
    };
    const params = selectedParams();
    return Object.entries(schema.properties ?? {}).flatMap(([key, spec]) => {
      const rawType = spec.type;
      if (rawType !== "boolean" && rawType !== "number" && rawType !== "integer" && rawType !== "string") {
        return [];
      }
      const enumValues = Array.isArray(spec.enum)
        ? spec.enum.map((item) => String(item))
        : [];
      const kind = rawType === "boolean"
        ? "boolean"
        : rawType === "number" || rawType === "integer"
          ? "number"
          : enumValues.length
            ? "enum"
            : "text";
      return [{
        key,
        label: String(spec.title ?? key.replaceAll("_", " ")),
        kind,
        options: enumValues,
        minimum: typeof spec.minimum === "number" ? spec.minimum : undefined,
        maximum: typeof spec.maximum === "number" ? spec.maximum : undefined,
        step: rawType === "integer" ? 1 : undefined,
        value: params[key] ?? spec.default
      } satisfies SchemaField];
    });
  }

  function setSchemaField(field: SchemaField, raw: string | boolean) {
    let value: unknown = raw;
    if (field.kind === "number") {
      value = Number(raw);
      if (!Number.isFinite(value)) return;
    }
    patchParams({ [field.key]: value });
  }

  function paramString(key: string, fallback = ""): string {
    const value = selectedParams()[key];
    return typeof value === "string" ? value : value === undefined || value === null ? fallback : String(value);
  }

  function paramNumber(key: string, fallback = 0): number {
    const value = selectedParams()[key];
    return typeof value === "number" ? value : Number(value ?? fallback) || fallback;
  }

  function paramBoolean(key: string, fallback = false): boolean {
    const value = selectedParams()[key];
    return typeof value === "boolean" ? value : fallback;
  }

  function captionString(key: string, fallback = ""): string {
    const style = (selectedParams().caption_style ?? {}) as Record<string, unknown>;
    const value = style[key];
    return typeof value === "string" ? value : fallback;
  }

  function speakerColorsText(): string {
    const style = (selectedParams().caption_style ?? {}) as Record<string, unknown>;
    const colors = style.speaker_colors;
    return Array.isArray(colors) ? colors.join(", ") : "";
  }

  function setSpeakerColors(value: string) {
    patchCaptionStyle(
      "speaker_colors",
      value.split(",").map((item) => item.trim()).filter(Boolean)
    );
  }

  async function generateProxy() {
    if (!job) return;
    proxyBusy = true;
    proxyError = "";
    try {
      const response = await createJobPreview(job.job_id);
      proxyUrl = response.url;
    } catch (reason) {
      proxyError = errorMessage(reason);
    } finally {
      proxyBusy = false;
    }
  }

  async function openNleValidation() {
    if (!inputOutput.trim()) {
      error = "Choose an output directory to validate exports.";
      return;
    }
    nleBusy = true;
    nleError = "";
    try {
      nleReport = await validateExports(inputOutput.trim());
      nleOpen = true;
    } catch (reason) {
      nleError = errorMessage(reason);
    } finally {
      nleBusy = false;
    }
  }

  async function openHistory() {
    if (!inputOutput.trim()) {
      error = "Choose an output directory to load run history.";
      return;
    }
    historyBusy = true;
    error = "";
    try {
      historyRuns = await getRunHistory(inputOutput.trim());
      historyOpen = true;
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      historyBusy = false;
    }
  }

  function jobFromRecord(record: RunRecord, current: Job): Job {
    return {
      job_id: record.job_id,
      status: record.status as Job["status"],
      progress: record.status === "succeeded" ? 100 : 0,
      stage: "done",
      message: "",
      source: current.source,
      output: current.output,
      options: {},
      result: {
        ok: true,
        recipe_id: record.recipe_id,
        step_runs: record.step_runs,
        cache_hits: record.cache_hits,
        cache_misses: record.cache_misses,
        artifacts: record.artifacts,
        warnings: record.warnings,
        elapsed_seconds: record.duration_ms / 1000
      },
      error: record.error ?? null,
      created_at: record.created_at,
      started_at: record.started_at,
      finished_at: null,
      duration_ms: record.duration_ms,
      log_count: 0,
      stages: []
    };
  }

  function compareRecord(record: RunRecord) {
    if (!job) {
      error = "Run a recipe first, then choose a previous run to compare.";
      return;
    }
    previousJob = jobFromRecord(record, job);
    historyOpen = false;
    buildComparison();
  }

  function updateParams(value: string): boolean {
    paramText = value;
    if (!selectedId) return false;
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
      return true;
    } catch (reason) {
      paramError = reason instanceof Error ? reason.message : String(reason);
      return false;
    }
  }

  function scheduleUiSave() {
    clearTimeout(uiSaveTimer);
    layoutStatus = "saving…";
    uiSaveTimer = setTimeout(async () => {
      try {
        await saveRecipe(recipeFromGraph());
        recipes = await listRecipes();
        layoutStatus = "layout saved";
      } catch (reason) {
        layoutStatus = errorMessage(reason);
      }
    }, 700);
  }

  function setNodeUi(id: string, patch: Partial<NonNullable<Recipe["ui"]>["nodes"][string]>) {
    const current = recipeUi.nodes[id] ?? {
      x: 60,
      y: 60,
      expanded: false,
      pinned: false,
      width: 420
    };
    recipeUi = {
      ...recipeUi,
      nodes: { ...recipeUi.nodes, [id]: { ...current, ...patch } }
    };
  }

  function selectNode(id: string) {
    selectedId = id;
    inspectorOpen = true;
    if (!recipeUi.nodes[id]?.expanded) toggleNodeExpanded(id);
  }

  function toggleNodeExpanded(id: string) {
    const current = recipeUi.nodes[id];
    if (!current) return;
    const next = !current.expanded;
    const updates: Record<string, boolean> = {};
    for (const node of nodes) {
      const data = nodeData(node);
      updates[node.id] = node.id === id ? next : next && !data.pinned ? false : Boolean(data.expanded);
    }
    nodes = nodes.map((node) => ({
      ...node,
      data: { ...nodeData(node), expanded: updates[node.id] ?? false }
    }));
    recipeUi = {
      ...recipeUi,
      nodes: Object.fromEntries(
        Object.entries(recipeUi.nodes).map(([key, value]) => [
          key,
          { ...value, expanded: updates[key] ?? value.expanded }
        ])
      )
    };
    setNodeUi(id, { expanded: next });
    scheduleUiSave();
  }

  function cycleNodeWidth(id: string) {
    const node = nodes.find((item) => item.id === id);
    if (!node) return;
    const widths = [360, 480, 600];
    const current = nodeData(node).width ?? 420;
    const next = widths[(widths.findIndex((value) => value >= current) + 1) % widths.length] ?? 480;
    setNodeUi(id, { width: next });
    nodes = nodes.map((item) =>
      item.id === id ? { ...item, data: { ...nodeData(item), width: next } } : item
    );
    scheduleUiSave();
  }

  function toggleNodePinned(id: string) {
    const current = recipeUi.nodes[id];
    if (!current) return;
    const pinned = !current.pinned;
    setNodeUi(id, { pinned });
    nodes = nodes.map((node) =>
      node.id === id
        ? { ...node, data: { ...nodeData(node), pinned } }
        : node
    );
    scheduleUiSave();
  }

  function patchNodeParams(id: string, path: string[], value: unknown) {
    const node = nodes.find((item) => item.id === id);
    if (!node) return;
    const params = setPath({ ...(nodeData(node).params ?? {}) }, path, value);
    nodes = nodes.map((item) =>
      item.id === id
        ? { ...item, data: { ...nodeData(item), params } }
        : item
    );
    if (selectedId === id) {
      paramText = JSON.stringify(params, null, 2);
    }
  }

  function openNodePathPicker(nodeId: string, path: string[]) {
    nodePathTarget = { nodeId, path };
    nodePathMode = /dir|directory|asset_dir/i.test(path[path.length - 1] ?? "") ? "directory" : "file";
    picker = "node-path";
  }

  function duplicateNode(id: string) {
    const source = nodes.find((node) => node.id === id);
    if (!source) return;
    const data = nodeData(source);
    let suffix = 2;
    let nextId = `${id}_copy`;
    while (nodes.some((node) => node.id === nextId)) {
      nextId = `${id}_copy${suffix++}`;
    }
    const position = { x: source.position.x + 40, y: source.position.y + 40 };
    const copy: Node = {
      ...source,
      id: nextId,
      position,
      selected: false,
      data: {
        ...data,
        onToggle: () => toggleNodeExpanded(nextId),
        onPin: () => toggleNodePinned(nextId),
        onWidth: () => cycleNodeWidth(nextId),
        onPatch: (path: string[], value: unknown) => patchNodeParams(nextId, path, value),
        onPickPath: (path: string[]) => openNodePathPicker(nextId, path),
        onRun: () => void runToHere(nextId),
        onDuplicate: () => duplicateNode(nextId),
        onRemove: () => removeNode(nextId),
        onOpenJson: () => {
          selectedId = nextId;
          openStepJson();
        }
      }
    };
    nodes = [...nodes, copy];
    recipeUi.nodes[nextId] = {
      x: position.x,
      y: position.y,
      expanded: Boolean(data.expanded),
      pinned: false,
      width: data.width ?? 420
    };
    selectedId = nextId;
    lastSelected = "";
    scheduleUiSave();
  }

  function removeNode(id: string) {
    nodes = nodes.filter((node) => node.id !== id);
    edges = edges.filter((edge) => edge.source !== id && edge.target !== id);
    delete recipeUi.nodes[id];
    if (selectedId === id) {
      selectedId = null;
      lastSelected = "";
      paramText = "{}";
    }
    scheduleUiSave();
  }

  function handleNodeDragStop(event: { nodes?: Node[] }) {
    for (const dragged of event.nodes ?? []) {
      const current = recipeUi.nodes[dragged.id];
      if (current) {
        recipeUi.nodes[dragged.id] = {
          ...current,
          x: dragged.position.x,
          y: dragged.position.y
        };
      }
    }
    scheduleUiSave();
  }

  function resetLayout() {
    const byId = new Map(nodes.map((node) => [node.id, node]));
    const depth: Record<string, number> = {};
    const visit = (id: string, trail: Set<string> = new Set()): number => {
      if (depth[id] !== undefined) return depth[id];
      if (trail.has(id)) return 0;
      const node = byId.get(id);
      if (!node) return 0;
      trail.add(id);
      const level = Math.max(
        0,
        ...edges
          .filter((edge) => edge.target === id)
          .map((edge) => visit(edge.source, trail) + 1)
      );
      trail.delete(id);
      depth[id] = level;
      return level;
    };
    const rows: Record<number, number> = {};
    nodes = nodes.map((node) => {
      const column = visit(node.id);
      const row = rows[column] ?? 0;
      rows[column] = row + 1;
      const position = { x: 60 + column * 300, y: 60 + row * 170 };
      recipeUi.nodes[node.id] = { ...(recipeUi.nodes[node.id] ?? {}), x: position.x, y: position.y } as NonNullable<Recipe["ui"]>["nodes"][string];
      return { ...node, position };
    });
    layoutStatus = "auto layout";
    scheduleUiSave();
  }

  function nodeValidationErrors(): Record<string, string> {
    const errors: Record<string, string> = {};
    for (const node of nodes) {
      const data = nodeData(node);
      for (const [key, message] of Object.entries(validateParams(data.schema ?? {}, data.params ?? {}))) {
        errors[`${node.id}.${key}`] = message;
      }
    }
    return errors;
  }

  function openStepJson() {
    if (!selectedId) return;
    jsonError = "";
    jsonModal = "step";
  }

  function openRecipeJson() {
    jsonError = "";
    addOpen = false;
    inspectorOpen = false;
    recipeJsonText = JSON.stringify(recipeFromGraph(), null, 2);
    jsonModal = "recipe";
  }

  function applyJson() {
    jsonError = "";
    if (jsonModal === "step") {
      if (!updateParams(paramText)) {
        jsonError = paramError;
        return;
      }
      jsonModal = null;
      return;
    }
    if (jsonModal === "recipe") {
      try {
        const parsed = JSON.parse(recipeJsonText) as Recipe;
        if (!parsed || !Array.isArray(parsed.steps)) {
          throw new Error("Recipe JSON must contain a steps array");
        }
        graphFromRecipe({
          schema_version: 1,
          id: parsed.id || recipeId,
          name: parsed.name || recipeName,
          description: parsed.description ?? "",
          llm: parsed.llm ?? llm,
          steps: parsed.steps
        });
        jsonModal = null;
      } catch (reason) {
        jsonError = reason instanceof Error ? reason.message : String(reason);
      }
    }
  }

  function toggleInspector() {
    inspectorOpen = !inspectorOpen;
    if (!inspectorOpen) addOpen = false;
  }

  function setStatuses(statuses: Record<string, NodeStatus>, progress: Record<string, number> = {}) {
    nodes = nodes.map((node) => {
      const status = statuses[node.id];
      const percent = progress[node.id];
      if (!status && percent === undefined) return node;
      const data = nodeData(node);
      return {
        ...node,
        data: {
          ...data,
          status: status ?? data.status,
          progress:
            percent ??
            (status === "cached" || status === "executed"
              ? 100
              : status === "failed"
                ? 0
                : data.progress)
        }
      };
    });
  }

  function resetStatuses() {
    setStatuses(Object.fromEntries(nodes.map((node) => [node.id, "idle" as NodeStatus])));
  }

  function applyJobStatuses(current: Job) {
    if (current.status === "running" || current.status === "queued") {
      const statuses: Record<string, NodeStatus> = {};
      const progress: Record<string, number> = {};
      for (const stage of current.stages) {
        if (stage.status === "running") statuses[stage.id] = "running";
        else if (stage.status === "succeeded") statuses[stage.id] = "executed";
        else if (stage.status === "failed") statuses[stage.id] = "failed";
      }
      for (const [id, percent] of Object.entries(current.step_progress ?? {})) {
        progress[id] = percent;
        if (percent < 100 && !statuses[id]) statuses[id] = "running";
      }
      setStatuses(statuses, progress);
      return;
    }
    if (current.status === "failed") {
      const statuses: Record<string, NodeStatus> = {};
      for (const stage of current.stages) {
        if (stage.status === "failed") statuses[stage.id] = "failed";
      }
      if (current.stage) statuses[current.stage] = "failed";
      setStatuses(statuses);
      return;
    }
    if (current.result?.step_runs?.length) {
      const statuses: Record<string, NodeStatus> = {};
      const progress: Record<string, number> = {};
      for (const run of current.result.step_runs) {
        statuses[run.id] = run.status === "cached" ? "cached" : "executed";
        progress[run.id] = run.progress ?? 100;
      }
      setStatuses(statuses, progress);
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
    const fieldErrors = nodeValidationErrors();
    if (Object.keys(fieldErrors).length) {
      error = `Fix ${Object.keys(fieldErrors).length} field error(s) before running.`;
      return;
    }
    busy = true;
    resetStatuses();
    previousJob = null;
    comparison = null;
    compareOpen = false;
    proxyUrl = "";
    proxyError = "";
    try {
      const recipe = recipeFromGraph();
      await validateRecipe(recipe);
      job = await runRecipe({
        source: inputSource.trim(),
        output: inputOutput.trim(),
        recipe,
        save_recipe: true,
        resume
      });
      watch(job.job_id);
      status = `Job ${job.job_id} started.`;
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  async function runToHere(stepId: string) {
    error = "";
    status = "";
    if (!inputSource.trim() || !inputOutput.trim()) {
      error = "Choose a source file and an output directory first.";
      return;
    }
    const fieldErrors = nodeValidationErrors();
    if (Object.keys(fieldErrors).length) {
      error = `Fix ${Object.keys(fieldErrors).length} field error(s) before running.`;
      return;
    }
    busy = true;
    resetStatuses();
    previousJob = null;
    comparison = null;
    compareOpen = false;
    try {
      const recipe = recipeFromGraph();
      await validateRecipe(recipe);
      job = await runRecipeStep(stepId, {
        source: inputSource.trim(),
        output: inputOutput.trim(),
        recipe,
        save_recipe: true,
        resume
      });
      watch(job.job_id);
      status = `Job ${job.job_id} started through ${stepId}.`;
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  async function loadPrevious(current: Job) {
    if (current.status !== "succeeded") return;
    try {
      const records = await getRunHistory(current.output);
      const record = records
        .filter(
          (item) =>
            item.job_id !== current.job_id &&
            item.recipe_id === current.result?.recipe_id &&
            item.status === "succeeded"
        )
        .sort((left, right) => right.created_at.localeCompare(left.created_at))[0];
      if (record) {
        previousJob = {
          job_id: record.job_id,
          status: "succeeded",
          progress: 100,
          stage: "done",
          message: "",
          source: current.source,
          output: current.output,
          options: {},
          result: {
            ok: true,
            recipe_id: record.recipe_id,
            step_runs: record.step_runs,
            cache_hits: record.cache_hits,
            cache_misses: record.cache_misses,
            artifacts: record.artifacts,
            warnings: record.warnings,
            elapsed_seconds: record.duration_ms / 1000
          },
          error: null,
          created_at: record.created_at,
          started_at: record.started_at,
          finished_at: null,
          duration_ms: record.duration_ms,
          log_count: 0,
          stages: []
        };
        return;
      }
      const history = await listJobs();
      const candidates = history
        .filter(
          (item) =>
            item.job_id !== current.job_id &&
            item.output === current.output &&
            item.result?.recipe_id === current.result?.recipe_id &&
            item.status === "succeeded"
        )
        .sort((left, right) => right.created_at.localeCompare(left.created_at));
      previousJob = candidates[0] ?? null;
    } catch {
      previousJob = null;
    }
  }

  function buildComparison() {
    if (!job || !previousJob) return;
    const previousRuns = new Map(
      (previousJob.result?.step_runs ?? []).map((run) => [run.id, run])
    );
    const currentRuns = job.result?.step_runs ?? [];
    comparison = {
      current: job,
      previous: previousJob,
      steps: currentRuns.map((run) => {
        const previous = previousRuns.get(run.id);
        return {
          id: run.id,
          type: run.type,
          previousStatus: previous?.status ?? "—",
          currentStatus: run.status,
          previousMs: previous?.elapsed_ms ?? 0,
          currentMs: run.elapsed_ms
        };
      })
    };
    compareOpen = true;
  }

  function runDuration(run: Job): string {
    if (run.duration_ms !== null && run.duration_ms !== undefined) {
      return `${(run.duration_ms / 1000).toFixed(1)}s`;
    }
    return run.result?.elapsed_seconds !== undefined
      ? `${run.result.elapsed_seconds.toFixed(1)}s`
      : "—";
  }

  function cachedCount(run: Job): number {
    return (run.result?.step_runs ?? []).filter((step) => step.status === "cached").length;
  }

  function executedCount(run: Job): number {
    return (run.result?.step_runs ?? []).filter((step) => step.status === "executed").length;
  }

  function watch(jobId: string) {
    clearInterval(poll);
    poll = setInterval(async () => {
      try {
        job = await getJob(jobId);
        if (job) applyJobStatuses(job);
        if (["succeeded", "failed", "cancelled"].includes(job.status)) {
          clearInterval(poll);
          void loadPrevious(job);
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
    if (picker === "batch-source") batchSourceDir = path;
    if (picker === "batch-output") batchOutputRoot = path;
    if (picker === "broll") patchParams({ asset_dir: path });
    if (picker === "second-source") patchParams({ second_source_path: path });
    if (picker === "node-path" && nodePathTarget) {
      patchNodeParams(nodePathTarget.nodeId, nodePathTarget.path, path);
      nodePathTarget = null;
    }
    picker = null;
  }

  async function openBatchHistory() {
    batchOpen = true;
    addOpen = false;
    inspectorOpen = false;
    try {
      batchHistory = await listBatches();
    } catch {
      batchHistory = [];
    }
  }

  async function loadBatch(batchId: string) {
    try {
      batch = await getBatch(batchId);
      watchBatch(batchId);
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function startBatch() {
    error = "";
    status = "";
    if (!batchSourceDir.trim() || !batchOutputRoot.trim()) {
      error = "Choose a batch input folder and an output root first.";
      return;
    }
    batchBusy = true;
    try {
      const extensions = batchExtensions
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      batch = await runBatch({
        source_dir: batchSourceDir.trim(),
        output_root: batchOutputRoot.trim(),
        recipe: recipeFromGraph(),
        recursive: batchRecursive,
        extensions,
        resume,
        max_files: 200
      });
      watchBatch(batch.batch_id);
      status = `Batch ${batch.batch_id} started.`;
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      batchBusy = false;
    }
  }

  function watchBatch(batchId: string) {
    clearInterval(batchPoll);
    batchPoll = setInterval(async () => {
      try {
        batch = await getBatch(batchId);
        if (["succeeded", "failed", "cancelled"].includes(batch.status)) {
          clearInterval(batchPoll);
        }
      } catch (reason) {
        error = errorMessage(reason);
        clearInterval(batchPoll);
      }
    }, 900);
  }

  async function resumeCurrentBatch() {
    if (!batch) return;
    try {
      batch = await resumeBatch(batch.batch_id);
      watchBatch(batch.batch_id);
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function stopBatch() {
    if (!batch) return;
    try {
      batch = await cancelBatch(batch.batch_id);
    } catch (reason) {
      error = errorMessage(reason);
    }
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
  <section class="relative overflow-hidden rounded-2xl border border-neutral-800 bg-neutral-900/50">
    <div class="flex flex-wrap items-center justify-between gap-2 border-b border-neutral-800 px-3 py-3 sm:px-4">
      <div class="min-w-0">
        <h2 class="text-sm font-semibold text-white">Recipe builder</h2>
        <p class="mt-0.5 hidden text-[11px] text-neutral-500 sm:block">
          Connect steps into a DAG. The engine executes dependencies in order; nothing is uploaded.
        </p>
      </div>
      <div class="flex flex-wrap items-center justify-end gap-1.5 text-xs">
        <button
          type="button"
          data-testid="recipe-add-step"
          onclick={() => {
            addOpen = !addOpen;
            inspectorOpen = false;
          }}
          class="rounded-lg border border-sky-500/40 bg-sky-500/10 px-2.5 py-1.5 font-medium text-sky-200 hover:bg-sky-500/20"
        >
          + Add step
        </button>
        <button
          type="button"
          onclick={() => void openBatchHistory()}
          class="rounded-lg border border-neutral-700 px-2.5 py-1.5 text-neutral-300 hover:border-sky-500"
        >
          Batch
        </button>
        <button
          type="button"
          data-testid="nle-validate"
          onclick={() => void openNleValidation()}
          disabled={nleBusy}
          class="rounded-lg border border-neutral-700 px-2.5 py-1.5 text-neutral-300 hover:border-sky-500 disabled:opacity-40"
        >
          {nleBusy ? "Validating…" : "Validate"}
        </button>
        <button
          type="button"
          data-testid="recipe-runs"
          onclick={() => void openHistory()}
          disabled={historyBusy}
          class="rounded-lg border border-neutral-700 px-2.5 py-1.5 text-neutral-300 hover:border-sky-500 disabled:opacity-40"
        >
          {historyBusy ? "Runs…" : "Runs"}
        </button>
        <button
          type="button"
          onclick={() => {
            configOpen = true;
            addOpen = false;
          }}
          class="rounded-lg border border-neutral-700 px-2.5 py-1.5 text-neutral-300 hover:border-sky-500"
        >
          Config
        </button>
        <button
          type="button"
          onclick={toggleInspector}
          aria-pressed={inspectorOpen}
          class={`rounded-lg border px-2.5 py-1.5 ${
            inspectorOpen
              ? "border-sky-500/50 bg-sky-500/10 text-sky-200"
              : "border-neutral-700 text-neutral-300 hover:border-sky-500"
          }`}
        >
          Inspector
        </button>
        <button
          type="button"
          data-testid="recipe-reset-layout"
          onclick={resetLayout}
          class="rounded-lg border border-neutral-700 px-2.5 py-1.5 text-neutral-300 hover:border-sky-500"
        >
          Auto layout
        </button>
        <button
          type="button"
          onclick={openRecipeJson}
          class="rounded-lg border border-neutral-700 px-2.5 py-1.5 text-neutral-300 hover:border-sky-500"
        >
          JSON
        </button>
        <select
          value={recipeId}
          onchange={(event) => void loadRecipe(event.currentTarget.value)}
          class="max-w-[190px] rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-200"
          aria-label="Load recipe"
        >
          {#each recipes as recipe}
            <option value={recipe.id}>{recipe.name}</option>
          {/each}
        </select>
        <button type="button" onclick={downloadRecipe} class="rounded-lg border border-neutral-700 px-2.5 py-1.5 text-neutral-300 hover:border-sky-500">
          Download
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
          {busy ? "Starting…" : "Run"}
        </button>
      </div>
    </div>

    <div class="p-3 sm:p-4">
      <div class="mb-3 grid gap-2 sm:grid-cols-2">
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

      <div class="relative">
        <div class="h-[clamp(560px,72vh,920px)] overflow-hidden rounded-xl border border-neutral-800 bg-neutral-950">
          <SvelteFlow
            bind:nodes
            bind:edges
            {nodeTypes}
            fitView={!hasSavedViewport}
            bind:viewport
            minZoom={0.2}
            maxZoom={1.6}
            colorMode="dark"
            onconnect={onConnect}
            onnodedragstop={handleNodeDragStop}
            onmoveend={() => scheduleUiSave()}
            onnodeclick={({ node }) => selectNode(node.id)}
          >
            <Background gap={20} size={1} />
            <Controls />
            <MiniMap pannable zoomable />
          </SvelteFlow>
        </div>

        {#if addOpen}
          <div class="absolute left-2 top-2 z-40 flex max-h-[calc(100%-1rem)] w-[min(340px,calc(100%-1rem))] flex-col overflow-hidden rounded-2xl border border-sky-500/30 bg-neutral-950/98 shadow-2xl backdrop-blur">
            <div class="flex items-center justify-between border-b border-neutral-800 px-3 py-2">
              <div>
                <p class="text-[10px] uppercase tracking-wide text-sky-300">Add step</p>
                <p class="text-[10px] text-neutral-500">Click to place a node on the canvas.</p>
              </div>
              <button type="button" onclick={() => (addOpen = false)} class="rounded px-1.5 text-neutral-500 hover:text-neutral-200" aria-label="Close add step">×</button>
            </div>
            <div class="p-2">
              <input
                bind:value={stepQuery}
                placeholder="Filter steps…"
                class="w-full rounded-lg border border-neutral-700 bg-neutral-900 px-2 py-1.5 text-[11px] text-neutral-200"
              />
            </div>
            <div class="min-h-0 flex-1 space-y-1 overflow-y-auto p-2 pt-0">
              {#each filteredSteps as step}
                <button
                  type="button"
                  data-testid={`add-${step.type}`}
                  onclick={() => addStep(step.type)}
                  class="w-full rounded-lg border border-neutral-800 px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:border-sky-500/60 hover:text-sky-200"
                  title={step.description}
                >
                  <span class="block">{step.title}</span>
                  <span class="font-mono text-[9px] text-neutral-600">{step.type}</span>
                </button>
              {/each}
              {#if filteredSteps.length === 0}
                <p class="px-2 py-3 text-[11px] text-neutral-500">No step matches that filter.</p>
              {/if}
            </div>
          </div>
        {/if}

        {#if inspectorOpen}
          <aside class="absolute bottom-2 right-2 top-2 z-30 flex w-[min(380px,calc(100%-1rem))] flex-col overflow-hidden rounded-2xl border border-neutral-700 bg-neutral-950/98 shadow-2xl backdrop-blur">
            <div class="flex items-center justify-between border-b border-neutral-800 px-3 py-2">
              <div class="min-w-0">
                <p class="text-[10px] uppercase tracking-wide text-neutral-500">Step inspector</p>
                <p class="truncate font-mono text-[11px] text-sky-300">{selectedId ?? "No node selected"}</p>
              </div>
              <button type="button" onclick={() => (inspectorOpen = false)} class="rounded px-1.5 text-neutral-500 hover:text-neutral-200" aria-label="Close inspector">×</button>
            </div>
            <div class="min-h-0 flex-1 overflow-y-auto p-3">
              {#if selectedId}
                {@const selectedNode = nodes.find((node) => node.id === selectedId)}
                {@const selectedType = selectedNode ? nodeData(selectedNode).type : ""}
                {#if selectedNode}
                  <div class="flex items-center justify-between gap-2">
                    <p class="text-[10px] text-neutral-500">{nodeData(selectedNode).type}</p>
                    <div class="flex items-center gap-2">
                      <button type="button" onclick={() => void runToHere(selectedId ?? "")} disabled={busy} class="rounded border border-sky-500/40 px-2 py-0.5 text-[10px] text-sky-300 disabled:opacity-40">Run to here</button>
                      <button type="button" onclick={removeSelected} class="text-[10px] text-rose-300 hover:text-rose-200">Remove</button>
                    </div>
                  </div>
                {/if}
                {#if selectedType === "edit.timeline"}
                  <div class="mt-3 rounded-lg border border-neutral-800 bg-neutral-900/60 p-2">
                    <p class="text-[10px] uppercase tracking-wide text-neutral-500">Transitions</p>
                    <div class="mt-2 grid grid-cols-2 gap-2">
                      <label class="text-[10px] text-neutral-400">Frames
                        <input data-testid="transition-frames" type="number" min="0" max="120" value={paramNumber("transition_frames", 0)}
                          oninput={(event) => patchParams({ transition_frames: Number(event.currentTarget.value) })}
                          class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100" />
                      </label>
                      <label class="text-[10px] text-neutral-400">Type
                        <select data-testid="transition-type" value={paramString("transition_type", "crossfade")}
                          onchange={(event) => patchParams({ transition_type: event.currentTarget.value })}
                          class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100">
                          <option value="crossfade">Crossfade</option>
                          <option value="fade_to_black">Fade to black</option>
                        </select>
                      </label>
                    </div>
                    <label class="mt-2 flex items-center gap-2 text-[10px] text-neutral-400">
                      <input type="checkbox" checked={paramBoolean("progressive_zoom")} onchange={(event) => patchParams({ progressive_zoom: event.currentTarget.checked })} />
                      Progressive zoom keyframes
                    </label>
                  </div>
                {/if}
                {#if selectedType === "audio.diarize"}
                  <div class="mt-3 rounded-lg border border-neutral-800 bg-neutral-900/60 p-2">
                    <p class="text-[10px] uppercase tracking-wide text-neutral-500">Speaker turns</p>
                    <div class="mt-2 grid grid-cols-2 gap-2">
                      <label class="text-[10px] text-neutral-400">Method
                        <select value={paramString("method", "heuristic")} onchange={(event) => patchParams({ method: event.currentTarget.value })}
                          class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100">
                          <option value="heuristic">Heuristic</option>
                          <option value="pyannote">pyannote model</option>
                          <option value="none">Disabled</option>
                        </select>
                      </label>
                      <label class="text-[10px] text-neutral-400">Pause (ms)
                        <input type="number" min="50" max="5000" value={paramNumber("pause_ms", 400)}
                          oninput={(event) => patchParams({ pause_ms: Number(event.currentTarget.value) })}
                          class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100" />
                      </label>
                    </div>
                    {#if paramString("method", "heuristic") === "pyannote"}
                      <label class="mt-2 block text-[10px] text-neutral-400">Model
                        <input type="text" value={paramString("model_path", "pyannote/speaker-diarization-3.1")}
                          oninput={(event) => patchParams({ model_path: event.currentTarget.value })}
                          class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[10px] text-neutral-100" />
                      </label>
                      <label class="mt-1 flex items-center gap-2 text-[10px] text-neutral-400">
                        <input type="checkbox" checked={paramBoolean("fallback_to_heuristic", true)} onchange={(event) => patchParams({ fallback_to_heuristic: event.currentTarget.checked })} />
                        Fall back to heuristic if the model is unavailable
                      </label>
                    {/if}
                  </div>
                {/if}
                {#if selectedType === "broll.plan"}
                  <div class="mt-3 rounded-lg border border-neutral-800 bg-neutral-900/60 p-2">
                    <p class="text-[10px] uppercase tracking-wide text-neutral-500">B-roll source</p>
                    <label class="mt-2 block text-[10px] text-neutral-400">Provider
                      <select value={paramString("provider", "local")} onchange={(event) => patchParams({ provider: event.currentTarget.value })}
                        class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100">
                        <option value="local">Local assets</option>
                        <option value="pexels">Pexels stock</option>
                      </select>
                    </label>
                    <label class="mt-2 block text-[10px] text-neutral-400">Search hint
                      <input type="text" value={paramString("query")} oninput={(event) => patchParams({ query: event.currentTarget.value })}
                        placeholder="optional keywords"
                        class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100" />
                    </label>
                    {#if paramString("provider", "local") === "pexels"}
                      <label class="mt-2 block text-[10px] text-neutral-400">API key environment variable
                        <input type="text" value={paramString("api_key_env", "PEXELS_API_KEY")} oninput={(event) => patchParams({ api_key_env: event.currentTarget.value })}
                          class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[10px] text-neutral-100" />
                      </label>
                    {:else}
                    <label class="mt-2 block text-[10px] text-neutral-400">Asset directory
                      <div class="mt-1 flex gap-1">
                        <input type="text" value={paramString("asset_dir")}
                          oninput={(event) => patchParams({ asset_dir: event.currentTarget.value })}
                          placeholder="/path/to/broll"
                          class="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[10px] text-neutral-100" />
                        <button type="button" onclick={() => (picker = "broll")} class="rounded border border-neutral-700 px-2 text-[10px] text-neutral-300 hover:border-sky-500">Browse</button>
                      </div>
                    </label>
                    {/if}
                    <div class="mt-2 grid grid-cols-2 gap-2">
                      <label class="text-[10px] text-neutral-400">Max per Short
                        <input type="number" min="1" max="5" value={paramNumber("max_per_short", 1)}
                          oninput={(event) => patchParams({ max_per_short: Number(event.currentTarget.value) })}
                          class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100" />
                      </label>
                      <label class="text-[10px] text-neutral-400">Cutaway sec
                        <input type="number" min="0.2" max="30" step="0.1" value={paramNumber("duration_sec", 2)}
                          oninput={(event) => patchParams({ duration_sec: Number(event.currentTarget.value) })}
                          class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100" />
                      </label>
                    </div>
                  </div>
                {/if}
                {#if selectedType === "shorts.reframe"}
                  <div class="mt-3 rounded-lg border border-neutral-800 bg-neutral-900/60 p-2">
                    <p class="text-[10px] uppercase tracking-wide text-neutral-500">Dialogue layout</p>
                    <label class="mt-2 flex items-center gap-2 text-[10px] text-neutral-400">
                      <input type="checkbox" checked={paramBoolean("split_screen_on_dialogue")} onchange={(event) => patchParams({ split_screen_on_dialogue: event.currentTarget.checked })} />
                      Use split-screen when a clip has multiple speakers
                    </label>
                  </div>
                {/if}
                {#if selectedType === "shorts.render" || selectedType === "shorts.captions"}
                  <div class="mt-3 rounded-lg border border-neutral-800 bg-neutral-900/60 p-2">
                    <p class="text-[10px] uppercase tracking-wide text-neutral-500">Captions and layout</p>
                    <label class="mt-2 block text-[10px] text-neutral-400">Speaker colors (comma-separated)
                      <input type="text" value={speakerColorsText()}
                        oninput={(event) => setSpeakerColors(event.currentTarget.value)}
                        placeholder="#FFFFFF, #00E5FF, #FFD400"
                        class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[10px] text-neutral-100" />
                    </label>
                    {#if selectedType === "shorts.render"}
                      <label class="mt-2 flex items-center gap-2 text-[10px] text-neutral-400">
                        <input type="checkbox" checked={paramBoolean("split_screen")} onchange={(event) => patchParams({ split_screen: event.currentTarget.checked })} />
                        Split-screen vertical frame
                      </label>
                      <label class="mt-2 block text-[10px] text-neutral-400">Second source (optional)
                        <div class="mt-1 flex gap-1">
                          <input type="text" value={paramString("second_source_path")}
                            oninput={(event) => patchParams({ second_source_path: event.currentTarget.value })}
                            placeholder="/path/to/second-angle.mp4"
                            class="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[10px] text-neutral-100" />
                          <button type="button" onclick={() => (picker = "second-source")} class="rounded border border-neutral-700 px-2 text-[10px] text-neutral-300 hover:border-sky-500">Browse</button>
                        </div>
                      </label>
                      <div class="mt-2 grid grid-cols-3 gap-2">
                        <label class="text-[10px] text-neutral-400">Zoom
                          <input type="number" min="1" max="2" step="0.05" value={paramNumber("split_screen_zoom", 1)}
                            oninput={(event) => patchParams({ split_screen_zoom: Number(event.currentTarget.value) })}
                            class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100" />
                        </label>
                        <label class="text-[10px] text-neutral-400">Left focus
                          <input type="number" min="0" max="1" step="0.05" value={paramNumber("split_screen_focus_left", 0.5)}
                            oninput={(event) => patchParams({ split_screen_focus_left: Number(event.currentTarget.value) })}
                            class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100" />
                        </label>
                        <label class="text-[10px] text-neutral-400">Right focus
                          <input type="number" min="0" max="1" step="0.05" value={paramNumber("split_screen_focus_right", 0.5)}
                            oninput={(event) => patchParams({ split_screen_focus_right: Number(event.currentTarget.value) })}
                            class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100" />
                        </label>
                      </div>
                      <label class="mt-1 flex items-center gap-2 text-[10px] text-neutral-400">
                        <input type="checkbox" checked={paramBoolean("mix_second_audio")} onchange={(event) => patchParams({ mix_second_audio: event.currentTarget.checked })} />
                        Mix second-source audio
                      </label>
                      <label class="mt-1 flex items-center gap-2 text-[10px] text-neutral-400">
                        <input type="checkbox" checked={paramBoolean("broll_enabled", true)} onchange={(event) => patchParams({ broll_enabled: event.currentTarget.checked })} />
                        Apply planned B-roll
                      </label>
                    {/if}
                  </div>
                {/if}
                {#if selectedType && schemaFields(selectedType).length}
                  <div class="mt-3 rounded-lg border border-neutral-800 bg-neutral-900/60 p-2">
                    <p class="text-[10px] uppercase tracking-wide text-neutral-500">Schema fields</p>
                    <div class="mt-2 space-y-2">
                      {#each schemaFields(selectedType) as field (field.key)}
                        <label class="block text-[10px] text-neutral-400">
                          {field.label}
                          {#if field.kind === "boolean"}
                            <input
                              data-testid={`schema-${field.key}`}
                              type="checkbox"
                              checked={field.value === true}
                              onchange={(event) => setSchemaField(field, event.currentTarget.checked)}
                              class="mt-1 block"
                            />
                          {:else if field.kind === "enum"}
                            <select
                              data-testid={`schema-${field.key}`}
                              value={field.value === undefined || field.value === null ? "" : String(field.value)}
                              onchange={(event) => setSchemaField(field, event.currentTarget.value)}
                              class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100"
                            >
                              {#each field.options as option}<option value={option}>{option}</option>{/each}
                            </select>
                          {:else if field.kind === "number"}
                            <input
                              data-testid={`schema-${field.key}`}
                              type="number"
                              min={field.minimum}
                              max={field.maximum}
                              step={field.step}
                              value={typeof field.value === "number" ? field.value : ""}
                              oninput={(event) => setSchemaField(field, event.currentTarget.value)}
                              class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100"
                            />
                          {:else}
                            <input
                              data-testid={`schema-${field.key}`}
                              type="text"
                              value={field.value === undefined || field.value === null ? "" : String(field.value)}
                              oninput={(event) => setSchemaField(field, event.currentTarget.value)}
                              class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100"
                            />
                          {/if}
                        </label>
                      {/each}
                    </div>
                  </div>
                {/if}
                <div class="mt-2 flex items-center justify-between gap-2">
                  <p class="text-[10px] text-neutral-500">Parameters (JSON)</p>
                  <button type="button" onclick={openStepJson} class="rounded border border-neutral-700 px-2 py-0.5 text-[10px] text-neutral-300 hover:border-sky-500">Expand</button>
                </div>
                <textarea
                  data-testid="step-params-json"
                  value={paramText}
                  oninput={(event) => updateParams(event.currentTarget.value)}
                  rows="12"
                  spellcheck="false"
                  class="mt-1 w-full resize-y rounded-lg border border-neutral-700 bg-neutral-950 p-2 font-mono text-[10px] text-neutral-200"
                ></textarea>
                {#if paramError}<p class="mt-1 text-[10px] text-rose-300">{paramError}</p>{/if}
                <p class="mt-2 text-[9px] leading-4 text-neutral-600">
                  JSON is applied to the node while it is valid. Use Expand for a large editor.
                </p>
              {:else}
                <p class="text-[11px] text-neutral-500">Click a node to edit it. Use <span class="text-sky-300">+ Add step</span> to place a new one.</p>
                <button type="button" onclick={() => { inspectorOpen = false; addOpen = true; }} class="mt-3 w-full rounded-lg border border-neutral-700 px-2 py-1.5 text-[11px] text-neutral-300 hover:border-sky-500">Open step palette</button>
              {/if}
            </div>
          </aside>
        {/if}
      </div>
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
      {#if job.result?.step_runs?.length}
        <p class="mt-1 text-[10px] text-neutral-500">
          Steps: {job.result.step_runs.filter((run) => run.status === "cached").length} cached ·
          {job.result.step_runs.filter((run) => run.status === "executed").length} executed
        </p>
      {/if}
      {#if job.result?.cache_hits?.length}
        <p class="mt-1 text-[10px] text-emerald-300">Cache hits: {job.result.cache_hits.join(", ")}</p>
      {/if}
      {#if previousJob}
        <div class="mt-3 flex flex-wrap items-center justify-between gap-2 rounded-lg border border-neutral-800 bg-neutral-950/60 px-3 py-2">
          <p class="text-[10px] text-neutral-500">
            Previous run: <span class="text-neutral-300">{runDuration(previousJob)}</span> ·
            {cachedCount(previousJob)} cached · {executedCount(previousJob)} executed
          </p>
          <button type="button" onclick={buildComparison} class="rounded-lg border border-sky-500/40 px-2.5 py-1 text-[10px] text-sky-300 hover:bg-sky-500/10">
            Compare
          </button>
        </div>
      {/if}
      {#if job.error}
        <p class="mt-2 rounded-lg border border-rose-500/20 bg-rose-950/30 p-2 text-[11px] text-rose-200">{job.error.message}</p>
      {/if}
      {#if job.result?.artifacts}
        <div class="mt-3 grid gap-1.5 sm:grid-cols-2">
          {#each Object.entries(job.result.artifacts) as [target, path]}
            <div class="rounded-lg border border-neutral-800 bg-neutral-950/60 p-2 text-[10px]">
              <span class="uppercase text-neutral-500">{target}</span>
              <span class="mt-0.5 block break-all font-mono text-emerald-300">{path}</span>
              {#if String(path).toLowerCase().endsWith(".mp4")}
                <video
                  class="mt-2 w-full rounded border border-neutral-800"
                  controls
                  preload="metadata"
                  src={jobArtifactUrl(job.job_id, target)}
                ><track kind="captions" src="data:text/vtt;charset=utf-8,WEBVTT%0A%0A" /></video>
              {/if}
            </div>
          {/each}
        </div>
      {/if}
      {#if job.status === "succeeded" && job.result?.artifacts && Object.keys(job.result.artifacts).length}
        <div class="mt-3 rounded-lg border border-neutral-800 bg-neutral-950/60 p-2">
          <div class="flex items-center justify-between gap-2">
            <p class="text-[10px] uppercase tracking-wide text-neutral-500">Preview proxy</p>
            <button type="button" onclick={() => void generateProxy()} disabled={proxyBusy} class="rounded border border-sky-500/40 px-2 py-1 text-[10px] text-sky-300 disabled:opacity-40">{proxyBusy ? "Gerando…" : "Gerar proxy 540p"}</button>
          </div>
          {#if proxyError}<p class="mt-1 text-[10px] text-rose-300">{proxyError}</p>{/if}
          {#if proxyUrl}
            <video class="mt-2 w-full rounded border border-neutral-800" controls preload="metadata" src={proxyUrl}><track kind="captions" src="data:text/vtt;charset=utf-8,WEBVTT%0A%0A" /></video>
          {/if}
        </div>
      {/if}
      {#if job.result?.shorts?.length}
        <div class="mt-3">
          <p class="text-[10px] uppercase tracking-wide text-neutral-500">Short previews</p>
          <div class="mt-2 grid gap-2 sm:grid-cols-2">
            {#each job.result.shorts.slice(0, 4) as short, index}
              <div class="rounded-lg border border-neutral-800 bg-neutral-950/60 p-2">
                <p class="truncate text-[10px] text-neutral-300">{short.title}</p>
                <video class="mt-1 w-full rounded" controls preload="metadata" src={shortFileUrl(job.job_id, index)}><track kind="captions" src="data:text/vtt;charset=utf-8,WEBVTT%0A%0A" /></video>
              </div>
            {/each}
          </div>
        </div>
      {/if}
      {#if job.result?.broll_plan && Object.keys(job.result.broll_plan).length}
        <div class="mt-3 rounded-lg border border-neutral-800 bg-neutral-950/60 p-2">
          <p class="text-[10px] uppercase tracking-wide text-neutral-500">B-roll plan</p>
          {#each Object.entries(job.result.broll_plan) as [title, entries]}
            <div class="mt-1 text-[10px] text-neutral-300">{title}</div>
            {#each entries as entry}
              <div class="ml-2 truncate font-mono text-[9px] text-neutral-500">
                {entry.provider ?? "local"} · {entry.license ?? "operator"} · {entry.path}
              </div>
            {/each}
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

  {#if nleOpen && nleReport}
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-3" role="presentation"
      onclick={(event) => { if (event.currentTarget === event.target) nleOpen = false; }}>
      <div class="flex max-h-[88vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-neutral-700 bg-neutral-950 shadow-2xl" role="dialog" aria-modal="true" aria-label="NLE validation">
        <div class="flex items-center justify-between border-b border-neutral-800 px-4 py-3">
          <div>
            <h3 class="text-sm font-semibold text-white">NLE export validation</h3>
            <p class="text-[10px] text-neutral-500">{nleReport.directory}</p>
          </div>
          <button type="button" onclick={() => (nleOpen = false)} class="rounded px-2 text-neutral-500 hover:text-neutral-200" aria-label="Close validation">×</button>
        </div>
        <div data-testid="nle-report" class="min-h-0 flex-1 overflow-y-auto p-3">
          <div class="space-y-2">
            {#each Object.entries(nleReport.exports) as [name, check]}
              <div class="rounded-xl border border-neutral-800 bg-neutral-900/60 p-3">
                <div class="flex items-center justify-between">
                  <p class="text-xs font-medium uppercase text-neutral-200">{name}</p>
                  <span class={`rounded px-2 py-0.5 text-[10px] ${check.ok ? "bg-emerald-500/10 text-emerald-300" : "bg-rose-500/10 text-rose-300"}`}>{check.ok ? "ok" : "failed"}</span>
                </div>
                <p class="mt-1 break-all font-mono text-[9px] text-neutral-500">{check.path}</p>
                {#each check.errors as error}<p class="mt-1 text-[10px] text-rose-300">{error}</p>{/each}
                {#each check.warnings as warning}<p class="mt-1 text-[10px] text-amber-300">{warning}</p>{/each}
                <div class="mt-2 flex flex-wrap gap-2 text-[9px] text-neutral-500">
                  {#each Object.entries(check) as [key, value]}
                    {#if !["ok", "path", "errors", "warnings"].includes(key)}
                      <span>{key}: {String(value)}</span>
                    {/if}
                  {/each}
                </div>
              </div>
            {/each}
          </div>
        </div>
      </div>
    </div>
  {/if}

  {#if nleError}<p class="text-[10px] text-rose-300">{nleError}</p>{/if}

  {#if historyOpen}
    <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-3" role="presentation"
      onclick={(event) => { if (event.currentTarget === event.target) historyOpen = false; }}>
      <div class="flex max-h-[88vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-neutral-700 bg-neutral-950 shadow-2xl" role="dialog" aria-modal="true" aria-label="Run history">
        <div class="flex items-center justify-between border-b border-neutral-800 px-4 py-3">
          <div>
            <h3 class="text-sm font-semibold text-white">Run history</h3>
            <p class="text-[10px] text-neutral-500">{historyRuns.length} persisted run(s) in {inputOutput}</p>
          </div>
          <button type="button" onclick={() => (historyOpen = false)} class="rounded px-2 text-neutral-500 hover:text-neutral-200" aria-label="Close history">×</button>
        </div>
        <div data-testid="run-history" class="min-h-0 flex-1 overflow-y-auto p-3">
          {#if historyRuns.length === 0}
            <p class="p-4 text-xs text-neutral-500">No runs recorded for this output yet.</p>
          {:else}
            <div class="space-y-2">
              {#each [...historyRuns].reverse() as record}
                <div class="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-neutral-800 bg-neutral-900/60 px-3 py-2">
                  <div class="min-w-0">
                    <p class="truncate text-xs text-neutral-200">{record.recipe_id || "recipe"}</p>
                    <p class="font-mono text-[10px] text-neutral-500">{record.job_id.slice(0, 8)} · {new Date(record.created_at).toLocaleString()} · {(record.duration_ms / 1000).toFixed(1)}s</p>
                  </div>
                  <div class="flex items-center gap-2">
                    <span class={`rounded px-2 py-0.5 text-[10px] ${record.status === "succeeded" ? "bg-emerald-500/10 text-emerald-300" : "bg-rose-500/10 text-rose-300"}`}>{record.status}</span>
                    <button type="button" onclick={() => compareRecord(record)} class="rounded border border-sky-500/40 px-2 py-1 text-[10px] text-sky-300 hover:bg-sky-500/10">Compare</button>
                  </div>
                </div>
              {/each}
            </div>
          {/if}
        </div>
      </div>
    </div>
  {/if}

  {#if compareOpen && comparison}
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4"
      role="presentation"
      onclick={(event) => {
        if (event.currentTarget === event.target) compareOpen = false;
      }}
    >
      <div class="flex max-h-[88vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-neutral-700 bg-neutral-950 shadow-2xl" role="dialog" aria-modal="true" aria-label="Run comparison">
        <div class="flex items-start justify-between gap-3 border-b border-neutral-800 px-5 py-3">
          <div>
            <h3 class="text-sm font-semibold text-white">Run comparison</h3>
            <p class="mt-1 text-[11px] text-neutral-500">Same output and recipe; current run versus the previous successful run.</p>
          </div>
          <button type="button" onclick={() => (compareOpen = false)} class="rounded px-2 text-neutral-500 hover:text-neutral-200" aria-label="Close comparison">×</button>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto p-5">
          <div class="grid gap-3 sm:grid-cols-2">
            {#each [{ label: "Current", run: comparison.current }, { label: "Previous", run: comparison.previous }] as item}
              <div class="rounded-xl border border-neutral-800 bg-neutral-900/50 p-3">
                <p class="text-[10px] uppercase tracking-wide text-neutral-500">{item.label}</p>
                <p class="mt-1 font-mono text-[10px] text-neutral-400">{item.run.job_id}</p>
                <div class="mt-2 grid grid-cols-2 gap-2 text-[11px]">
                  <span class="text-neutral-500">Duration</span><span class="text-neutral-200">{runDuration(item.run)}</span>
                  <span class="text-neutral-500">Cached</span><span class="text-emerald-300">{cachedCount(item.run)}</span>
                  <span class="text-neutral-500">Executed</span><span class="text-sky-300">{executedCount(item.run)}</span>
                  <span class="text-neutral-500">Warnings</span><span class="text-amber-300">{item.run.result?.warnings?.length ?? 0}</span>
                </div>
              </div>
            {/each}
          </div>
          <div class="mt-4 overflow-hidden rounded-xl border border-neutral-800">
            <table class="w-full text-left text-[11px]">
              <thead class="bg-neutral-900 text-[9px] uppercase tracking-wide text-neutral-500">
                <tr>
                  <th class="px-3 py-2">Step</th>
                  <th class="px-3 py-2">Previous</th>
                  <th class="px-3 py-2">Current</th>
                  <th class="px-3 py-2 text-right">Prev ms</th>
                  <th class="px-3 py-2 text-right">Now ms</th>
                </tr>
              </thead>
              <tbody>
                {#each comparison.steps as step}
                  <tr class="border-t border-neutral-800">
                    <td class="px-3 py-2">
                      <span class="block text-neutral-200">{step.id}</span>
                      <span class="font-mono text-[9px] text-neutral-600">{step.type}</span>
                    </td>
                    <td class="px-3 py-2 text-neutral-400">{step.previousStatus}</td>
                    <td class="px-3 py-2">
                      <span class={step.currentStatus === "cached" ? "text-emerald-300" : "text-sky-300"}>{step.currentStatus}</span>
                    </td>
                    <td class="px-3 py-2 text-right font-mono text-neutral-500">{step.previousMs}</td>
                    <td class="px-3 py-2 text-right font-mono text-neutral-300">{step.currentMs}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  {/if}

  {#if batchOpen}
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4"
      role="presentation"
      onclick={(event) => {
        if (event.currentTarget === event.target) batchOpen = false;
      }}
    >
      <div class="flex max-h-[88vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-neutral-700 bg-neutral-950 shadow-2xl" role="dialog" aria-modal="true" aria-label="Folder batch">
        <div class="flex items-start justify-between gap-3 border-b border-neutral-800 px-5 py-3">
          <div>
            <h3 class="text-sm font-semibold text-white">Folder batch</h3>
            <p class="mt-1 text-[11px] text-neutral-500">Run this recipe over every matching media file, one at a time.</p>
          </div>
          <button type="button" onclick={() => (batchOpen = false)} class="rounded px-2 text-neutral-500 hover:text-neutral-200" aria-label="Close batch">×</button>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto p-5">
          <div class="grid gap-3 sm:grid-cols-2">
            <label class="block text-[10px] uppercase tracking-wide text-neutral-500">
              Input folder
              <span class="mt-1 flex gap-1">
                <input bind:value={batchSourceDir} placeholder="/media/inbox" class="min-w-0 flex-1 rounded-lg border border-neutral-700 bg-neutral-900 px-2 py-1.5 font-mono text-[11px] text-neutral-200" />
                <button type="button" onclick={() => (picker = "batch-source")} class="rounded-lg border border-neutral-700 px-2 text-[11px] text-neutral-300">…</button>
              </span>
            </label>
            <label class="block text-[10px] uppercase tracking-wide text-neutral-500">
              Output root
              <span class="mt-1 flex gap-1">
                <input bind:value={batchOutputRoot} placeholder="/media/out" class="min-w-0 flex-1 rounded-lg border border-neutral-700 bg-neutral-900 px-2 py-1.5 font-mono text-[11px] text-neutral-200" />
                <button type="button" onclick={() => (picker = "batch-output")} class="rounded-lg border border-neutral-700 px-2 text-[11px] text-neutral-300">…</button>
              </span>
            </label>
            <label class="block text-[10px] text-neutral-500">
              Extensions
              <input bind:value={batchExtensions} placeholder=".mp4,.mov (empty = defaults)" class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-900 px-2 py-1.5 font-mono text-[10px] text-neutral-200" />
            </label>
            <label class="flex items-end gap-2 pb-1 text-[11px] text-neutral-300">
              <input type="checkbox" bind:checked={batchRecursive} class="h-4 w-4 rounded border-neutral-700 bg-neutral-900" />
              Include subfolders
            </label>
          </div>
          <div class="mt-3 flex flex-wrap items-center justify-between gap-2">
            <p class="text-[10px] text-neutral-500">Each file gets its own output folder and reuses the same recipe checkpoints.</p>
            <div class="flex gap-2">
              {#if batch && ["queued", "running"].includes(batch.status)}
                <button type="button" onclick={() => void stopBatch()} class="rounded-lg border border-rose-500/40 px-3 py-1.5 text-xs text-rose-200">Cancel batch</button>
              {/if}
              {#if batch && ["failed", "cancelled"].includes(batch.status)}
                <button type="button" onclick={() => void resumeCurrentBatch()} class="rounded-lg border border-sky-500/40 px-3 py-1.5 text-xs text-sky-200">Resume batch</button>
              {/if}
              <button type="button" onclick={() => void startBatch()} disabled={batchBusy} class="rounded-lg bg-sky-500 px-3 py-1.5 text-xs font-medium text-neutral-950 hover:bg-sky-400 disabled:opacity-50">
                {batchBusy ? "Starting…" : "Start batch"}
              </button>
            </div>
          </div>

          {#if batch}
            <div class="mt-5 rounded-xl border border-neutral-800 bg-neutral-900/50 p-3">
              <div class="flex flex-wrap items-center justify-between gap-2">
                <div>
                  <p class="font-mono text-[10px] text-neutral-500">{batch.batch_id}</p>
                  <p class="mt-1 text-xs text-neutral-300">{batch.message}</p>
                </div>
                <span class="rounded-full border border-neutral-700 px-2.5 py-1 text-[10px] uppercase text-neutral-300">{batch.status}</span>
              </div>
              <div class="mt-3 h-2 overflow-hidden rounded-full bg-neutral-800">
                <div class="h-full rounded-full bg-sky-400 transition-all" style={`width: ${batch.total ? (batch.completed / batch.total) * 100 : 0}%`}></div>
              </div>
              <p class="mt-1 text-[10px] text-neutral-500">{batch.completed}/{batch.total} processed · {batch.failed} failed</p>
              <div class="mt-3 max-h-64 space-y-1 overflow-y-auto">
                {#each batch.items as item}
                  <div class="flex items-center gap-2 rounded-lg border border-neutral-800 bg-neutral-950/60 px-2 py-1.5 text-[10px]">
                    <span class={`h-1.5 w-1.5 shrink-0 rounded-full ${
                      item.status === "succeeded" ? "bg-emerald-400" : item.status === "failed" ? "bg-rose-400" : item.status === "running" ? "animate-pulse bg-amber-400" : "bg-neutral-600"
                    }`}></span>
                    <span class="min-w-0 flex-1 truncate font-mono text-neutral-300">{item.source}</span>
                    <span class="shrink-0 text-neutral-500">{item.status}</span>
                  </div>
                {/each}
              </div>
            </div>
          {/if}

          {#if batchHistory.length}
            <div class="mt-4 rounded-xl border border-neutral-800 bg-neutral-900/40 p-3">
              <p class="text-[10px] uppercase tracking-wide text-neutral-500">Persisted batches</p>
              <div class="mt-2 max-h-40 space-y-1 overflow-y-auto">
                {#each batchHistory as entry}
                  <button type="button" onclick={() => void loadBatch(entry.batch_id)} class="flex w-full items-center justify-between gap-2 rounded-lg border border-neutral-800 bg-neutral-950/60 px-2 py-1.5 text-left text-[10px] hover:border-sky-500">
                    <span class="min-w-0 truncate font-mono text-neutral-400">{entry.batch_id.slice(0, 8)} · {entry.recipe_id}</span>
                    <span class="text-neutral-500">{entry.status} · {entry.completed}/{entry.total}</span>
                  </button>
                {/each}
              </div>
            </div>
          {/if}
        </div>
      </div>
    </div>
  {/if}

  {#if configOpen}
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4"
      role="presentation"
      onclick={(event) => {
        if (event.currentTarget === event.target) configOpen = false;
      }}
    >
      <div class="max-h-[86vh] w-full max-w-2xl overflow-y-auto rounded-2xl border border-neutral-700 bg-neutral-950 p-5 shadow-2xl" role="dialog" aria-modal="true" aria-label="Recipe settings">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h3 class="text-sm font-semibold text-white">Recipe settings</h3>
            <p class="mt-1 text-[11px] text-neutral-500">Identity and optional LLM router. Secrets stay in environment variables.</p>
          </div>
          <button type="button" onclick={() => (configOpen = false)} class="rounded px-2 text-neutral-500 hover:text-neutral-200" aria-label="Close settings">×</button>
        </div>
        <div class="mt-4 grid gap-3 sm:grid-cols-2">
          <label class="block text-[10px] text-neutral-500">
            Recipe ID
            <input bind:value={recipeId} class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-900 px-2 py-1.5 font-mono text-[11px] text-neutral-200" />
          </label>
          <label class="block text-[10px] text-neutral-500">
            Name
            <input bind:value={recipeName} class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-900 px-2 py-1.5 text-[11px] text-neutral-200" />
          </label>
          <label class="block text-[10px] text-neutral-500 sm:col-span-2">
            Description
            <textarea bind:value={recipeDescription} rows="2" class="mt-1 w-full resize-y rounded-lg border border-neutral-700 bg-neutral-900 px-2 py-1.5 text-[11px] text-neutral-200"></textarea>
          </label>
          <label class="block text-[10px] text-neutral-500">
            LLM provider
            <select bind:value={llm.provider} class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-900 px-2 py-1.5 text-[11px] text-neutral-200">
              <option value="none">None (local-only)</option>
              <option value="openai_compatible">OpenAI-compatible</option>
              <option value="opencode">OpenCode CLI (opt-in)</option>
            </select>
          </label>
          <label class="block text-[10px] text-neutral-500">
            Model
            <input bind:value={llm.model} placeholder="qwen2.5:7b-instruct" class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-900 px-2 py-1.5 text-[11px] text-neutral-200" />
          </label>
          <label class="flex items-center gap-2 text-[11px] text-neutral-300 sm:col-span-2">
            <input type="checkbox" bind:checked={resume} class="h-4 w-4 rounded border-neutral-700 bg-neutral-900" />
            Reuse existing step checkpoints when the fingerprint matches
          </label>
          {#if llm.provider !== "none"}
            <label class="block text-[10px] text-neutral-500 sm:col-span-2">
              Base URL
              <input bind:value={llm.base_url} placeholder="http://localhost:11434/v1" class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-900 px-2 py-1.5 font-mono text-[10px] text-neutral-200" />
            </label>
            <label class="block text-[10px] text-neutral-500">
              API key env var
              <input bind:value={llm.api_key_env} class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-900 px-2 py-1.5 font-mono text-[10px] text-neutral-200" />
            </label>
            <label class="block text-[10px] text-neutral-500">
              Timeout (s)
              <input type="number" bind:value={llm.timeout_seconds} min="1" max="600" class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-900 px-2 py-1.5 text-[11px] text-neutral-200" />
            </label>
          {/if}
        </div>
        <div class="mt-4 flex justify-end">
          <button type="button" onclick={() => (configOpen = false)} class="rounded-lg bg-sky-500 px-3 py-1.5 text-xs font-medium text-neutral-950 hover:bg-sky-400">Done</button>
        </div>
      </div>
    </div>
  {/if}

  {#if jsonModal}
    <div
      class="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-2 sm:p-4"
      role="presentation"
      onclick={(event) => {
        if (event.currentTarget === event.target) jsonModal = null;
      }}
    >
      <div class="flex h-[88vh] w-[min(1100px,96vw)] flex-col overflow-hidden rounded-2xl border border-neutral-700 bg-neutral-950 shadow-2xl" role="dialog" aria-modal="true" aria-label="JSON editor">
        <div class="flex items-center justify-between gap-3 border-b border-neutral-800 px-4 py-3">
          <div>
            <h3 class="text-sm font-semibold text-white">{jsonModal === "recipe" ? "Recipe JSON" : "Step parameters"}</h3>
            <p class="mt-0.5 text-[10px] text-neutral-500">
              {jsonModal === "recipe" ? "Edit the full DAG, then apply it to the canvas." : `Editing ${selectedId ?? "selected step"}.`}
            </p>
          </div>
          <button type="button" onclick={() => (jsonModal = null)} class="rounded px-2 text-neutral-500 hover:text-neutral-200" aria-label="Close JSON editor">×</button>
        </div>
        <div class="flex min-h-0 flex-1 flex-col p-3">
          {#if jsonModal === "recipe"}
            <textarea
              bind:value={recipeJsonText}
              spellcheck="false"
              class="min-h-0 flex-1 resize-none rounded-xl border border-neutral-700 bg-neutral-950 p-3 font-mono text-xs leading-5 text-neutral-200"
            ></textarea>
          {:else}
            <textarea
              value={paramText}
              oninput={(event) => updateParams(event.currentTarget.value)}
              spellcheck="false"
              class="min-h-0 flex-1 resize-none rounded-xl border border-neutral-700 bg-neutral-950 p-3 font-mono text-xs leading-5 text-neutral-200"
            ></textarea>
          {/if}
          {#if jsonError}<p class="mt-2 text-[11px] text-rose-300">{jsonError}</p>{/if}
        </div>
        <div class="flex items-center justify-between gap-2 border-t border-neutral-800 px-4 py-3">
          <p class="text-[10px] text-neutral-500">Apply updates the canvas locally. Run Validate to check the DAG on the server.</p>
          <div class="flex gap-2">
            <button type="button" onclick={() => (jsonModal = null)} class="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300">Cancel</button>
            <button type="button" onclick={applyJson} class="rounded-lg bg-sky-500 px-3 py-1.5 text-xs font-medium text-neutral-950 hover:bg-sky-400">Apply</button>
          </div>
        </div>
      </div>
    </div>
  {/if}

  {#if picker}
    <PathPicker
      open={true}
      mode={picker === "node-path" ? nodePathMode : picker === "source" || picker === "second-source" ? "file" : "directory"}
      title={
        picker === "source"
          ? "Choose source video"
          : picker === "second-source"
            ? "Choose second split-screen source"
          : picker === "node-path"
            ? "Choose step field path"
          : picker === "output"
            ? "Choose output directory"
            : picker === "batch-source"
              ? "Choose batch input folder"
              : picker === "broll"
                ? "Choose local B-roll asset folder"
                : "Choose batch output root"
      }
      initialPath={
        picker === "source"
          ? inputSource
          : picker === "second-source"
            ? paramString("second_source_path")
          : picker === "node-path"
            ? ""
          : picker === "output"
            ? inputOutput
            : picker === "batch-source"
              ? batchSourceDir
              : picker === "broll"
                ? paramString("asset_dir")
                : batchOutputRoot
      }
      onclose={() => (picker = null)}
      onselect={(path) => choose(path)}
    />
  {/if}
</div>
