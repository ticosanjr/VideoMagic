<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import ErrorBanner from "$lib/ErrorBanner.svelte";
  import HiltPanel from "$lib/HiltPanel.svelte";
  import {
    ApiError,
    cancelJob,
    errorMessage,
    getJob,
    getLogs,
    getRecipe,
    listJobInteractions,
    listJobs,
    listPendingInteractions,
    listRecipeSteps,
    retryJob,
    type HiltInteraction,
    type HiltPending,
    type Job,
    type LogLine,
    type Recipe,
    type RecipeGroup,
    type StepManifest
  } from "$lib/api";

  const RECIPE_ID = "lamera_video_edit";
  const POLL_MS = 1200;

  let recipe = $state<Recipe | null>(null);
  let manifests = $state<StepManifest[]>([]);
  let jobs = $state<Job[]>([]);
  let pending = $state<HiltPending[]>([]);
  let job = $state<Job | null>(null);
  let history = $state<HiltInteraction[]>([]);
  let selectedJobId = $state("");
  let selectedGroupId = $state("");
  let logs = $state<LogLine[]>([]);
  let loading = $state(true);
  let busy = $state(false);
  let error = $state("");
  let logsOpen = $state(false);
  let historyOpen = $state(false);
  let poll: ReturnType<typeof setInterval> | undefined;
  let lastStatus = "";

  const groups = $derived(recipe?.ui?.groups ?? []);

  function statusLabel(status: string): string {
    const labels: Record<string, string> = {
      queued: "Queued",
      paused: "Paused",
      running: "Running",
      waiting_approval: "Waiting approval",
      waiting_input: "Waiting input",
      succeeded: "Succeeded",
      failed: "Failed",
      cancelled: "Cancelled",
      answered: "Answered"
    };
    return labels[status] ?? status;
  }

  function statusClass(status: string): string {
    if (status === "succeeded") return "text-emerald-300 border-emerald-500/30 bg-emerald-500/10";
    if (status === "failed") return "text-rose-300 border-rose-500/30 bg-rose-500/10";
    if (status === "cancelled") return "text-neutral-400 border-neutral-600/40 bg-neutral-700/10";
    if (status === "waiting_approval" || status === "waiting_input") return "text-amber-300 border-amber-500/30 bg-amber-500/10";
    if (status === "running") return "text-sky-300 border-sky-500/30 bg-sky-500/10";
    return "text-neutral-400 border-neutral-700 bg-neutral-800/40";
  }

  function nodeState(id: string): "done" | "cached" | "running" | "waiting" | "failed" | "pending" {
    const run = job?.result?.step_runs?.find((item) => item.id === id);
    if (run) {
      if (run.status === "cached") return "cached";
      if (run.status === "skipped") return "done";
      return "done";
    }
    const stage = job?.stages?.find((item) => item.id === id);
    if (stage?.status === "failed") return "failed";
    if (stage?.status === "running") return "running";
    if (stage?.status === "succeeded") return "done";
    if (
      job?.interaction?.step_id === id &&
      (job.status === "waiting_approval" || job.status === "waiting_input")
    ) {
      return "waiting";
    }
    if (job?.stage === id) return "running";
    return "pending";
  }

  function nodeProgress(id: string): number {
    const run = job?.result?.step_runs?.find((item) => item.id === id);
    if (run) return run.status === "skipped" ? 100 : 100;
    const stage = job?.stages?.find((item) => item.id === id);
    if (stage) return Math.max(0, Math.min(100, stage.progress));
    return Math.max(0, Math.min(100, Number(job?.step_progress?.[id] ?? 0)));
  }

  function nodeStateClass(state: string): string {
    if (state === "done" || state === "cached") return "bg-emerald-400";
    if (state === "running") return "bg-sky-400 animate-pulse";
    if (state === "waiting") return "bg-amber-400 animate-pulse";
    if (state === "failed") return "bg-rose-400";
    return "bg-neutral-600";
  }

  function phaseStats(group: RecipeGroup): {
    done: number;
    running: number;
    waiting: number;
    failed: number;
    total: number;
    percent: number;
    status: string;
  } {
    let done = 0;
    let running = 0;
    let waiting = 0;
    let failed = 0;
    for (const id of group.nodes) {
      const state = nodeState(id);
      if (state === "done" || state === "cached") done += 1;
      else if (state === "running") running += 1;
      else if (state === "waiting") waiting += 1;
      else if (state === "failed") failed += 1;
    }
    const total = Math.max(1, group.nodes.length);
    const current = job?.stage && group.nodes.includes(job.stage) ? nodeProgress(job.stage) : 0;
    const percent = Math.round(((done + (running ? current / 100 : 0)) / total) * 100);
    const status = failed
      ? "failed"
      : waiting
        ? "waiting"
        : running
          ? "running"
          : done >= group.nodes.length
            ? "done"
            : "pending";
    return { done, running, waiting, failed, total: group.nodes.length, percent, status };
  }

  function stepTitle(type: string): string {
    return manifests.find((item) => item.type === type)?.title ?? type;
  }

  function stepIcon(type: string): string {
    return manifests.find((item) => item.type === type)?.icon ?? "●";
  }

  function selectedGroup(): RecipeGroup | null {
    return groups.find((item) => item.id === selectedGroupId) ?? groups[0] ?? null;
  }

  function groupNodes(group: RecipeGroup | null) {
    if (!group || !recipe) return [];
    return group.nodes
      .map((id) => recipe?.steps.find((step) => step.id === id))
      .filter((step): step is NonNullable<typeof step> => Boolean(step));
  }

  function basename(path: string): string {
    const parts = path.split(/[\\/]/);
    return parts[parts.length - 1] || path;
  }

  function shortId(id: string): string {
    return id.slice(0, 8);
  }

  function formatDate(value: string | null): string {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
  }

  function currentGroupId(): string {
    if (!recipe) return "";
    const stage = job?.stage;
    const group = groups.find((item) => stage && item.nodes.includes(stage));
    return group?.id ?? groups[0]?.id ?? "";
  }

  async function selectJob(id: string) {
    clearInterval(poll);
    selectedJobId = id;
    if (!id) {
      job = null;
      logs = [];
      history = [];
      return;
    }
    lastStatus = "";
    const optimistic = jobs.find((item) => item.job_id === id);
    if (optimistic) job = optimistic;
    await refreshJob();
    selectedGroupId = currentGroupId();
    await loadLogs();
    await loadHistory();
    poll = setInterval(() => void refreshJob(), POLL_MS);
  }

  async function refreshJob() {
    if (!selectedJobId) return;
    try {
      const next = await getJob(selectedJobId, { silent: true });
      job = next;
      if (!selectedGroupId) selectedGroupId = currentGroupId();
      if (next.status !== lastStatus) {
        lastStatus = next.status;
        if (next.status === "waiting_approval" || next.status === "waiting_input") {
          await refreshPending();
          await loadHistory();
        }
        if (next.status === "succeeded" || next.status === "failed" || next.status === "cancelled") {
          clearInterval(poll);
          await loadLogs();
          await refreshLists();
          await loadHistory();
        }
      }
    } catch (reason) {
      clearInterval(poll);
      if (reason instanceof ApiError && reason.code === "job_not_found") {
        selectedJobId = "";
        job = null;
        error = "This run is no longer available. Start a new Lamera run in Recipes.";
        return;
      }
      error = errorMessage(reason);
    }
  }

  async function refreshPending() {
    try {
      const items = await listPendingInteractions();
      pending = items.filter((item) => item.interaction.recipe_id === RECIPE_ID);
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function refreshLists() {
    try {
      const [loadedJobs, loadedPending] = await Promise.all([
        listJobs(false, { limit: 30, recipeId: RECIPE_ID }),
        listPendingInteractions()
      ]);
      jobs = loadedJobs;
      pending = loadedPending.filter((item) => item.interaction.recipe_id === RECIPE_ID);
      if (!selectedJobId) {
        const target = pending[0]?.job_id ?? jobs[0]?.job_id ?? "";
        if (target) await selectJob(target);
      }
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function loadLogs() {
    if (!selectedJobId) {
      logs = [];
      return;
    }
    try {
      logs = await getLogs(selectedJobId, undefined, undefined, 250);
    } catch (reason) {
      if (!(reason instanceof ApiError && reason.code === "job_not_found")) {
        error = errorMessage(reason);
      }
    }
  }

  async function loadHistory() {
    if (!selectedJobId) {
      history = [];
      return;
    }
    try {
      history = await listJobInteractions(selectedJobId);
    } catch {
      history = [];
    }
  }

  async function load() {
    loading = true;
    error = "";
    try {
      const [loadedRecipe, loadedManifests] = await Promise.all([
        getRecipe(RECIPE_ID),
        listRecipeSteps()
      ]);
      recipe = loadedRecipe;
      manifests = loadedManifests;
      if (!selectedGroupId) selectedGroupId = groups[0]?.id ?? "";
      await refreshLists();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      loading = false;
    }
  }

  async function refreshAll() {
    busy = true;
    error = "";
    try {
      await refreshLists();
      if (selectedJobId) {
        await refreshJob();
        await loadLogs();
        await loadHistory();
      }
    } finally {
      busy = false;
    }
  }

  async function cancelSelected() {
    if (!job) return;
    if (!window.confirm("Cancel this Lamera run? The current step will stop.")) return;
    busy = true;
    error = "";
    try {
      job = await cancelJob(job.job_id);
      await refreshLists();
      await loadLogs();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  async function retrySelected() {
    if (!job) return;
    busy = true;
    error = "";
    try {
      const next = await retryJob(job.job_id);
      await refreshLists();
      await selectJob(next.job_id);
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  function openPending(item: HiltPending) {
    if (selectedJobId !== item.job_id) {
      void selectJob(item.job_id);
    }
    requestAnimationFrame(() => {
      document.getElementById("lamera-gate")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function openBuilder() {
    window.location.hash = "#recipes";
  }

  async function handleResumed(next: Job) {
    await refreshLists();
    await selectJob(next.job_id);
    error = "";
  }

  onMount(() => {
    void load();
  });

  onDestroy(() => {
    clearInterval(poll);
  });
</script>

<div class="space-y-4">
  <ErrorBanner message={error} onDismiss={() => (error = "")} />

  <section class="rounded-2xl border border-neutral-800 bg-neutral-900/60 p-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p class="text-[10px] uppercase tracking-[0.16em] text-sky-300/70">Lamera workspace</p>
        <h2 class="mt-1 text-lg font-semibold text-neutral-100">Lamera Video Edit</h2>
        <p class="mt-1 max-w-2xl text-[11px] leading-5 text-neutral-400">
          Operate the long-form pipeline by phase: inspect progress, open the current gate,
          review previews, and keep the HITL inbox clear.
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onclick={() => void refreshAll()}
          disabled={busy || loading}
          class="rounded-lg border border-neutral-700 px-3 py-1.5 text-[10px] text-neutral-200 disabled:opacity-40"
        >{busy ? "Refreshing…" : "Refresh"}</button>
        <button
          type="button"
          onclick={openBuilder}
          class="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-[10px] text-sky-200"
        >Open recipe builder</button>
      </div>
    </div>
  </section>

  {#if loading}
    <div class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4 text-xs text-neutral-500">
      Loading Lamera recipe and runs…
    </div>
  {:else if !recipe}
    <div class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4 text-xs text-neutral-500">
      The Lamera recipe is not available in this installation.
    </div>
  {:else}
    <div class="grid gap-4 xl:grid-cols-[330px_1fr]">
      <aside class="space-y-3">
        <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-3">
          <div class="flex items-center justify-between gap-2">
            <h3 class="text-[11px] font-semibold uppercase tracking-wide text-neutral-300">Runs</h3>
            <span class="rounded-full bg-neutral-800 px-2 py-0.5 text-[9px] text-neutral-400">{jobs.length}</span>
          </div>
          <div class="mt-2 space-y-1.5">
            {#each jobs as item (item.job_id)}
              <button
                type="button"
                onclick={() => void selectJob(item.job_id)}
                class={`w-full rounded-lg border px-2 py-1.5 text-left transition ${selectedJobId === item.job_id ? "border-sky-500/40 bg-sky-500/10" : "border-neutral-800 bg-neutral-950/40 hover:border-neutral-700"}`}
                aria-current={selectedJobId === item.job_id ? "true" : undefined}
              >
                <span class="flex items-center justify-between gap-2">
                  <span class="font-mono text-[10px] text-neutral-300">{shortId(item.job_id)}</span>
                  <span class={`rounded border px-1.5 py-0.5 text-[8px] uppercase ${statusClass(item.status)}`}>{statusLabel(item.status)}</span>
                </span>
                <span class="mt-0.5 block truncate text-[10px] text-neutral-400">{basename(item.source)}</span>
                <span class="mt-1 block h-1 overflow-hidden rounded-full bg-neutral-800">
                  <span class="block h-full rounded-full bg-sky-400/70" style={`width:${Math.max(0, Math.min(100, item.progress))}%`}></span>
                </span>
              </button>
            {:else}
              <p class="rounded-lg border border-dashed border-neutral-800 px-2 py-3 text-[10px] text-neutral-500">
                No Lamera run yet. Open the recipe builder and start one.
              </p>
            {/each}
          </div>
        </section>

        <section class="rounded-2xl border border-amber-400/20 bg-amber-950/10 p-3">
          <div class="flex items-center justify-between gap-2">
            <h3 class="text-[11px] font-semibold uppercase tracking-wide text-amber-200">HITL inbox</h3>
            <span class={`rounded-full px-2 py-0.5 text-[9px] ${pending.length ? "bg-amber-500/20 text-amber-200" : "bg-neutral-800 text-neutral-500"}`}>{pending.length}</span>
          </div>
          <div class="mt-2 space-y-1.5">
            {#each pending as item (item.interaction.interaction_id)}
              <button
                type="button"
                onclick={() => openPending(item)}
                class={`w-full rounded-lg border px-2 py-1.5 text-left ${selectedJobId === item.job_id ? "border-amber-400/40 bg-amber-500/10" : "border-amber-400/10 bg-black/10 hover:border-amber-400/30"}`}
              >
                <span class="block text-[10px] font-medium text-amber-100">{item.interaction.title}</span>
                <span class="mt-0.5 block text-[9px] text-amber-100/50">{item.interaction.step_id} · {basename(item.interaction.recipe_id)}</span>
              </button>
            {:else}
              <p class="rounded-lg border border-dashed border-amber-400/10 px-2 py-3 text-[10px] text-amber-100/40">
                No pending gate. The run will appear here when it needs you.
              </p>
            {/each}
          </div>
        </section>

        <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-3">
          <h3 class="text-[11px] font-semibold uppercase tracking-wide text-neutral-300">Phases</h3>
          <div class="mt-2 space-y-1.5">
            {#each groups as group (group.id)}
              {@const stats = phaseStats(group)}
              <button
                type="button"
                onclick={() => (selectedGroupId = group.id)}
                class={`w-full rounded-lg border px-2 py-1.5 text-left ${selectedGroupId === group.id ? "border-white/20 bg-white/[0.04]" : "border-neutral-800 bg-neutral-950/40 hover:border-neutral-700"}`}
                aria-current={selectedGroupId === group.id ? "true" : undefined}
              >
                <span class="flex items-center justify-between gap-2">
                  <span class="truncate text-[10px] font-medium" style={`color:${group.color}`}>{group.label}</span>
                  <span class="text-[9px] text-neutral-500">{stats.done}/{stats.total}</span>
                </span>
                <span class="mt-1 block h-1 overflow-hidden rounded-full bg-neutral-800">
                  <span class="block h-full rounded-full" style={`width:${stats.percent}%;background:${group.color};`}></span>
                </span>
              </button>
            {/each}
          </div>
        </section>
      </aside>

      <main class="min-w-0 space-y-4">
        {#if job}
          <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <span class={`rounded border px-2 py-0.5 text-[9px] uppercase ${statusClass(job.status)}`}>{statusLabel(job.status)}</span>
                  <span class="font-mono text-[10px] text-neutral-500">{job.job_id}</span>
                </div>
                <h3 class="mt-1 truncate text-sm font-semibold text-neutral-100">{job.message || job.stage}</h3>
                <p class="mt-0.5 truncate text-[10px] text-neutral-500">{basename(job.source)} → {job.output}</p>
              </div>
              <div class="flex flex-wrap gap-2">
                {#if job.status === "running" || job.status === "queued" || job.status === "waiting_approval" || job.status === "waiting_input"}
                  <button
                    type="button"
                    onclick={() => void cancelSelected()}
                    disabled={busy}
                    class="rounded-lg border border-rose-500/30 bg-rose-500/10 px-2.5 py-1.5 text-[10px] text-rose-200 disabled:opacity-40"
                  >Cancel run</button>
                {/if}
                {#if job.status === "failed" || job.status === "cancelled"}
                  <button
                    type="button"
                    onclick={() => void retrySelected()}
                    disabled={busy}
                    class="rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1.5 text-[10px] text-emerald-200 disabled:opacity-40"
                  >Retry</button>
                {/if}
              </div>
            </div>
            <div class="mt-3 flex flex-wrap items-center gap-3 text-[10px] text-neutral-500">
              <span>{job.progress}% overall</span>
              <span>stage <span class="font-mono text-neutral-300">{job.stage}</span></span>
              <span>created {formatDate(job.created_at)}</span>
              {#if job.finished_at}<span>finished {formatDate(job.finished_at)}</span>{/if}
            </div>
            <div class="mt-2 h-1.5 overflow-hidden rounded-full bg-neutral-800">
              <div class="h-full rounded-full bg-sky-400/70" style={`width:${Math.max(0, Math.min(100, job.progress))}%`}></div>
            </div>
          </section>

          <section id="lamera-gate" class="scroll-mt-24">
            {#if job.interaction}
              <HiltPanel
                {job}
                onresumed={(next) => void handleResumed(next)}
                onerror={(message) => (error = message)}
              />
            {:else if pending.length}
              <div class="rounded-2xl border border-amber-400/20 bg-amber-950/10 p-4">
                <h3 class="text-xs font-semibold text-amber-100">A gate is waiting in another run</h3>
                <p class="mt-1 text-[10px] text-amber-100/60">Select it in the HITL inbox to open the approval card.</p>
              </div>
            {:else}
              <div class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4">
                <h3 class="text-xs font-semibold text-neutral-200">No gate is waiting</h3>
                <p class="mt-1 text-[10px] text-neutral-500">The run is working or has completed. Phase progress is below.</p>
              </div>
            {/if}
          </section>

          {#if selectedGroup()}
            {@const group = selectedGroup()!}
            {@const stats = phaseStats(group)}
            <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
              <div class="flex flex-wrap items-start justify-between gap-2">
                <div>
                  <h3 class="text-sm font-semibold" style={`color:${group.color}`}>{group.label}</h3>
                  <p class="mt-1 max-w-3xl text-[10px] leading-5 text-neutral-400">{group.description}</p>
                </div>
                <span class="rounded-full border border-neutral-700 px-2 py-0.5 text-[9px] uppercase text-neutral-400">{stats.percent}%</span>
              </div>
              <div class="mt-3 space-y-1.5">
                {#each groupNodes(group) as step (step.id)}
                  {@const state = nodeState(step.id)}
                  {@const percent = nodeProgress(step.id)}
                  <div class="rounded-lg border border-neutral-800 bg-neutral-950/40 px-2.5 py-2">
                    <div class="flex flex-wrap items-center justify-between gap-2">
                      <div class="min-w-0">
                        <span class="flex items-center gap-1.5">
                          <span class={`h-2 w-2 rounded-full ${nodeStateClass(state)}`}></span>
                          <span class="truncate text-[11px] text-neutral-200">{stepIcon(step.type)} {stepTitle(step.type)}</span>
                          {#if job.interaction?.step_id === step.id}
                            <span class="rounded border border-amber-400/30 bg-amber-500/10 px-1.5 py-0.5 text-[8px] uppercase text-amber-200">gate waiting</span>
                          {/if}
                        </span>
                        <span class="mt-0.5 block font-mono text-[9px] text-neutral-500">{step.id} · {step.type}</span>
                      </div>
                      <span class={`rounded border px-1.5 py-0.5 text-[8px] uppercase ${statusClass(state === "done" || state === "cached" ? "succeeded" : state === "failed" ? "failed" : state === "waiting" ? "waiting_approval" : state === "running" ? "running" : "queued")}`}>
                        {state === "cached" ? "cached" : state}
                      </span>
                    </div>
                    {#if state === "running" || state === "waiting"}
                      <div class="mt-1.5 h-1 overflow-hidden rounded-full bg-neutral-800">
                        <div class="h-full rounded-full bg-sky-400/60" style={`width:${percent}%`}></div>
                      </div>
                    {/if}
                  </div>
                {/each}
              </div>
            </section>
          {/if}

          <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <button
                type="button"
                onclick={() => (logsOpen = !logsOpen)}
                class="text-left text-xs font-semibold text-neutral-200"
              >
                Logs {logsOpen ? "▾" : "▸"}
              </button>
              <div class="flex items-center gap-2">
                <span class="text-[9px] text-neutral-500">{logs.length} lines</span>
                <button
                  type="button"
                  onclick={() => void loadLogs()}
                  class="rounded border border-neutral-700 px-2 py-0.5 text-[9px] text-neutral-300"
                >Reload</button>
              </div>
            </div>
            {#if logsOpen}
              <div class="mt-2 max-h-72 overflow-auto rounded-lg border border-neutral-800 bg-black/30 p-2 font-mono text-[9px] leading-4">
                {#each logs as line}
                  <div class={line.level === "error" ? "text-rose-300" : line.level === "warning" ? "text-amber-300" : line.level === "debug" ? "text-neutral-500" : "text-neutral-300"}>
                    <span class="text-neutral-600">{line.timestamp.slice(11, 19)}</span>
                    <span class="ml-1 text-sky-300/70">{line.module}</span>
                    <span class="ml-1">{line.message}</span>
                  </div>
                {:else}
                  <p class="text-neutral-500">No logs loaded.</p>
                {/each}
              </div>
            {/if}
          </section>

          <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
            <button
              type="button"
              onclick={() => (historyOpen = !historyOpen)}
              class="text-left text-xs font-semibold text-neutral-200"
            >
              Gate history {historyOpen ? "▾" : "▸"} <span class="ml-1 text-[9px] font-normal text-neutral-500">{history.length}</span>
            </button>
            {#if historyOpen}
              <div class="mt-2 space-y-1">
                {#each history as item}
                  <div class="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-neutral-800 bg-neutral-950/40 px-2 py-1.5 text-[10px]">
                    <span class="truncate text-neutral-300">{item.title}</span>
                    <span class="uppercase text-neutral-500">{item.status}</span>
                  </div>
                {:else}
                  <p class="text-[10px] text-neutral-500">No gate history for this run.</p>
                {/each}
              </div>
            {/if}
          </section>
        {:else}
          <div class="rounded-2xl border border-dashed border-neutral-800 bg-neutral-900/30 p-8 text-center">
            <p class="text-sm text-neutral-300">No Lamera run selected.</p>
            <p class="mt-1 text-[10px] text-neutral-500">Open the recipe builder, choose Lamera Video Edit, and start a run.</p>
            <button
              type="button"
              onclick={openBuilder}
              class="mt-3 rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-[10px] text-sky-200"
            >Open recipe builder</button>
          </div>
        {/if}
      </main>
    </div>
  {/if}
</div>
