<script lang="ts">
  import HelpTip from "$lib/HelpTip.svelte";
  import ErrorBanner from "$lib/ErrorBanner.svelte";
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
  import NodeInspector from "$lib/nodes/NodeInspector.svelte";
  import Modal from "$lib/ui/Modal.svelte";
  import Button from "$lib/ui/Button.svelte";
  import Icon from "$lib/ui/Icon.svelte";
  import IconButton from "$lib/ui/IconButton.svelte";
  import { stepIcon } from "$lib/ui/icons";
  import StepNode from "$lib/nodes/StepNode.svelte";
  import { setPath, validateParams } from "$lib/recipeFields";
  import PathPicker from "$lib/PathPicker.svelte";
  import { recipesFor, type RecipeFilter } from "$lib/recipeLibrary";
  import {
    dryRunRecipe,
    errorMessage,
    getJob,
    getLogs,
    getNodeOptions,
    getRecipe,
    getRecipeHistory,
    getRecipeVersion,
    jobArtifactUrl,
    shortFileUrl,
    getRunHistory,
    listJobs,
    listNodePresets,
    listRecipes,
    listRecipeSteps,
    cancelBatch,
    createJobPreview,
    createNodePreset,
    deleteNodePreset,
    favoriteNodePreset,
    getBatch,
    listBatches,
    resumeBatch,
    runBatch,
    resumeJob,
    runRecipe,
    runRecipeStep,
    restoreRecipeVersion,
    saveRecipe,
    setRecipeFavorite,
    updateNodePreset,
    updateRecipeTags,
    validateExports,
    validateRecipe,
    type Batch,
    type Job,
    type Recipe,
    type NleValidationReport,
    type RecipeHistoryEntry,
    type RecipeSummary,
    type RunRecord,
    type NodeOptions,
    type NodePreset,
    type StepManifest,
    type StepPort
  } from "$lib/api";

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
    description?: string;
    params: Record<string, unknown>;
    schema?: Record<string, unknown>;
    implementation?: "available" | "partial" | "planned";
    dimmed?: boolean;
    icon?: string;
    color?: string;
    status?: NodeStatus;
    progress?: number;
    inputs?: Record<string, string>;
    inputPorts?: StepPort[];
    outputPorts?: StepPort[];
    mediaOverride?: string;
    outputMode?: "pipeline" | "folder";
    outputDir?: string;
    enabled?: boolean;
    onEnabledChange?: (enabled: boolean) => void;
    presets?: NodePreset[];
    options?: NodeOptions | null;
    onApplyPreset?: (preset: NodePreset) => void;
    onSavePreset?: (name: string) => void;
    onUpdatePreset?: (presetId: string) => void;
    onDeletePreset?: (presetId: string) => void;
    onFavoritePreset?: (presetId: string, favorite: boolean) => void;
    onRenamePreset?: (presetId: string, name: string) => void;
    onDuplicatePreset?: (presetId: string, name: string) => void;
    expanded?: boolean;
    pinned?: boolean;
    width?: number;
    onToggle?: () => void;
    onPin?: () => void;
    onPatch?: (path: string[], value: unknown) => void;
    onPickPath?: (path: string[]) => void;
    onStepPatch?: (key: "media_override" | "output_mode" | "output_dir", value: unknown) => void;
    onPickStepPath?: (key: "media_override" | "output_dir") => void;
    errors?: Record<string, string>;
    onRun?: () => void;
    onDuplicate?: () => void;
    onRemove?: () => void;
    onOpenJson?: () => void;
  };

  const nodeTypes = { step: StepNode };
  let steps = $state<StepManifest[]>([]);
  let recipes = $state<RecipeSummary[]>([]);
  let nodePresets = $state<NodePreset[]>([]);
  let nodeOptions = $state<NodeOptions | null>(null);
  let nodes = $state<Node[]>([]);
  let edges = $state<Edge[]>([]);
  let selectedId = $state<string | null>(null);
  let selectedNodeIds = $state<string[]>([]);
  let copiedNodeIds = $state<string[]>([]);
  let nodeQuery = $state("");
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
  let canvasEl: HTMLDivElement | null = $state(null);
  let hasSavedViewport = $state(false);
  let undoStack = $state<Recipe[]>([]);
  let redoStack = $state<Recipe[]>([]);
  let dirty = $state(false);
  let lastUndoKey = "";
  let lastUndoAt = 0;
  let uiSaveTimer: ReturnType<typeof setTimeout> | undefined;
  let nodePathTarget = $state<{
    nodeId: string;
    path: string[];
    scope?: "params" | "step";
  } | null>(null);
  let nodePathMode = $state<"file" | "directory">("file");
  let llm = $state<Recipe["llm"]>({
    provider: "none",
    base_url: null,
    model: "",
    api_key_env: "VIDEOWFLOW_LLM_API_KEY",
    timeout_seconds: 90
  });
  let inputOutput = $state("");
  let workspaceOpen = $state(false);
  let workspaceDraft = $state("");
  let workspaceAction = $state<"nle" | "history" | null>(null);
  let picker = $state<
    | "workspace"
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
  let moreOpen = $state(false);
  let tourOpen = $state(false);
  let tourStep = $state(0);
  let configOpen = $state(false);
  let jsonModal = $state<"step" | "recipe" | null>(null);
  let recipeJsonText = $state("");
  let recipeVariables = $state<
    Record<
      string,
      {
        type: "string" | "number" | "boolean" | "enum";
        default?: unknown;
        description?: string;
        options?: unknown[];
        required?: boolean;
      }
    >
  >({});
  let recipeProfiles = $state<Record<string, Record<string, unknown>>>({});
  let recipeVariants = $state<Array<Record<string, unknown>>>([]);
  let variableValues = $state<Record<string, unknown>>({});
  let recipeProfile = $state("");
  let gateComment = $state("");
  let gateBusy = $state(false);
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
  let recipeHistoryOpen = $state(false);
  let recipeHistory = $state<RecipeHistoryEntry[]>([]);
  let recipeHistoryError = $state("");
  let versionDiffOpen = $state(false);
  let versionDiffLines = $state<string[]>([]);
  let versionDiffBusy = $state(false);
  let versionDiffError = $state("");
  let templatesOpen = $state(false);
  let templateQuery = $state("");
  let recipeFilter = $state<RecipeFilter>("all");
  let wiring = $state<{
    source: string;
    target: string;
    sourcePort: string;
    targetPort: string;
  } | null>(null);
  let nleOpen = $state(false);
  let nleReport = $state<NleValidationReport | null>(null);
  let nleBusy = $state(false);
  let nleError = $state("");
  let proxyUrl = $state("");
  let proxyBusy = $state(false);
  let proxyError = $state("");
  let logOpen = $state(false);
  let logStep = $state("");
  let logLines = $state<Awaited<ReturnType<typeof getLogs>>>([]);
  let logBusy = $state(false);
  let logError = $state("");
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

  const visibleRecipes = $derived(
    recipesFor(recipes, recipeFilter, templateQuery)
  );
  const currentRecipe = $derived(
    recipes.find((recipe) => recipe.id === recipeId)
  );
  const favoriteCount = $derived(recipes.filter((recipe) => recipe.favorite).length);

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

  $effect(() => {
    const handler = (event: BeforeUnloadEvent) => {
      if (!dirty) return;
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", handler);
    return () => window.removeEventListener("beforeunload", handler);
  });

  onMount(() => {
    const onBuilderAction = (event: Event) => {
      const detail = (event as CustomEvent<unknown>).detail;
      if (detail && typeof detail === "object") {
        const payload = detail as { action?: string; path?: string };
        if (payload.action === "load-timeline" && payload.path) {
          addStep("timeline.load", { path: payload.path });
          return;
        }
      }
      const action = String(detail ?? "");
      if (action === "add-step") {
        addOpen = true;
        inspectorOpen = false;
      } else if (action === "run") {
        void execute();
      } else if (action === "dry-run") {
        void dryRun();
      } else if (action === "save") {
        void save();
      } else if (action === "validate") {
        void validate();
      } else if (action === "inspector") {
        toggleInspector();
      } else if (action === "auto-layout") {
        resetLayout();
      } else if (action === "json") {
        openRecipeJson();
      } else if (action === "runs") {
        void openHistory();
      }
    };
    window.addEventListener("videoflow:builder-action", onBuilderAction);
    const onBuilderKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing = target
        ? ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable
        : false;
      const modifier = event.ctrlKey || event.metaKey;
      if (modifier && event.key.toLowerCase() === "s") {
        event.preventDefault();
        void save();
        return;
      }
      if (modifier && event.key === "Enter") {
        event.preventDefault();
        void execute();
        return;
      }
      if (!typing && modifier && event.key.toLowerCase() === "c") {
        event.preventDefault();
        copySelectedNodes();
        return;
      }
      if (!typing && modifier && event.key.toLowerCase() === "v") {
        event.preventDefault();
        pasteNodes();
        return;
      }
      if (!typing && !modifier && event.key === "Delete" && (selectedId || selectedNodeIds.length)) {
        event.preventDefault();
        removeSelectedNodes();
      }
    };
    window.addEventListener("keydown", onBuilderKey);
    void (async () => {
      try {
        steps = await listRecipeSteps();
        recipes = await listRecipes();
        nodePresets = await listNodePresets();
        nodeOptions = await getNodeOptions();
        const first = recipes[0];
        if (first) await loadRecipe(first.id);
      } catch (reason) {
        error = errorMessage(reason);
      }
    })();
    return () => {
      window.removeEventListener("videoflow:builder-action", onBuilderAction);
      window.removeEventListener("keydown", onBuilderKey);
    };
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
    recipeVariables = recipe.variables ?? {};
    recipeProfiles = recipe.profiles ?? {};
    recipeVariants = recipe.variants ?? [];
    variableValues = Object.fromEntries(
      Object.entries(recipeVariables).map(([key, spec]) => [key, spec.default ?? ""])
    );
    recipeProfile = "";
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
        x: saved?.x ?? 60 + column * 460,
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
          description: manifest?.description ?? "",
          params: step.params,
          schema: manifest?.params_schema ?? {},
          enabled: step.enabled !== false,
          onEnabledChange: (enabled: boolean) => patchStepEnabled(step.id, enabled),
          inputs: step.inputs ?? {},
          inputPorts: manifest?.inputs ?? [],
          outputPorts: manifest?.outputs ?? [],
          presets: nodePresets.filter((preset) => preset.step_type === step.type),
          options: nodeOptions,
          onApplyPreset: (preset: NodePreset) => {
            const node = nodes.find((item) => item.id === step.id);
            if (node) patchNodeParamsMany(step.id, preset.params);
          },
          onSavePreset: (name: string) => void saveNodePreset(step.id, step.type, name),
          onUpdatePreset: (id: string) => void updateNodePresetFromNode(step.id, id),
          onDeletePreset: (id: string) => void removeNodePreset(id),
          onFavoritePreset: (id: string, favorite: boolean) =>
            void favoritePreset(id, favorite),
          onRenamePreset: (id: string, name: string) => void renameNodePreset(id, name),
          onDuplicatePreset: (id: string, name: string) => void duplicateNodePreset(id, name),
          mediaOverride: step.media_override ?? "",
          outputMode: step.output_mode ?? "pipeline",
          outputDir: step.output_dir ?? "",
          onStepPatch: (key: "media_override" | "output_mode" | "output_dir", value: unknown) => patchStepField(step.id, key, value),
          onPickStepPath: (key: "media_override" | "output_dir") => openStepPathPicker(step.id, key),
          implementation: manifest?.status ?? "available",
          icon: manifest?.icon ?? "●",
          color: manifest?.color ?? "#38bdf8",
          status: "idle",
          progress: 0,
          expanded: recipeUi.nodes[step.id].expanded,
          pinned: recipeUi.nodes[step.id].pinned,
          width: recipeUi.nodes[step.id].width,
          onSelect: () => selectNode(step.id),
          onToggle: () => toggleNodeExpanded(step.id),
          onPin: () => toggleNodePinned(step.id),
          onWidth: () => cycleNodeWidth(step.id),
          onResize: (width: number) => resizeNode(step.id, width),
          onPatch: (path: string[], value: unknown) => patchNodeParams(step.id, path, value),
          onPatchMany: (patch: Record<string, unknown>) => patchNodeParamsMany(step.id, patch),
          onPickPath: (path: string[]) => openNodePathPicker(step.id, path),
          onRun: () => void runToHere(step.id),
          onDuplicate: () => duplicateNode(step.id),
          onRemove: () => removeNode(step.id),
          onLogs: () => void openStepLogs(step.id),
          onOpenJson: () => {
            selectedId = step.id;
            openStepJson();
          }
        }
      } satisfies Node;
    });
    nodes = next;
    edges = recipe.steps.flatMap((step) =>
      step.needs.map((need) => {
        const mappings = Object.entries(step.inputs ?? {})
          .filter(([, reference]) => String(reference).split(".")[0] === need)
          .map(([inputPort, reference]) => `${String(reference).split(".").slice(1).join(".")} → ${inputPort}`);
        return {
          id: `${need}->${step.id}`,
          source: need,
          target: step.id,
          animated: true,
          label: mappings.join(" · ")
        };
      })
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
      variables: recipeVariables,
      profiles: recipeProfiles,
      variants: recipeVariants,
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
        const sources = new Set(
          edges.filter((edge) => edge.target === node.id).map((edge) => edge.source)
        );
        const inputs = Object.fromEntries(
          Object.entries(data.inputs ?? {}).filter(([, reference]) =>
            sources.has(String(reference).split(".")[0])
          )
        );
        return {
          id: node.id,
          type: data.type,
          needs: [...sources],
          inputs,
          media_override: data.mediaOverride ?? "",
          output_mode: data.outputMode ?? "pipeline",
          output_dir: data.outputDir ?? "",
          enabled: data.enabled !== false,
          params: data.params ?? {}
        };
      })
    };
  }

  function addStep(type: string, initialParams: Record<string, unknown> = {}) {
    const manifest = manifestFor(type);
    if (!manifest) return;
    pushUndo();
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
        position: { x: 80 + (nodes.length % 4) * 460, y: 100 + Math.floor(nodes.length / 4) * 180 },
        data: {
          title: manifest.title,
          type,
          description: manifest.description,
          params: { ...defaultsFor(manifest), ...initialParams },
          schema: manifest.params_schema,
          enabled: true,
          onEnabledChange: (enabled: boolean) => patchStepEnabled(id, enabled),
          inputs: {},
          inputPorts: manifest.inputs ?? [],
          outputPorts: manifest.outputs ?? [],
          presets: nodePresets.filter((preset) => preset.step_type === type),
          options: nodeOptions,
          onApplyPreset: (preset: NodePreset) => void patchNodeParamsMany(id, preset.params),
          onSavePreset: (name: string) => void saveNodePreset(id, type, name),
          onUpdatePreset: (presetId: string) => void updateNodePresetFromNode(id, presetId),
          onDeletePreset: (presetId: string) => void removeNodePreset(presetId),
          onFavoritePreset: (presetId: string, favorite: boolean) =>
            void favoritePreset(presetId, favorite),
          onRenamePreset: (presetId: string, name: string) => void renameNodePreset(presetId, name),
          onDuplicatePreset: (presetId: string, name: string) => void duplicateNodePreset(presetId, name),
          mediaOverride: "",
          outputMode: "pipeline",
          outputDir: "",
          onStepPatch: (key: "media_override" | "output_mode" | "output_dir", value: unknown) => patchStepField(id, key, value),
          onPickStepPath: (key: "media_override" | "output_dir") => openStepPathPicker(id, key),
          implementation: manifest.status ?? "available",
          icon: manifest.icon ?? "●",
          color: manifest.color ?? "#38bdf8",
          status: "idle",
          progress: 0,
          expanded: true,
          pinned: false,
          width: 420,
          onSelect: () => selectNode(id),
          onToggle: () => toggleNodeExpanded(id),
          onPin: () => toggleNodePinned(id),
          onWidth: () => cycleNodeWidth(id),
          onResize: (width: number) => resizeNode(id, width),
          onPatch: (path: string[], value: unknown) => patchNodeParams(id, path, value),
          onPatchMany: (patch: Record<string, unknown>) => patchNodeParamsMany(id, patch),
          onPickPath: (path: string[]) => openNodePathPicker(id, path),
          onRun: () => void runToHere(id),
          onDuplicate: () => duplicateNode(id),
          onRemove: () => removeNode(id),
          onLogs: () => void openStepLogs(id),
          onOpenJson: () => {
            selectedId = id;
            openStepJson();
          }
        }
      } satisfies Node
    ];
    recipeUi.nodes[id] = {
      x: 80 + (nodes.length % 4) * 460,
      y: 100 + Math.floor(nodes.length / 4) * 180,
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

  function alignSelected(axis: "x" | "y") {
    const chosen = nodes.filter((node) => selectedNodeIds.includes(node.id));
    if (chosen.length < 2) return;
    pushUndo();
    const target = Math.min(
      ...chosen.map((node) => (axis === "x" ? node.position.x : node.position.y))
    );
    nodes = nodes.map((node) =>
      selectedNodeIds.includes(node.id)
        ? { ...node, position: { ...node.position, [axis]: target } }
        : node
    );
    for (const node of nodes) {
      if (!selectedNodeIds.includes(node.id)) continue;
      recipeUi.nodes[node.id] = {
        ...(recipeUi.nodes[node.id] ?? {
          expanded: true,
          pinned: false,
          width: 420
        }),
        x: node.position.x,
        y: node.position.y
      };
    }
    scheduleUiSave();
  }

  function removeSelectedNodes() {
    const ids = selectedNodeIds.length
      ? selectedNodeIds
      : selectedId
        ? [selectedId]
        : [];
    if (!ids.length) return;
    pushUndo();
    nodes = nodes.filter((node) => !ids.includes(node.id));
    edges = edges.filter(
      (edge) => !ids.includes(edge.source) && !ids.includes(edge.target)
    );
    for (const id of ids) delete recipeUi.nodes[id];
    if (selectedId && ids.includes(selectedId)) {
      selectedId = null;
      paramText = "{}";
    }
    selectedNodeIds = [];
    scheduleUiSave();
  }

  function fitSelectedNodes() {
    const chosen = nodes.filter((node) => selectedNodeIds.includes(node.id));
    if (!chosen.length || !canvasEl) return;
    const pad = 70;
    const minX = Math.min(...chosen.map((node) => node.position.x));
    const minY = Math.min(...chosen.map((node) => node.position.y));
    const maxX = Math.max(
      ...chosen.map((node) => node.position.x + (nodeData(node).width ?? 420))
    );
    const maxY = Math.max(
      ...chosen.map(
        (node) => node.position.y + (nodeData(node).expanded ? 640 : 170)
      )
    );
    const rect = canvasEl.getBoundingClientRect();
    const zoom = Math.min(
      1.6,
      Math.max(
        0.2,
        Math.min(
          (rect.width - pad * 2) / Math.max(1, maxX - minX),
          (rect.height - pad * 2) / Math.max(1, maxY - minY)
        )
      )
    );
    viewport = {
      x: pad - minX * zoom,
      y: pad - minY * zoom,
      zoom
    };
    scheduleUiSave();
  }

  function copySelectedNodes() {
    const ids = selectedNodeIds.length
      ? selectedNodeIds
      : selectedId
        ? [selectedId]
        : [];
    copiedNodeIds = ids.filter((id) => nodes.some((node) => node.id === id));
    if (copiedNodeIds.length) layoutStatus = `${copiedNodeIds.length} copied`;
  }

  function pasteNodes() {
    if (!copiedNodeIds.length) return;
    const ids = copiedNodeIds.filter((id) => nodes.some((node) => node.id === id));
    for (const id of ids) duplicateNode(id);
  }

  function filterNodes(value: string) {
    nodeQuery = value;
    const needle = value.trim().toLowerCase();
    const dimmed = new Set<string>();
    nodes = nodes.map((node) => {
      const data = nodeData(node);
      const hit =
        !needle ||
        `${node.id} ${data.title} ${data.type}`.toLowerCase().includes(needle);
      if (!hit) dimmed.add(node.id);
      return { ...node, data: { ...data, dimmed: !hit } };
    });
    edges = edges.map((edge) => ({
      ...edge,
      style:
        needle && (dimmed.has(edge.source) || dimmed.has(edge.target))
          ? "opacity:0.12"
          : undefined
    }));
  }

  function removeConnection(source: string, target: string) {
    pushUndo();
    const targetNode = nodes.find((node) => node.id === target);
    if (!targetNode) return;
    const inputs = Object.fromEntries(
      Object.entries(nodeData(targetNode).inputs ?? {}).filter(
        ([, reference]) => String(reference).split(".")[0] !== source
      )
    );
    nodes = nodes.map((node) =>
      node.id === target
        ? { ...node, data: { ...nodeData(node), inputs } }
        : node
    );
    edges = edges.filter(
      (edge) => !(edge.source === source && edge.target === target)
    );
    wiring = null;
    scheduleUiSave();
  }

  function portTypeCompatible(source: string, target: string): boolean {
    return source === target || source === "any" || target === "any";
  }

  function wiringChoices(source: string, target: string) {
    const sourceNode = nodes.find((node) => node.id === source);
    const targetNode = nodes.find((node) => node.id === target);
    if (!sourceNode || !targetNode) return [];
    const outputs = nodeData(sourceNode).outputPorts ?? [];
    const inputs = nodeData(targetNode).inputPorts ?? [];
    return outputs.flatMap((output) =>
      inputs
        .filter((input) => portTypeCompatible(output.type, input.type))
        .map((input) => ({ output, input }))
    );
  }

  function edgeLabel(source: string, target: string): string {
    const targetNode = nodes.find((node) => node.id === target);
    if (!targetNode) return "";
    const entries = Object.entries(nodeData(targetNode).inputs ?? {}).filter(
      ([, reference]) => String(reference).split(".")[0] === source
    );
    return entries
      .map(([inputPort, reference]) => `${String(reference).split(".").slice(1).join(".")} → ${inputPort}`)
      .join(" · ");
  }

  function openWiring(source: string, target: string) {
    const sourceNode = nodes.find((node) => node.id === source);
    const targetNode = nodes.find((node) => node.id === target);
    if (!sourceNode || !targetNode) return;
    const outputs = nodeData(sourceNode).outputPorts ?? [];
    const inputs = nodeData(targetNode).inputPorts ?? [];
    if (!outputs.length || !inputs.length) {
      error = `No ports available between ${source} and ${target}.`;
      return;
    }
    const firstCompatible = wiringChoices(source, target)[0];
    wiring = {
      source,
      target,
      sourcePort: firstCompatible?.output.id ?? outputs[0].id,
      targetPort: firstCompatible?.input.id ?? inputs[0].id
    };
  }

  function openInspectorWiring(nodeId: string) {
    const node = nodes.find((item) => item.id === nodeId);
    if (!node) return;
    const input = (nodeData(node).inputPorts ?? [])[0];
    if (!input) return;
    const reference = String(nodeData(node).inputs?.[input.id] ?? "");
    const sourceId = reference.split(".")[0];
    if (sourceId) {
      openWiring(sourceId, nodeId);
      return;
    }
    const source = nodes.find(
      (candidate) =>
        candidate.id !== nodeId &&
        (nodeData(candidate).outputPorts ?? []).some((port) =>
          portTypeCompatible(port.type, input.type)
        )
    );
    if (source) openWiring(source.id, nodeId);
  }

  function openEdgeWiring(edge: Edge) {
    const targetNode = nodes.find((node) => node.id === edge.target);
    if (!targetNode) return;
    const entries = Object.entries(nodeData(targetNode).inputs ?? {}).filter(
      ([, reference]) => String(reference).split(".")[0] === edge.source
    );
    const [inputPort, reference] = entries[0] ?? [];
    if (inputPort && reference) {
      wiring = {
        source: edge.source,
        target: edge.target,
        sourcePort: String(reference).split(".").slice(1).join("."),
        targetPort: inputPort
      };
      return;
    }
    openWiring(edge.source, edge.target);
  }

  function confirmWiring() {
    if (!wiring) return;
    const { source, target, sourcePort, targetPort } = wiring;
    const sourceNode = nodes.find((node) => node.id === source);
    const targetNode = nodes.find((node) => node.id === target);
    if (!sourceNode || !targetNode) return;
    const output = (nodeData(sourceNode).outputPorts ?? []).find(
      (port) => port.id === sourcePort
    );
    const input = (nodeData(targetNode).inputPorts ?? []).find(
      (port) => port.id === targetPort
    );
    if (!output || !input || !portTypeCompatible(output.type, input.type)) {
      error = "Choose compatible port types before connecting.";
      return;
    }
    const reference = `${source}.${sourcePort}`;
    const exists = edges.some((edge) => edge.source === source && edge.target === target);
    pushUndo();
    const label = `${sourcePort} → ${targetPort}`;
    nodes = nodes.map((node) =>
      node.id === target
        ? {
            ...node,
            data: {
              ...nodeData(node),
              inputs: { ...(nodeData(node).inputs ?? {}), [targetPort]: reference }
            }
          }
        : node
    );
    if (!exists) {
      edges = [
        ...edges,
        {
          id: `${source}->${target}`,
          source,
          target,
          animated: true,
          label
        }
      ];
    } else {
      edges = edges.map((edge) =>
        edge.source === source && edge.target === target
          ? { ...edge, label }
          : edge
      );
    }
    wiring = null;
    scheduleUiSave();
  }

  function availableWiringOptions(targetId: string, inputId: string) {
    const targetNode = nodes.find((node) => node.id === targetId);
    if (!targetNode) return [];
    const inputPort = (nodeData(targetNode).inputPorts ?? []).find(
      (port) => port.id === inputId
    );
    if (!inputPort) return [];
    return nodes
      .filter((node) => node.id !== targetId)
      .flatMap((node) =>
        (nodeData(node).outputPorts ?? []).map((output) => ({
          value: `${node.id}.${output.id}`,
          label: `${node.id} · ${output.label} · ${output.type}`,
          compatible: portTypeCompatible(output.type, inputPort.type)
        }))
      );
  }

  function setNodeInput(targetId: string, inputId: string, reference: string) {
    const targetNode = nodes.find((node) => node.id === targetId);
    if (!targetNode) return;
    pushUndo();
    const previous = String(nodeData(targetNode).inputs?.[inputId] ?? "");
    const inputs = { ...(nodeData(targetNode).inputs ?? {}) };
    if (reference) inputs[inputId] = reference;
    else delete inputs[inputId];
    nodes = nodes.map((node) =>
      node.id === targetId
        ? { ...node, data: { ...nodeData(node), inputs } }
        : node
    );
    const oldSource = previous.split(".")[0];
    const stillUsesOld =
      oldSource &&
      Object.values(inputs).some((value) => String(value).split(".")[0] === oldSource);
    if (oldSource && !stillUsesOld) {
      edges = edges.filter(
        (edge) => !(edge.source === oldSource && edge.target === targetId)
      );
    }
    if (!reference) {
      scheduleUiSave();
      return;
    }
    const source = reference.split(".")[0];
    const sourcePort = reference.split(".").slice(1).join(".");
    const exists = edges.some(
      (edge) => edge.source === source && edge.target === targetId
    );
    if (!exists) {
      edges = [
        ...edges,
        {
          id: `${source}->${targetId}`,
          source,
          target: targetId,
          animated: true,
          label: `${sourcePort} → ${inputId}`
        }
      ];
    } else {
      edges = edges.map((edge) =>
        edge.source === source && edge.target === targetId
          ? { ...edge, label: `${sourcePort} → ${inputId}` }
          : edge
      );
    }
    scheduleUiSave();
  }

  function onConnect(connection: Connection) {
    if (!connection.source || !connection.target) return;
    if (connection.source === connection.target) return;
    const adjacency = new Map<string, string[]>();
    for (const edge of edges) {
      const list = adjacency.get(edge.source) ?? [];
      list.push(edge.target);
      adjacency.set(edge.source, list);
    }
    const reaches = (from: string, to: string): boolean => {
      if (from === to) return true;
      const stack = [from];
      const seen = new Set<string>();
      while (stack.length) {
        const current = stack.pop()!;
        if (seen.has(current)) continue;
        seen.add(current);
        if (current === to) return true;
        for (const next of adjacency.get(current) ?? []) stack.push(next);
      }
      return false;
    };
    if (reaches(connection.target, connection.source)) {
      error = "This connection would create a cycle.";
      return;
    }
    openWiring(connection.source, connection.target);
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

  async function openStepLogs(stepId: string) {
    if (!job) {
      error = "Run a recipe to inspect step logs.";
      return;
    }
    logStep = stepId;
    logOpen = true;
    logBusy = true;
    logError = "";
    try {
      logLines = await getLogs(job.job_id, stepId, undefined, 300);
    } catch (reason) {
      logError = errorMessage(reason);
      logLines = [];
    } finally {
      logBusy = false;
    }
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
      workspaceAction = "nle";
      workspaceDraft = job?.output ?? "";
      workspaceOpen = true;
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
      workspaceAction = "history";
      workspaceDraft = job?.output ?? "";
      workspaceOpen = true;
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
      pushCoalescedUndo(`${selectedId}:json`);
      nodes = nodes.map((node) =>
        node.id === selectedId
          ? { ...node, data: { ...nodeData(node), params: parsed } }
          : node
      );
      paramError = "";
      scheduleUiSave();
      return true;
    } catch (reason) {
      paramError = reason instanceof Error ? reason.message : String(reason);
      return false;
    }
  }

  function snapshotRecipe(): Recipe {
    return JSON.parse(JSON.stringify(recipeFromGraph())) as Recipe;
  }

  function pushUndo() {
    undoStack = [...undoStack.slice(-49), snapshotRecipe()];
    redoStack = [];
  }

  function pushCoalescedUndo(key: string) {
    const now = Date.now();
    if (key !== lastUndoKey || now - lastUndoAt > 1000) {
      pushUndo();
      lastUndoKey = key;
      lastUndoAt = now;
    }
  }

  function restoreRecipe(recipe: Recipe) {
    const keep = selectedId;
    graphFromRecipe(recipe);
    if (keep && recipe.steps.some((step) => step.id === keep)) {
      selectNode(keep);
    }
    scheduleUiSave();
  }

  function undo() {
    const previous = undoStack.at(-1);
    if (!previous) return;
    redoStack = [...redoStack, snapshotRecipe()];
    undoStack = undoStack.slice(0, -1);
    restoreRecipe(previous);
  }

  function redo() {
    const next = redoStack.at(-1);
    if (!next) return;
    undoStack = [...undoStack, snapshotRecipe()];
    redoStack = redoStack.slice(0, -1);
    restoreRecipe(next);
  }

  function resizeNode(id: string, width: number) {
    setNodeUi(id, { width });
    nodes = nodes.map((node) =>
      node.id === id
        ? { ...node, data: { ...nodeData(node), width } }
        : node
    );
    scheduleUiSave();
  }

  function scheduleUiSave() {
    clearTimeout(uiSaveTimer);
    dirty = true;
    layoutStatus = "saving…";
    uiSaveTimer = setTimeout(async () => {
      try {
        await saveRecipe(recipeFromGraph());
        recipes = await listRecipes();
        layoutStatus = "saved";
        dirty = false;
      } catch (reason) {
        layoutStatus = errorMessage(reason);
        dirty = true;
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
    pushCoalescedUndo(`${id}:${path.join(".")}`);
    const params = setPath({ ...(nodeData(node).params ?? {}) }, path, value);
    nodes = nodes.map((item) =>
      item.id === id
        ? { ...item, data: { ...nodeData(item), params } }
        : item
    );
    if (selectedId === id) {
      paramText = JSON.stringify(params, null, 2);
    }
    scheduleUiSave();
  }

  function patchNodeParamsMany(id: string, patch: Record<string, unknown>) {
    const node = nodes.find((item) => item.id === id);
    if (!node) return;
    pushUndo();
    const params = { ...(nodeData(node).params ?? {}), ...patch };
    nodes = nodes.map((item) =>
      item.id === id
        ? { ...item, data: { ...nodeData(item), params } }
        : item
    );
    if (selectedId === id) {
      paramText = JSON.stringify(params, null, 2);
    }
    scheduleUiSave();
  }

  function patchStepEnabled(id: string, enabled: boolean) {
    pushUndo();
    nodes = nodes.map((node) =>
      node.id === id
        ? { ...node, data: { ...nodeData(node), enabled } }
        : node
    );
    scheduleUiSave();
  }

  function patchStepField(
    id: string,
    key: "media_override" | "output_mode" | "output_dir",
    value: unknown
  ) {
    pushCoalescedUndo(`${id}:${key}`);
    const field =
      key === "media_override"
        ? "mediaOverride"
        : key === "output_mode"
          ? "outputMode"
          : "outputDir";
    nodes = nodes.map((node) =>
      node.id === id
        ? { ...node, data: { ...nodeData(node), [field]: value } }
        : node
    );
    scheduleUiSave();
  }

  function openStepPathPicker(
    nodeId: string,
    key: "media_override" | "output_dir"
  ) {
    nodePathTarget = { nodeId, path: [key], scope: "step" };
    nodePathMode = key === "output_dir" ? "directory" : "file";
    picker = "node-path";
  }

  function openNodePathPicker(nodeId: string, path: string[]) {
    nodePathTarget = { nodeId, path, scope: "params" };
    nodePathTarget = { nodeId, path };
    nodePathMode = /dir|directory|asset_dir/i.test(path[path.length - 1] ?? "") ? "directory" : "file";
    picker = "node-path";
  }

  function duplicateNode(id: string) {
    const source = nodes.find((node) => node.id === id);
    if (source) pushUndo();
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
        onSelect: () => selectNode(nextId),
        onToggle: () => toggleNodeExpanded(nextId),
        onPin: () => toggleNodePinned(nextId),
        onWidth: () => cycleNodeWidth(nextId),
        onResize: (width: number) => resizeNode(nextId, width),
        onPatch: (path: string[], value: unknown) => patchNodeParams(nextId, path, value),
        onPatchMany: (patch: Record<string, unknown>) => patchNodeParamsMany(nextId, patch),
        onPickPath: (path: string[]) => openNodePathPicker(nextId, path),
        onRun: () => void runToHere(nextId),
        onDuplicate: () => duplicateNode(nextId),
        onRemove: () => removeNode(nextId),
        onLogs: () => void openStepLogs(nextId),
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
    pushUndo();
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

  function handleNodeDragStart() {
    pushUndo();
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

  async function compareVersion(version: string) {
    versionDiffBusy = true;
    versionDiffError = "";
    try {
      const current = recipeFromGraph();
      const older = await getRecipeVersion(recipeId, version);
      versionDiffLines = describeRecipeDiff(current, older);
      versionDiffOpen = true;
    } catch (reason) {
      versionDiffError = errorMessage(reason);
    } finally {
      versionDiffBusy = false;
    }
  }

  function describeRecipeDiff(current: Recipe, older: Recipe): string[] {
    const lines: string[] = [];
    if (current.name !== older.name) {
      lines.push(`Name: "${older.name}" → "${current.name}"`);
    }
    const currentSteps = new Map(current.steps.map((step) => [step.id, step]));
    const olderSteps = new Map(older.steps.map((step) => [step.id, step]));
    for (const id of olderSteps.keys()) {
      if (!currentSteps.has(id)) lines.push(`Removed step: ${id}`);
    }
    for (const id of currentSteps.keys()) {
      if (!olderSteps.has(id)) lines.push(`Added step: ${id}`);
    }
    for (const [id, currentStep] of currentSteps) {
      const olderStep = olderSteps.get(id);
      if (!olderStep) continue;
      if (currentStep.type !== olderStep.type) {
        lines.push(`${id}: type ${olderStep.type} → ${currentStep.type}`);
      }
      if (JSON.stringify(currentStep.needs) !== JSON.stringify(olderStep.needs)) {
        lines.push(`${id}: needs [${olderStep.needs.join(", ")}] → [${currentStep.needs.join(", ")}]`);
      }
      if (JSON.stringify(currentStep.inputs) !== JSON.stringify(olderStep.inputs)) {
        lines.push(`${id}: wiring changed`);
      }
      const keys = new Set([
        ...Object.keys(olderStep.params),
        ...Object.keys(currentStep.params)
      ]);
      for (const key of keys) {
        if (
          JSON.stringify(currentStep.params[key]) !==
          JSON.stringify(olderStep.params[key])
        ) {
          lines.push(`${id}.${key}: ${JSON.stringify(olderStep.params[key])} → ${JSON.stringify(currentStep.params[key])}`);
        }
      }
    }
    if (current.steps.length !== older.steps.length) {
      lines.unshift(`Steps: ${older.steps.length} → ${current.steps.length}`);
    }
    return lines.length ? lines : ["No recipe changes."];
  }

  function nodeValidationErrors(): Record<string, string> {
    const errors: Record<string, string> = {};
    for (const node of nodes) {
      const data = nodeData(node);
      for (const [key, message] of Object.entries(validateParams(data.schema ?? {}, data.params ?? {}, data.type))) {
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
        statuses[run.id] =
          run.status === "cached" ? "cached" : run.status === "skipped" ? "skipped" : "executed";
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

  async function saveAs() {
    const id = window.prompt("New recipe id", `${recipeId}_copy`);
    if (!id) return;
    const name = window.prompt("New recipe name", `${recipeName} copy`);
    if (!name) return;
    recipeId = id;
    recipeName = name;
    await save();
  }

  async function openRecipeHistory() {
    recipeHistoryOpen = true;
    recipeHistoryError = "";
    try {
      recipeHistory = await getRecipeHistory(recipeId);
    } catch (reason) {
      recipeHistoryError = errorMessage(reason);
    }
  }

  async function restoreHistory(version: string) {
    try {
      graphFromRecipe(await restoreRecipeVersion(recipeId, version));
      recipeHistoryOpen = false;
      status = `Restored recipe version ${version}`;
    } catch (reason) {
      recipeHistoryError = errorMessage(reason);
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

  async function decideGate(approved: boolean) {
    if (!job) return;
    gateBusy = true;
    error = "";
    try {
      const resumed = await resumeJob(job.job_id, {
        approved,
        comment: gateComment
      });
      job = resumed;
      gateComment = "";
      status = approved ? "Gate approved; job resumed." : "Gate rejected; job resumed.";
      watch(resumed.job_id);
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      gateBusy = false;
    }
  }

  async function dryRun() {
    error = "";
    status = "";
    try {
      const plan = await dryRunRecipe({
        source: "",
        output: "",
        recipe: recipeFromGraph(),
        variables: variableValues,
        profile: recipeProfile || null
      });
      status = `Dry run: ${plan.steps.length} step(s), variables ${JSON.stringify(plan.variables)}.`;
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function refreshRecipes() {
    try {
      recipes = await listRecipes();
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function refreshNodePresets() {
    nodePresets = await listNodePresets();
    nodes = nodes.map((node) => ({
      ...node,
      data: {
        ...nodeData(node),
        presets: nodePresets.filter(
          (preset) => preset.step_type === nodeData(node).type
        )
      }
    }));
  }

  async function saveNodePreset(
    nodeId: string,
    stepType: string,
    name: string
  ) {
    const node = nodes.find((item) => item.id === nodeId);
    if (!node || !name.trim()) return;
    try {
      await createNodePreset({
        step_type: stepType,
        name: name.trim(),
        params: { ...(nodeData(node).params ?? {}) }
      });
      await refreshNodePresets();
      status = `Preset "${name.trim()}" saved.`;
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function updateNodePresetFromNode(nodeId: string, presetId: string) {
    const node = nodes.find((item) => item.id === nodeId);
    if (!node) return;
    try {
      await updateNodePreset(presetId, {
        params: { ...(nodeData(node).params ?? {}) }
      });
      await refreshNodePresets();
      status = "Preset updated.";
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function removeNodePreset(presetId: string) {
    try {
      await deleteNodePreset(presetId);
      await refreshNodePresets();
      status = "Preset deleted.";
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function renameNodePreset(presetId: string, name: string) {
    if (!name.trim()) return;
    try {
      await updateNodePreset(presetId, { name: name.trim() });
      await refreshNodePresets();
      status = "Preset renamed.";
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function duplicateNodePreset(presetId: string, name: string) {
    const preset = nodePresets.find((item) => item.id === presetId);
    if (!preset) return;
    try {
      await createNodePreset({
        step_type: preset.step_type,
        name: name.trim() || `${preset.name} copy`,
        params: { ...preset.params }
      });
      await refreshNodePresets();
      status = "Preset duplicated.";
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function favoritePreset(presetId: string, favorite: boolean) {
    try {
      await favoriteNodePreset(presetId, favorite);
      await refreshNodePresets();
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function saveTags(recipe: RecipeSummary, value: string) {
    const tags = value
      .split(",")
      .map((tag) => tag.trim())
      .filter(Boolean);
    try {
      await updateRecipeTags(recipe.id, tags);
      await refreshRecipes();
      status = `${recipe.name} tags updated.`;
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function toggleFavorite(recipe: RecipeSummary) {
    try {
      await setRecipeFavorite(recipe.id, !recipe.favorite);
      await refreshRecipes();
      status = recipe.favorite
        ? `${recipe.name} removed from favorites.`
        : `${recipe.name} added to favorites.`;
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function execute() {
    error = "";
    status = "";
    const fieldErrors = nodeValidationErrors();
    const errorKeys = Object.keys(fieldErrors);
    if (errorKeys.length) {
      const firstNode = errorKeys[0].split(".")[0];
      if (nodes.some((node) => node.id === firstNode)) {
        selectNode(firstNode);
      }
      error = `Fix ${errorKeys.length} field error(s) before running.`;
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
        source: "",
        output: "",
        recipe,
        save_recipe: true,
        resume,
        variables: variableValues,
        profile: recipeProfile || null
      });
      inputOutput = job.output;
      watch(job.job_id);
      await refreshRecipes();
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
    const fieldErrors = nodeValidationErrors();
    const errorKeys = Object.keys(fieldErrors);
    if (errorKeys.length) {
      const firstNode = errorKeys[0].split(".")[0];
      if (nodes.some((node) => node.id === firstNode)) {
        selectNode(firstNode);
      }
      error = `Fix ${errorKeys.length} field error(s) before running.`;
      return;
    }
    busy = true;
    resetStatuses();
    previousJob = null;
    comparison = null;
    compareOpen = false;
    try {
      const recipe = recipeFromGraph();
      await validateRecipe(recipe, stepId);
      job = await runRecipeStep(stepId, {
        source: "",
        output: "",
        recipe,
        save_recipe: true,
        resume,
        variables: variableValues,
        profile: recipeProfile || null
      });
      inputOutput = job.output;
      watch(job.job_id);
      await refreshRecipes();
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
      if (document.hidden) return;
      try {
        job = await getJob(jobId);
        if (job) {
          inputOutput = job.output;
          applyJobStatuses(job);
        }
        if (["succeeded", "failed", "cancelled", "waiting_approval"].includes(job.status)) {
          clearInterval(poll);
          if (job.status !== "waiting_approval") void loadPrevious(job);
        }
      } catch (reason) {
        error = errorMessage(reason);
        clearInterval(poll);
      }
    }, 800);
  }

  function choose(path: string) {
    if (picker === "workspace") workspaceDraft = path;
    if (picker === "batch-source") batchSourceDir = path;
    if (picker === "batch-output") batchOutputRoot = path;
    if (picker === "broll") patchParams({ asset_dir: path });
    if (picker === "second-source") patchParams({ second_source_path: path });
    if (picker === "node-path" && nodePathTarget) {
      if (nodePathTarget.scope === "step") {
        patchStepField(
          nodePathTarget.nodeId,
          nodePathTarget.path[0] as "media_override" | "output_dir",
          path
        );
      } else {
        patchNodeParams(nodePathTarget.nodeId, nodePathTarget.path, path);
      }
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
      if (document.hidden) return;
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
  <ErrorBanner message={error} onDismiss={() => (error = "")} />
  {#if status}
    <div role="status" class="rounded-2xl border border-emerald-500/20 bg-emerald-950/20 px-4 py-3 text-xs text-emerald-200">{status}</div>
  {/if}

  <section class="relative overflow-hidden rounded-2xl border border-neutral-800 bg-neutral-900/50">
    <div class="flex flex-wrap items-center justify-between gap-2 border-b border-neutral-800 px-3 py-3 sm:px-4">
      <div class="min-w-0">
        <div class="flex items-center gap-1.5">
          <h2 class="text-sm font-semibold text-white">Recipe builder</h2>
          <HelpTip label="Produce" body="Build a DAG of steps, validate it, dry-run it, and execute it. Recipes are the execution contract." doc="docs/recipes.md" />
          <span class="text-[10px] text-neutral-500" aria-live="polite">
            {#if dirty}<span class="text-amber-300">unsaved</span>{:else}{layoutStatus}{/if}
          </span>
        </div>
        <p class="mt-0.5 hidden text-[11px] text-neutral-500 sm:block">
          Connect steps into a DAG. The engine executes dependencies in order; nothing is uploaded.
        </p>
      </div>
      <div class="flex flex-wrap items-center justify-end gap-1.5 text-xs">
        <Button
          icon="plus"
          variant="primary"
          size="md"
          testid="recipe-add-step"
          onclick={() => { addOpen = !addOpen; inspectorOpen = false; }}
        >Add step</Button>
        <Button
          icon="play"
          variant="primary"
          size="md"
          testid="recipe-run"
          disabled={busy}
          onclick={() => void execute()}
        >{busy ? "Starting…" : "Run"}</Button>
        <Button icon="save" variant="secondary" size="md" onclick={() => void save()} title="Save the recipe">Save</Button>
        <Button icon="check" variant="secondary" size="md" onclick={() => void validate()} title="Validate the recipe graph">Validate</Button>
        <Button
          icon="panel"
          variant={inspectorOpen ? "primary" : "secondary"}
          size="md"
          onclick={toggleInspector}
          title={inspectorOpen ? "Close the inspector" : "Open the inspector"}
        >Inspector</Button>
        <IconButton icon="undo" label="Undo" disabled={!undoStack.length} onclick={undo} />
        <IconButton icon="redo" label="Redo" disabled={!redoStack.length} onclick={redo} />
        <Button icon="activity" variant="secondary" size="md" testid="recipe-runs" disabled={historyBusy} onclick={() => void openHistory()}>{historyBusy ? "Runs…" : "Runs"}</Button>
        <IconButton icon="code" label="Recipe JSON" testid="recipe-json" onclick={openRecipeJson} />
        <div class="relative">
          <Button icon="more" variant="secondary" size="md" testid="recipe-more" onclick={() => (moreOpen = !moreOpen)}>More</Button>
          {#if moreOpen}
            <button type="button" class="fixed inset-0 z-40 cursor-default" aria-label="Close menu" onclick={() => (moreOpen = false)}></button>
            <div class="absolute right-0 z-50 mt-1 w-56 overflow-hidden rounded-xl border border-neutral-700 bg-neutral-950 p-1 shadow-2xl" role="menu" data-testid="recipe-more-menu">
              <button type="button" role="menuitem" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-white/5" onclick={() => { moreOpen = false; void dryRun(); }}><Icon name="flask" size={13} />Dry run</button>
              <button type="button" role="menuitem" data-testid="nle-validate" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-white/5" disabled={nleBusy} onclick={() => { moreOpen = false; void openNleValidation(); }}><Icon name="check" size={13} />{nleBusy ? "Validating…" : "Validate NLE exports"}</button>
              <button type="button" role="menuitem" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-white/5" onclick={() => { moreOpen = false; void openBatchHistory(); }}><Icon name="layers" size={13} />Batch history</button>
              <button type="button" role="menuitem" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-white/5" onclick={() => { moreOpen = false; configOpen = true; addOpen = false; }}><Icon name="settings" size={13} />Recipe config</button>
              <div class="my-1 border-t border-neutral-800"></div>
              <button type="button" role="menuitem" data-testid="recipe-reset-layout" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-white/5" onclick={() => { moreOpen = false; resetLayout(); }}><Icon name="layout" size={13} />Auto layout</button>
              <button type="button" role="menuitem" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-white/5" onclick={() => { moreOpen = false; void saveAs(); }}><Icon name="duplicate" size={13} />Save as</button>
              <button type="button" role="menuitem" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-white/5" onclick={() => { moreOpen = false; downloadRecipe(); }}><Icon name="file" size={13} />Download</button>
              <button type="button" role="menuitem" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-white/5" onclick={() => { moreOpen = false; void openRecipeHistory(); }}><Icon name="clock" size={13} />Version history</button>
              <button type="button" role="menuitem" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-white/5" onclick={() => { moreOpen = false; tourStep = 0; tourOpen = true; }}><Icon name="bulb" size={13} />Quick tour</button>
            </div>
          {/if}
        </div>
        <button
          type="button"
          data-testid="recipe-library"
          onclick={() => (templatesOpen = true)}
          class="flex max-w-[240px] items-center gap-1.5 rounded-lg border border-neutral-700 bg-neutral-950 px-2.5 py-1.5 text-xs text-neutral-200 hover:border-sky-500"
          title="Open recipe library"
        >
          <Icon name="folder" size={13} />
          <span class="truncate">{currentRecipe?.name ?? recipeName}</span>
          <Icon name="chevron" size={11} class="text-neutral-500" />
        </button>
        {#if currentRecipe}
          <IconButton
            icon="star"
            label={currentRecipe.favorite ? "Remove from favorites" : "Add to favorites"}
            testid="recipe-favorite"
            class={currentRecipe.favorite ? "text-amber-300" : "text-neutral-400"}
            onclick={() => void toggleFavorite(currentRecipe)}
          />
        {/if}
      </div>
    </div>

    <div class="p-3 sm:p-4">
      {#if Object.keys(recipeVariables).length || Object.keys(recipeProfiles).length}
        <div class="mb-3 rounded-xl border border-neutral-800 bg-neutral-950/50 p-3">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <p class="text-[10px] uppercase tracking-wide text-neutral-500">Recipe inputs</p>
            {#if Object.keys(recipeProfiles).length}
              <select bind:value={recipeProfile} class="rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-200">
                <option value="">no profile</option>
                {#each Object.keys(recipeProfiles) as profile}<option value={profile}>{profile}</option>{/each}
              </select>
            {/if}
          </div>
          <div class="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {#each Object.entries(recipeVariables) as [name, spec]}
              <label class="text-[10px] text-neutral-400" title={spec.description ?? ""}>
                {name}{#if spec.required} *{/if}
                {#if spec.type === "boolean"}
                  <input type="checkbox" checked={Boolean(variableValues[name])} onchange={(event) => (variableValues[name] = event.currentTarget.checked)} class="mt-1 block h-4 w-4 rounded border-neutral-700 bg-neutral-950" />
                {:else if spec.type === "number"}
                  <input type="number" value={variableValues[name] as number} oninput={(event) => (variableValues[name] = Number(event.currentTarget.value))} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" />
                {:else if spec.type === "enum" && spec.options?.length}
                  <select bind:value={variableValues[name]} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100">
                    {#each spec.options as option}<option value={String(option)}>{String(option)}</option>{/each}
                  </select>
                {:else}
                  <input bind:value={variableValues[name]} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" />
                {/if}
              </label>
            {/each}
          </div>
        </div>
      {/if}

      <div class="flex flex-col gap-2 xl:flex-row">
        <div class="relative min-w-0 flex-1">
        <div bind:this={canvasEl} class="h-[clamp(560px,72vh,920px)] overflow-hidden rounded-xl border border-neutral-800 bg-neutral-950">
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
            onnodedragstart={handleNodeDragStart}
            onnodedragstop={handleNodeDragStop}
            onmoveend={() => scheduleUiSave()}
            onnodeclick={({ node }) => selectNode(node.id)}
            onedgeclick={({ edge }) => openEdgeWiring(edge)}
            onselectionchange={({ nodes: selectedNodes }) => {
              selectedNodeIds = selectedNodes.map((node) => node.id);
            }}
          >
            <Background gap={20} size={1} />
            <Controls />
            <MiniMap pannable zoomable />
          </SvelteFlow>
          <div class="pointer-events-none absolute right-2 top-2 z-20 flex max-w-[calc(100%-1rem)] flex-wrap items-center justify-end gap-1 rounded-xl border border-neutral-800 bg-neutral-950/90 p-1 shadow-lg backdrop-blur">
            <input
              value={nodeQuery}
              oninput={(event) => filterNodes(event.currentTarget.value)}
              placeholder="Find node"
              aria-label="Find node"
              class="pointer-events-auto w-32 rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-200 placeholder:text-neutral-600"
            />
            {#if selectedNodeIds.length > 1}
              <span class="pointer-events-none px-1 text-[9px] text-sky-300">{selectedNodeIds.length} selected</span>
              <IconButton icon="layout" label="Align horizontally" title="Align selected nodes to the left" onclick={() => alignSelected("x")} />
              <IconButton icon="layout" label="Align vertically" title="Align selected nodes to the top" onclick={() => alignSelected("y")} />
              <IconButton icon="search" label="Fit selected" title="Fit the selected nodes in the viewport" onclick={fitSelectedNodes} />
              <IconButton icon="duplicate" label="Duplicate selected" onclick={() => { for (const id of selectedNodeIds) duplicateNode(id); }} />
              <IconButton icon="trash" label="Delete selected" variant="danger" onclick={removeSelectedNodes} />
            {/if}
            {#if copiedNodeIds.length}
              <IconButton icon="duplicate" label="Paste copied nodes" title="Paste copied nodes" onclick={pasteNodes} />
            {/if}
          </div>
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
                  <span class="flex items-center gap-1.5">
                    <span style={`color:${step.color ?? "#38bdf8"}`}><Icon name={stepIcon(step.type)} size={13} /></span>
                    <span class="block">{step.title}</span>
                    {#if (step.status ?? "available") !== "available"}
                      <span class={`ml-auto rounded px-1 py-0.5 text-[8px] uppercase ${(step.status ?? "available") === "partial" ? "bg-amber-500/10 text-amber-300" : "bg-neutral-700/60 text-neutral-400"}`}>{step.status}</span>
                    {/if}
                  </span>
                  <span class="font-mono text-[9px] text-neutral-600">{step.type}</span>
                </button>
              {/each}
              {#if filteredSteps.length === 0}
                <p class="px-2 py-3 text-[11px] text-neutral-500">No step matches that filter.</p>
              {/if}
            </div>
          </div>
        {/if}

        </div>
        {#if inspectorOpen}
          {@const inspected = selectedId ? nodes.find((node) => node.id === selectedId) : undefined}
          {#if inspected}
            <NodeInspector
              node={{ id: inspected.id, ...nodeData(inspected) }}
              busy={busy}
              paramText={paramText}
              paramError={paramError}
              wiringOptions={(portId) => availableWiringOptions(inspected.id, portId)}
              oninput={(portId, reference) => setNodeInput(inspected.id, portId, reference)}
              onpatch={(path, value) => patchNodeParams(inspected.id, path, value)}
              onpickpath={(path) => openNodePathPicker(inspected.id, path)}
              onsteppatch={(key, value) => patchStepField(inspected.id, key, value)}
              onpicksteppath={(key) => openStepPathPicker(inspected.id, key)}
              onapplypreset={(preset) => patchNodeParamsMany(inspected.id, preset.params)}
              onsavepreset={(name) => void saveNodePreset(inspected.id, nodeData(inspected).type, name)}
              onupdatepreset={(presetId) => void updateNodePresetFromNode(inspected.id, presetId)}
              ondeletepreset={(presetId) => void removeNodePreset(presetId)}
              onfavoritepreset={(presetId, favorite) => void favoritePreset(presetId, favorite)}
              onrenamepreset={(presetId, name) => void renameNodePreset(presetId, name)}
              onduplicatepreset={(presetId, name) => void duplicateNodePreset(presetId, name)}
              onparaminput={(value) => updateParams(value)}
              onexpandjson={openStepJson}
              onrun={() => void runToHere(inspected.id)}
              onwiring={() => openInspectorWiring(inspected.id)}
              onduplicate={() => duplicateNode(inspected.id)}
              onremove={() => removeNode(inspected.id)}
              onlogs={() => void openStepLogs(inspected.id)}
              onclose={() => (inspectorOpen = false)}
            />
          {:else}
            <aside class="flex h-[clamp(560px,72vh,920px)] w-full shrink-0 flex-col overflow-hidden rounded-2xl border border-neutral-700 bg-neutral-950/98 shadow-2xl backdrop-blur xl:w-[420px]">
              <div class="flex items-center justify-between border-b border-neutral-800 px-3 py-2">
                <p class="text-[10px] uppercase tracking-wide text-neutral-500">Step inspector</p>
                <button type="button" onclick={() => (inspectorOpen = false)} class="rounded px-1.5 text-neutral-500 hover:text-neutral-200" aria-label="Close inspector">×</button>
              </div>
              <div class="flex flex-1 flex-col justify-center p-3">
                <p class="text-[11px] text-neutral-500">Click a node to edit it. Use <span class="text-sky-300">+ Add step</span> to place a new one.</p>
                <button type="button" onclick={() => { inspectorOpen = false; addOpen = true; }} class="mt-3 w-full rounded-lg border border-neutral-700 px-2 py-1.5 text-[11px] text-neutral-300 hover:border-sky-500">Open step palette</button>
              </div>
            </aside>
          {/if}
        {/if}
      </div>
    </div>
  </section>


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
      {#if job.status === "waiting_approval"}
        <div class="mt-3 rounded-xl border border-amber-400/30 bg-amber-950/30 p-3">
          <p class="text-xs font-medium text-amber-200">{job.error?.title || "Approval required"}</p>
          <p class="mt-1 text-[11px] text-amber-200/70">{job.error?.message}</p>
          <textarea rows="2" bind:value={gateComment} placeholder="Decision comment" class="mt-2 w-full rounded-lg border border-amber-400/20 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100"></textarea>
          <div class="mt-2 flex gap-2">
            <button type="button" onclick={() => void decideGate(true)} disabled={gateBusy} class="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-[11px] text-emerald-200 disabled:opacity-40">Approve and resume</button>
            <button type="button" onclick={() => void decideGate(false)} disabled={gateBusy} class="rounded-lg border border-rose-500/40 px-3 py-1.5 text-[11px] text-rose-200 disabled:opacity-40">Reject</button>
          </div>
        </div>
      {/if}
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
      {#if job.result?.variants?.length}
        <div class="mt-3 rounded-xl border border-neutral-800 bg-neutral-950/60 p-3">
          <p class="text-[10px] uppercase tracking-wide text-neutral-500">Variants</p>
          <div class="mt-2 overflow-x-auto">
            <table class="w-full text-left text-[10px] text-neutral-400">
              <thead><tr class="text-neutral-600"><th class="pr-3">name</th><th class="pr-3">output</th><th class="pr-3">segments</th><th class="pr-3">shorts</th><th class="pr-3">steps</th></tr></thead>
              <tbody>
                {#each job.result.variants as variant}
                  {@const summary = variant.summary as Record<string, unknown>}
                  <tr class="border-t border-neutral-800">
                    <td class="py-1 pr-3 text-sky-300">{variant.name}</td>
                    <td class="py-1 pr-3 break-all font-mono text-neutral-500">{variant.output}</td>
                    <td class="py-1 pr-3">{String(summary.video_segment_count ?? "—")}</td>
                    <td class="py-1 pr-3">{String(summary.short_count ?? "—")}</td>
                    <td class="py-1 pr-3">{Array.isArray(summary.step_runs) ? summary.step_runs.length : "—"}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        </div>
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

  {#if tourOpen}
    <div class="fixed inset-0 z-[110] flex items-center justify-center bg-black/75 p-4" role="presentation"
      onclick={(event) => { if (event.currentTarget === event.target) tourOpen = false; }}>
      <div class="w-full max-w-md rounded-2xl border border-sky-500/30 bg-neutral-950 p-5 shadow-2xl" role="dialog" aria-modal="true" aria-label="Builder tour" data-testid="builder-tour">
        <div class="flex items-center justify-between">
          <p class="text-[10px] uppercase tracking-wide text-sky-300">Step {tourStep + 1} of 3</p>
          <button type="button" onclick={() => (tourOpen = false)} class="rounded px-2 text-neutral-500 hover:text-neutral-200" aria-label="Close tour">×</button>
        </div>
        {#if tourStep === 0}
          <h3 class="mt-3 text-base font-semibold text-white">Build the graph</h3>
          <p class="mt-2 text-xs leading-relaxed text-neutral-400">Use <span class="text-sky-300">Add step</span> to place nodes, then drag from a node's right handle to the next node's input. The More menu holds validation, history, batch, and export actions.</p>
        {:else if tourStep === 1}
          <h3 class="mt-3 text-base font-semibold text-white">Inspect and edit</h3>
          <p class="mt-2 text-xs leading-relaxed text-neutral-400">Click a node to open the inspector. It shows every input, output, preset, and field with help text. Edits autosave; Ctrl/Cmd+Z undoes them.</p>
        {:else}
          <h3 class="mt-3 text-base font-semibold text-white">Stay oriented</h3>
          <p class="mt-2 text-xs leading-relaxed text-neutral-400">Use Find node to dim the rest of the graph, shift-drag to select several nodes, and the selection bar to align, duplicate, delete, or fit them. Ctrl/Cmd+K searches every builder action.</p>
        {/if}
        <div class="mt-5 flex items-center justify-between">
          <button type="button" onclick={() => (tourOpen = false)} class="text-[10px] text-neutral-500 hover:text-neutral-200">Skip</button>
          <div class="flex gap-1.5">
            {#if tourStep > 0}<button type="button" onclick={() => (tourStep -= 1)} class="rounded-lg border border-neutral-700 px-2.5 py-1 text-[11px] text-neutral-300">Back</button>{/if}
            {#if tourStep < 2}
              <button type="button" onclick={() => (tourStep += 1)} class="rounded-lg bg-sky-500 px-3 py-1 text-[11px] font-medium text-neutral-950">Next</button>
            {:else}
              <button type="button" onclick={() => (tourOpen = false)} class="rounded-lg bg-sky-500 px-3 py-1 text-[11px] font-medium text-neutral-950">Done</button>
            {/if}
          </div>
        </div>
      </div>
    </div>
  {/if}

  {#if wiring}
    {@const sourceNode = nodes.find((node) => node.id === wiring?.source)}
    {@const targetNode = nodes.find((node) => node.id === wiring?.target)}
    {@const outputPorts = sourceNode ? nodeData(sourceNode).outputPorts ?? [] : []}
    {@const inputPorts = targetNode ? nodeData(targetNode).inputPorts ?? [] : []}
    {@const chosenOutput = outputPorts.find((item) => item.id === wiring?.sourcePort)}
    {@const chosenInput = inputPorts.find((item) => item.id === wiring?.targetPort)}
    {@const compatibleOutputs = outputPorts.filter((port) =>
      chosenInput ? portTypeCompatible(port.type, chosenInput.type) : true
    )}
    {@const incompatibleOutputs = outputPorts.filter(
      (port) => !compatibleOutputs.includes(port)
    )}
    {@const compatibleInputs = inputPorts.filter((port) =>
      chosenOutput ? portTypeCompatible(chosenOutput.type, port.type) : true
    )}
    {@const incompatibleInputs = inputPorts.filter(
      (port) => !compatibleInputs.includes(port)
    )}
    <div class="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-3" role="presentation"
      onclick={(event) => { if (event.currentTarget === event.target) wiring = null; }}>
      <div class="w-full max-w-lg rounded-2xl border border-neutral-700 bg-neutral-950 shadow-2xl" role="dialog" aria-modal="true" aria-label="Wire ports">
        <div class="flex items-center justify-between border-b border-neutral-800 px-4 py-3">
          <div><h3 class="text-sm font-semibold text-white">Wire ports</h3><p class="text-[10px] text-neutral-500">{wiring.source} → {wiring.target}</p></div>
          <button type="button" onclick={() => (wiring = null)} class="rounded px-2 text-neutral-500 hover:text-neutral-200" aria-label="Close port wiring">×</button>
        </div>
        <div class="grid gap-3 p-4 sm:grid-cols-2">
          <div>
            <p class="text-[10px] uppercase tracking-wide text-neutral-500">Outputs from {wiring.source}</p>
            <p class="mt-1 text-[9px] text-neutral-600">{outputPorts.length} port(s), all visible</p>
            <div class="mt-2 space-y-1">
              {#each compatibleOutputs as port}
                <button
                  type="button"
                  data-testid={`wire-output-${port.id}`}
                  aria-pressed={wiring.sourcePort === port.id}
                  onclick={() => {
                    if (!wiring) return;
                    const first = inputPorts.find((input) => portTypeCompatible(port.type, input.type));
                    wiring = { ...wiring, sourcePort: port.id, targetPort: first?.id ?? wiring.targetPort };
                  }}
                  class={`w-full rounded-lg border px-2 py-1.5 text-left text-[10px] ${wiring.sourcePort === port.id ? "border-sky-400/60 bg-sky-500/10 text-sky-100" : "border-neutral-700 text-neutral-300 hover:border-sky-500/50"}`}
                >
                  <span class="block">{port.label}</span>
                  <span class="font-mono text-[9px] text-neutral-500">{port.type}</span>
                </button>
              {/each}
            </div>
            {#if incompatibleOutputs.length}
              <details class="mt-2 rounded-lg border border-neutral-800 bg-neutral-950/60 p-2" data-testid="wire-outputs-incompatible">
                <summary class="cursor-pointer text-[10px] text-neutral-500">Incompatible outputs ({incompatibleOutputs.length})</summary>
                <div class="mt-1 space-y-1">
                  {#each incompatibleOutputs as port}
                    <button type="button" disabled data-testid={`wire-output-incompatible-${port.id}`} class="w-full cursor-not-allowed rounded border border-neutral-800 px-2 py-1 text-left text-[10px] text-neutral-600">
                      <span class="block">{port.label} <span class="text-[9px]">(incompatible)</span></span>
                      <span class="font-mono text-[9px]">{port.type} → {chosenInput?.type ?? "select an input first"}</span>
                    </button>
                  {/each}
                </div>
              </details>
            {/if}
          </div>

          <div>
            <p class="text-[10px] uppercase tracking-wide text-neutral-500">Inputs into {wiring.target}</p>
            <p class="mt-1 text-[9px] text-neutral-600">{inputPorts.length} port(s), all visible</p>
            <div class="mt-2 space-y-1">
              {#each compatibleInputs as port}
                <button
                  type="button"
                  data-testid={`wire-input-${port.id}`}
                  aria-pressed={wiring.targetPort === port.id}
                  onclick={() => {
                    if (!wiring) return;
                    const first = outputPorts.find((output) => portTypeCompatible(output.type, port.type));
                    wiring = { ...wiring, targetPort: port.id, sourcePort: first?.id ?? wiring.sourcePort };
                  }}
                  class={`w-full rounded-lg border px-2 py-1.5 text-left text-[10px] ${wiring.targetPort === port.id ? "border-sky-400/60 bg-sky-500/10 text-sky-100" : "border-neutral-700 text-neutral-300 hover:border-sky-500/50"}`}
                >
                  <span class="block">{port.label}{port.required ? " *" : ""}</span>
                  <span class="font-mono text-[9px] text-neutral-500">{port.type}</span>
                </button>
              {/each}
            </div>
            {#if incompatibleInputs.length}
              <details class="mt-2 rounded-lg border border-neutral-800 bg-neutral-950/60 p-2" data-testid="wire-inputs-incompatible">
                <summary class="cursor-pointer text-[10px] text-neutral-500">Incompatible inputs ({incompatibleInputs.length})</summary>
                <div class="mt-1 space-y-1">
                  {#each incompatibleInputs as port}
                    <button type="button" disabled data-testid={`wire-input-incompatible-${port.id}`} class="w-full cursor-not-allowed rounded border border-neutral-800 px-2 py-1 text-left text-[10px] text-neutral-600">
                      <span class="block">{port.label}{port.required ? " *" : ""} <span class="text-[9px]">(incompatible)</span></span>
                      <span class="font-mono text-[9px]">{chosenOutput?.type ?? "select an output first"} → {port.type}</span>
                    </button>
                  {/each}
                </div>
              </details>
            {/if}
          </div>
        </div>
        <div class="flex items-center justify-between gap-2 border-t border-neutral-800 px-4 py-3">
          <p class="text-[10px] text-neutral-600">All ports are listed; incompatible ones are disabled inside the accordions.</p>
          <div class="flex gap-1.5">
            {#if nodes.some((node) => node.id === wiring?.source) && nodes.some((node) => node.id === wiring?.target)}
              <button type="button" onclick={() => wiring && removeConnection(wiring.source, wiring.target)} class="rounded-lg border border-rose-500/30 px-2.5 py-1 text-[11px] text-rose-300 hover:bg-rose-500/10">Disconnect</button>
            {/if}
            <button type="button" onclick={() => (wiring = null)} class="rounded-lg border border-neutral-700 px-2.5 py-1 text-[11px] text-neutral-300">Cancel</button>
            <button type="button" data-testid="wire-confirm" onclick={confirmWiring} disabled={!inputPorts.length || !chosenOutput || !inputPorts.some((port) => port.id === wiring?.targetPort && chosenOutput && portTypeCompatible(chosenOutput.type, port.type))} class="rounded-lg bg-sky-500 px-3 py-1 text-[11px] font-medium text-neutral-950 disabled:opacity-40">Connect</button>
          </div>
        </div>
      </div>
    </div>
  {/if}

  {#if templatesOpen}
    <div class="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-3" role="presentation"
      onclick={(event) => { if (event.currentTarget === event.target) templatesOpen = false; }}>
      <div class="flex max-h-[82vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-neutral-700 bg-neutral-950 shadow-2xl" role="dialog" aria-modal="true" aria-label="Recipe library">
        <div class="flex items-center justify-between border-b border-neutral-800 px-4 py-3">
          <div><h3 class="text-sm font-semibold text-white">Recipe library</h3><p class="text-[10px] text-neutral-500">Favorites, recent runs, and every saved workflow.</p></div>
          <button type="button" onclick={() => (templatesOpen = false)} class="rounded px-2 text-neutral-500 hover:text-neutral-200" aria-label="Close templates">×</button>
        </div>
        <div class="border-b border-neutral-800 p-3">
          <input bind:value={templateQuery} placeholder="Search recipes…" class="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-1.5 text-xs text-neutral-200" />
          <div class="mt-2 flex flex-wrap gap-1" role="tablist" aria-label="Recipe filters">
            {#each [["favorites", `Favorites (${favoriteCount})`], ["recent", "Recent"], ["all", "All recipes"]] as [id, label]}
              <button
                type="button"
                role="tab"
                aria-selected={recipeFilter === id}
                class={recipeFilter === id ? "rounded-lg bg-sky-500/15 px-2.5 py-1 text-[10px] text-sky-200 ring-1 ring-inset ring-sky-400/25" : "rounded-lg border border-neutral-800 px-2.5 py-1 text-[10px] text-neutral-400 hover:text-neutral-200"}
                onclick={() => (recipeFilter = id as RecipeFilter)}
              >{label}</button>
            {/each}
          </div>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto p-3">
          {#if !visibleRecipes.length}
            <p class="rounded-xl border border-neutral-800 bg-neutral-900/40 p-4 text-xs text-neutral-500">
              {recipeFilter === "recent" ? "Run a recipe to populate Recent." : "No recipe matches this filter."}
            </p>
          {:else}
            <div class="grid gap-2 sm:grid-cols-2">
              {#each visibleRecipes as recipe}
                <div class="flex items-start gap-2 rounded-xl border border-neutral-800 bg-neutral-900/60 p-2 hover:border-sky-500">
                  <button type="button" onclick={() => { templatesOpen = false; void loadRecipe(recipe.id); }} class="min-w-0 flex-1 p-1 text-left">
                    <p class="truncate text-xs font-medium text-neutral-100">{recipe.name}</p>
                    <p class="mt-1 line-clamp-2 text-[10px] leading-4 text-neutral-500">{recipe.description || "No description"}</p>
                    <p class="mt-2 truncate font-mono text-[9px] text-neutral-600">{recipe.id} · {recipe.source}{recipe.last_used_at ? ` · used ${recipe.use_count}×` : ""}</p>
                    <input
                      value={recipe.tags?.join(", ") ?? ""}
                      placeholder="tags"
                      onclick={(event) => event.stopPropagation()}
                      onchange={(event) => void saveTags(recipe, event.currentTarget.value)}
                      class="mt-1 w-full rounded border border-neutral-800 bg-neutral-950 px-1.5 py-0.5 text-[9px] text-neutral-300"
                    />
                    {#if recipe.tags?.length}
                      <p class="mt-1 flex flex-wrap gap-1">{#each recipe.tags as tag}<span class="rounded bg-white/5 px-1.5 py-0.5 text-[9px] text-neutral-400">{tag}</span>{/each}</p>
                    {/if}
                  </button>
                  <button
                    type="button"
                    onclick={() => void toggleFavorite(recipe)}
                    class={recipe.favorite ? "rounded p-1 text-lg leading-none text-amber-300" : "rounded p-1 text-lg leading-none text-neutral-600 hover:text-amber-300"}
                    aria-label={recipe.favorite ? `Remove ${recipe.name} from favorites` : `Add ${recipe.name} to favorites`}
                    title={recipe.favorite ? "Remove from favorites" : "Add to favorites"}
                  ><Icon name="star" size={16} class={recipe.favorite ? "text-amber-300" : "text-neutral-500"} /></button>
                </div>
              {/each}
            </div>
          {/if}
        </div>
      </div>
    </div>
  {/if}

  {#if versionDiffOpen}
    <div class="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-3" role="presentation"
      onclick={(event) => { if (event.currentTarget === event.target) versionDiffOpen = false; }}>
      <div class="flex max-h-[80vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-neutral-700 bg-neutral-950 shadow-2xl" role="dialog" aria-modal="true" aria-label="Version comparison">
        <div class="flex items-center justify-between border-b border-neutral-800 px-4 py-3">
          <div><h3 class="text-sm font-semibold text-white">Version comparison</h3><p class="text-[10px] text-neutral-500">Selected version → current recipe</p></div>
          <button type="button" onclick={() => (versionDiffOpen = false)} class="rounded px-2 text-neutral-500 hover:text-neutral-200" aria-label="Close comparison">×</button>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto p-3">
          {#if versionDiffError}<p class="text-[10px] text-rose-300">{versionDiffError}</p>{/if}
          <ul class="space-y-1 font-mono text-[10px] text-neutral-300">
            {#each versionDiffLines as line}<li class="rounded bg-neutral-900/60 px-2 py-1">{line}</li>{/each}
          </ul>
        </div>
      </div>
    </div>
  {/if}

  {#if recipeHistoryOpen}
    <div class="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-3" role="presentation"
      onclick={(event) => { if (event.currentTarget === event.target) recipeHistoryOpen = false; }}>
      <div class="flex max-h-[80vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl border border-neutral-700 bg-neutral-950 shadow-2xl" role="dialog" aria-modal="true" aria-label="Recipe history">
        <div class="flex items-center justify-between border-b border-neutral-800 px-4 py-3">
          <div><h3 class="text-sm font-semibold text-white">Recipe history</h3><p class="font-mono text-[10px] text-sky-300">{recipeId}</p></div>
          <button type="button" onclick={() => (recipeHistoryOpen = false)} class="rounded px-2 text-neutral-500 hover:text-neutral-200" aria-label="Close history">×</button>
        </div>
        <div class="min-h-0 flex-1 overflow-y-auto p-3">
          {#if recipeHistoryError}<p class="text-[10px] text-rose-300">{recipeHistoryError}</p>{/if}
          {#if !recipeHistory.length && !recipeHistoryError}<p class="text-xs text-neutral-500">Save the recipe twice to create versions.</p>{/if}
          {#each recipeHistory as entry}
            <div class="mb-2 flex items-center justify-between gap-2 rounded-lg border border-neutral-800 bg-neutral-900/60 p-2">
              <div class="min-w-0"><p class="truncate text-xs text-neutral-200">{entry.name}</p><p class="text-[9px] text-neutral-500">{entry.version} · {entry.step_count} steps</p></div>
              <div class="flex gap-1">
                <button type="button" disabled={versionDiffBusy} onclick={() => void compareVersion(entry.version)} class="rounded border border-neutral-700 px-2 py-1 text-[10px] text-neutral-300">Compare</button>
                <button type="button" onclick={() => void restoreHistory(entry.version)} class="rounded border border-sky-500/40 px-2 py-1 text-[10px] text-sky-300">Restore</button>
              </div>
            </div>
          {/each}
        </div>
      </div>
    </div>
  {/if}

  {#if logOpen}
    <div class="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-3" role="presentation"
      onclick={(event) => { if (event.currentTarget === event.target) logOpen = false; }}>
      <div class="flex max-h-[88vh] w-full max-w-3xl flex-col overflow-hidden rounded-2xl border border-neutral-700 bg-neutral-950 shadow-2xl" role="dialog" aria-modal="true" aria-label="Step logs">
        <div class="flex items-center justify-between border-b border-neutral-800 px-4 py-3">
          <div><h3 class="text-sm font-semibold text-white">Step logs</h3><p class="font-mono text-[10px] text-sky-300">{logStep}</p></div>
          <button type="button" onclick={() => (logOpen = false)} class="rounded px-2 text-neutral-500 hover:text-neutral-200" aria-label="Close logs">×</button>
        </div>
        <div class="min-h-0 flex-1 overflow-auto p-3 font-mono text-[10px]">
          {#if logBusy}<p class="text-neutral-500">Loading…</p>{/if}
          {#if logError}<p class="text-rose-300">{logError}</p>{/if}
          {#each logLines as line}
            <p class={`whitespace-pre-wrap ${line.level === "error" ? "text-rose-300" : line.level === "warning" ? "text-amber-300" : "text-neutral-400"}`}>{line.timestamp} {line.level.toUpperCase()} {line.message}</p>
          {/each}
          {#if !logBusy && !logLines.length && !logError}<p class="text-neutral-500">No log lines for this step yet.</p>{/if}
        </div>
      </div>
    </div>
  {/if}

  {#if nleOpen && nleReport}
    <div class="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-3" role="presentation"
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
    <div class="fixed inset-0 z-[100] flex items-center justify-center bg-black/70 p-3" role="presentation"
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
      class="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 p-4"
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
      class="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 p-4"
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
      class="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 p-4"
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

  <Modal
    open={workspaceOpen}
    title="Choose the job output"
    description="Validation and run history read the folder produced by a recipe job."
    width="w-[min(560px,96vw)]"
    onclose={() => (workspaceOpen = false)}
  >
    {#snippet footer()}
      <div class="flex justify-end gap-2">
        <button type="button" onclick={() => (workspaceOpen = false)} class="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300">Cancel</button>
        <button
          type="button"
          data-testid="workspace-continue"
          onclick={() => {
            inputOutput = workspaceDraft.trim();
            workspaceOpen = false;
            const action = workspaceAction;
            workspaceAction = null;
            if (!inputOutput) {
              error = "Choose a job output folder first.";
              return;
            }
            if (action === "nle") void openNleValidation();
            if (action === "history") void openHistory();
          }}
          class="rounded-lg bg-sky-500 px-3 py-1.5 text-xs font-medium text-neutral-950"
        >Continue</button>
      </div>
    {/snippet}
    <label class="block text-[10px] text-neutral-400">
      Output folder
      <span class="mt-1 flex gap-1">
        <input
          bind:value={workspaceDraft}
          data-testid="workspace-output"
          placeholder="/path/to/job-output"
          class="min-w-0 flex-1 rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[11px] text-neutral-100"
        />
        <button type="button" onclick={() => (picker = "workspace")} class="rounded-lg border border-neutral-700 px-2 text-[11px] text-neutral-300">…</button>
      </span>
    </label>
  </Modal>

  <Modal
    open={Boolean(jsonModal)}
    title={jsonModal === "recipe" ? "Recipe JSON" : "Step parameters"}
    label="JSON editor"
    description={jsonModal === "recipe" ? "Edit the full DAG, then apply it to the canvas." : `Editing ${selectedId ?? "selected step"}.`}
    width="w-[min(1100px,96vw)]"
    height="h-[88vh]"
    bodyClass="flex min-h-0 flex-1 flex-col p-3"
    onclose={() => (jsonModal = null)}
  >
    {#snippet footer()}
      <div class="flex items-center justify-between gap-2">
        <p class="text-[10px] text-neutral-500">Apply updates the canvas locally. Run Validate to check the DAG on the server.</p>
        <div class="flex gap-2">
          <button type="button" onclick={() => (jsonModal = null)} class="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300">Cancel</button>
          <button type="button" onclick={applyJson} class="rounded-lg bg-sky-500 px-3 py-1.5 text-xs font-medium text-neutral-950 hover:bg-sky-400">Apply</button>
        </div>
      </div>
    {/snippet}
    {#if jsonModal === "recipe"}
      <textarea
        data-testid="recipe-json-text"
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
  </Modal>

  {#if picker}
    <PathPicker
      open={true}
      mode={picker === "node-path" ? nodePathMode : picker === "second-source" ? "file" : "directory"}
      title={
        picker === "second-source"
            ? "Choose second split-screen source"
          : picker === "node-path"
            ? "Choose step field path"
            : picker === "workspace"
              ? "Choose job output folder"
            : picker === "batch-source"
              ? "Choose batch input folder"
              : picker === "broll"
                ? "Choose local B-roll asset folder"
                : "Choose batch output root"
      }
      initialPath={
        picker === "second-source"
            ? paramString("second_source_path")
          : picker === "node-path"
            ? ""
            : picker === "workspace"
              ? workspaceDraft
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
