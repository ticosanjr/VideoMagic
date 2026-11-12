<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import Button from "$lib/ui/Button.svelte";
  import ErrorBanner from "$lib/ErrorBanner.svelte";
  import HiltPanel from "$lib/HiltPanel.svelte";
  import DocumentaryOverview from "$lib/DocumentaryOverview.svelte";
  import FootageOverview from "$lib/FootageOverview.svelte";
  import SyntheticOverview from "$lib/SyntheticOverview.svelte";
  import Icon from "$lib/ui/Icon.svelte";
  import Progress from "$lib/ui/Progress.svelte";
  import StatusBadge from "$lib/StatusBadge.svelte";
  import {
    errorMessage,
    getJob,
    getLogs,
    getRecipe,
    listJobInteractions,
    type HiltInteraction,
    type Job,
    type LogLine,
    type Recipe
  } from "$lib/api";
  import { formatDateTime, formatDuration } from "$lib/format";
  import { jobDisplayName } from "$lib/jobsView";
  import { i18n } from "$lib/i18n.svelte";

  let {
    jobId,
    onback,
    onopenbuilder
  }: {
    jobId: string;
    onback: () => void;
    onopenbuilder?: (recipeId: string) => void;
  } = $props();

  let job = $state<Job | null>(null);
  let recipe = $state<Recipe | null>(null);
  let logs = $state<LogLine[]>([]);
  let history = $state<HiltInteraction[]>([]);
  let loading = $state(true);
  let error = $state("");
  let tab = $state<"overview" | "artifacts" | "logs" | "history">("overview");
  let poll: ReturnType<typeof setTimeout> | undefined;
  let inFlight = false;
  let lastStatus = "";

  const groups = $derived(recipe?.ui?.groups ?? []);
  const kind = $derived.by(() => {
    const id =
      recipe?.id ||
      job?.result?.recipe_id ||
      job?.interaction?.recipe_id ||
      "";
    if (id === "synthetic_code_studio") return "synthetic";
    if (id === "footage_intelligence_edit") return "footage";
    if (["lamera_video_edit", "full_ai_editor", "deepseek_full_edit"].includes(id)) {
      return "documentary";
    }
    return "generic";
  });
  const artifacts = $derived(
    Object.entries(job?.result?.artifacts ?? {}) as Array<[string, string]>
  );
  const artifactMap = $derived(
    Object.fromEntries(artifacts) as Record<string, string>
  );
  const terminal = $derived(
    job ? ["succeeded", "failed", "cancelled"].includes(job.status) : false
  );

  onMount(() => {
    const onVisibility = () => {
      if (!document.hidden) schedule();
    };
    document.addEventListener("visibilitychange", onVisibility);
    void load();
    return () => {
      clearTimeout(poll);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  });

  onDestroy(() => clearTimeout(poll));

  async function load() {
    loading = true;
    error = "";
    try {
      const next = await getJob(jobId);
      job = next;
      const recipeId =
        next.result?.recipe_id ||
        next.interaction?.recipe_id ||
        ((next.options as { recipe?: { id?: string } } | undefined)?.recipe?.id ?? "");
      if (recipeId && recipe?.id !== recipeId) {
        recipe = await getRecipe(recipeId).catch(() => null);
      }
      await Promise.all([loadLogs(), loadHistory()]);
      lastStatus = next.status;
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      loading = false;
      schedule();
    }
  }

  async function refresh() {
    error = "";
    try {
      const next = await getJob(jobId, { silent: true });
      const changed = next.status !== lastStatus;
      job = next;
      lastStatus = next.status;
      if (changed || tab === "logs" || tab === "history") {
        await Promise.all([loadLogs(), loadHistory()]);
      }
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      schedule();
    }
  }

  async function loadLogs() {
    try {
      logs = await getLogs(jobId, undefined, undefined, 300);
    } catch {
      logs = [];
    }
  }

  async function loadHistory() {
    try {
      history = await listJobInteractions(jobId);
    } catch {
      history = [];
    }
  }

  function schedule() {
    clearTimeout(poll);
    if (!job || terminal || document.hidden) return;
    poll = setTimeout(() => {
      if (inFlight) {
        schedule();
        return;
      }
      inFlight = true;
      void refresh().finally(() => {
        inFlight = false;
      });
    }, job.status === "waiting_approval" || job.status === "waiting_input" ? 5000 : 1500);
  }

  async function resumed(next: Job) {
    job = next;
    await refresh();
  }

  function stepState(id: string): "done" | "running" | "waiting" | "failed" | "pending" {
    const run = job?.result?.step_runs?.find((item) => item.id === id);
    if (run) return run.status === "skipped" ? "done" : "done";
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

  function groupProgress(nodes: string[]): number {
    if (!nodes.length) return 0;
    const done = nodes.filter((id) => ["done", "waiting"].includes(stepState(id))).length;
    return Math.round((done / nodes.length) * 100);
  }

  function artifactUrl(name: string): string {
    return `/api/v1/jobs/${encodeURIComponent(jobId)}/artifacts/${encodeURIComponent(name)}`;
  }

  function openBuilder() {
    const recipeId =
      job?.result?.recipe_id ||
      job?.interaction?.recipe_id ||
      recipe?.id ||
      "";
    if (recipeId) onopenbuilder?.(recipeId);
  }
</script>

<div class="space-y-4" data-testid="recipe-workspace">
  <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="flex min-w-0 items-start gap-3">
        <button type="button" onclick={onback} class="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-neutral-700 text-neutral-400 hover:text-neutral-100" aria-label={i18n.t("back")}>
          <Icon name="chevron" size={15} class="rotate-90" />
        </button>
        <div class="min-w-0">
          <p class="vf-label">Run workspace</p>
          <h2 class="mt-1 truncate text-[length:var(--vf-text-xl)] font-semibold text-white">
            {recipe?.name || (job ? jobDisplayName(job) : jobId)}
          </h2>
          <p class="mt-1 flex flex-wrap items-center gap-2 text-[length:var(--vf-text-xs)] text-neutral-500">
            {#if job}<StatusBadge status={job.status} />{/if}
            <span class="font-mono">{jobId}</span>
            {#if job?.stage}<span>· {job.stage}</span>{/if}
          </p>
        </div>
      </div>
      <div class="flex flex-wrap gap-2">
        <Button variant="secondary" icon="refresh" onclick={() => void refresh()}>Refresh</Button>
        {#if recipe}<Button variant="secondary" icon="code" onclick={openBuilder}>Open builder</Button>{/if}
        <Button variant="secondary" icon="activity" onclick={onback}>{i18n.t("open_runs")}</Button>
      </div>
    </div>
    {#if job}
      <div class="mt-4 flex items-center gap-3">
        <Progress value={job.progress} label={job.message || job.stage} tone={job.status === "failed" ? "danger" : job.status === "succeeded" ? "success" : "accent"} />
        <span class="w-12 shrink-0 text-right font-mono text-[length:var(--vf-text-xs)] text-neutral-400">{job.progress}%</span>
      </div>
      <p class="mt-2 truncate text-[length:var(--vf-text-xs)] text-neutral-400">{job.message || job.stage}</p>
    {/if}
  </section>

  <ErrorBanner message={error} title="The run could not be loaded" onDismiss={() => (error = "")} />

  {#if loading && !job}
    <div class="flex items-center gap-3 rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4">
      <Progress value={35} label="Loading run" />
      <span class="text-[length:var(--vf-text-xs)] text-neutral-500">Loading run…</span>
    </div>
  {:else if job}
    <div class="flex flex-wrap gap-1.5" role="tablist" aria-label="Workspace views">
      {#each [["overview", "Overview"], ["artifacts", "Artifacts"], ["logs", "Logs"], ["history", "History"]] as [id, label]}
        <button
          type="button"
          role="tab"
          aria-selected={tab === id}
          onclick={() => (tab = id as typeof tab)}
          class={`rounded-lg border px-3 py-1.5 text-[length:var(--vf-text-xs)] transition-colors ${tab === id ? "border-sky-400/30 bg-sky-400/10 text-sky-100" : "border-neutral-800 text-neutral-400 hover:text-neutral-100"}`}
        >{label}</button>
      {/each}
    </div>

    <div class="grid gap-4 xl:grid-cols-[280px_minmax(0,1fr)_300px]">
      <aside class="space-y-3">
        <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-3">
          <p class="vf-label">Phases</p>
          {#if groups.length}
            <ol class="mt-2 space-y-2">
              {#each groups as group}
                {@const percent = groupProgress(group.nodes)}
                <li class="rounded-lg border border-neutral-800 bg-neutral-950/50 px-3 py-2">
                  <div class="flex items-center justify-between gap-2">
                    <span class="truncate text-[length:var(--vf-text-xs)] font-medium" style={`color:${group.color}`}>{group.label}</span>
                    <span class="font-mono text-[length:var(--vf-text-2xs)] text-neutral-500">{percent}%</span>
                  </div>
                  <Progress value={percent} label={group.label} tone={percent === 100 ? "success" : "accent"} />
                </li>
              {/each}
            </ol>
          {:else if job.stages.length}
            <ol class="mt-2 space-y-1.5">
              {#each job.stages as stage}
                <li class="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 text-[length:var(--vf-text-xs)]">
                  <span class="truncate text-neutral-300">{stage.label || stage.id}</span>
                  <StatusBadge status={stage.status} />
                </li>
              {/each}
            </ol>
          {:else}
            <p class="mt-2 text-[length:var(--vf-text-xs)] text-neutral-500">Stages appear when the run starts.</p>
          {/if}
        </section>
      </aside>

      <main class="min-w-0 space-y-4">
        {#if tab === "overview"}
          {#if job.interaction && (job.status === "waiting_approval" || job.status === "waiting_input")}
            <HiltPanel {job} onresumed={(next) => void resumed(next)} onerror={(message) => (error = message)} />
          {:else}
            <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
              <div class="flex items-center justify-between gap-3">
                <div>
                  <p class="vf-label">Current step</p>
                  <h3 class="mt-1 text-[length:var(--vf-text-base)] font-semibold text-neutral-100">{job.stage || "Waiting"}</h3>
                  <p class="mt-1 text-[length:var(--vf-text-xs)] text-neutral-500">{job.message || "The runner has not reported a message yet."}</p>
                </div>
                {#if job.status === "running" || job.status === "queued"}<span class="h-2.5 w-2.5 animate-pulse rounded-full bg-sky-400"></span>{/if}
              </div>
              <div class="mt-3"><Progress value={job.progress} label={job.stage} /></div>
            </section>
            {#if kind === "synthetic"}
              <SyntheticOverview jobId={jobId} artifacts={artifactMap} />
            {:else if kind === "footage"}
              <FootageOverview jobId={jobId} />
            {:else if kind === "documentary"}
              <DocumentaryOverview jobId={jobId} title={recipe?.name ?? "Documentary pipeline"} />
            {/if}
            <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
              <p class="vf-label">Recent log</p>
              {#if logs.length}
                <ul class="mt-2 space-y-1 font-mono text-[length:var(--vf-text-2xs)] text-neutral-400">
                  {#each logs.slice(-6) as line}
                    <li class="truncate"><span class="text-neutral-600">{line.timestamp?.slice(11, 19) || ""}</span> <span class={line.level === "error" ? "text-rose-300" : line.level === "warning" ? "text-amber-300" : ""}>{line.message}</span></li>
                  {/each}
                </ul>
              {:else}
                <p class="mt-2 text-[length:var(--vf-text-xs)] text-neutral-500">No logs yet.</p>
              {/if}
            </section>
          {/if}
        {:else if tab === "artifacts"}
          <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
            <p class="vf-label">Artifacts</p>
            {#if artifacts.length}
              <ul class="mt-3 grid gap-2 sm:grid-cols-2">
                {#each artifacts as [name, path]}
                  <li>
                    <a href={artifactUrl(name)} target="_blank" rel="noreferrer" class="flex items-center justify-between gap-2 rounded-lg border border-neutral-800 bg-neutral-950/50 px-3 py-2 text-[length:var(--vf-text-xs)] text-neutral-300 hover:border-sky-500/40">
                      <span class="truncate">{name}</span>
                      <Icon name="external" size={14} class="shrink-0 text-neutral-500" />
                    </a>
                    <p class="mt-1 truncate px-1 font-mono text-[length:var(--vf-text-2xs)] text-neutral-600">{path}</p>
                  </li>
                {/each}
              </ul>
            {:else}
              <p class="mt-2 text-[length:var(--vf-text-xs)] text-neutral-500">No artifacts yet. They appear as the run produces files.</p>
            {/if}
          </section>
        {:else if tab === "logs"}
          <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
            <p class="vf-label">Logs</p>
            {#if logs.length}
              <ol class="mt-3 max-h-[62vh] space-y-1 overflow-auto font-mono text-[length:var(--vf-text-2xs)]">
                {#each logs as line}
                  <li class="rounded px-2 py-1 hover:bg-white/[0.03]">
                    <span class="text-neutral-600">{line.timestamp?.slice(11, 19) || ""}</span>
                    <span class="ml-2 text-neutral-500">{line.module}</span>
                    <span class={`ml-2 ${line.level === "error" ? "text-rose-300" : line.level === "warning" ? "text-amber-300" : "text-neutral-300"}`}>{line.message}</span>
                  </li>
                {/each}
              </ol>
            {:else}
              <p class="mt-2 text-[length:var(--vf-text-xs)] text-neutral-500">No logs yet.</p>
            {/if}
          </section>
        {:else}
          <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
            <p class="vf-label">History</p>
            {#if history.length}
              <ul class="mt-3 space-y-2">
                {#each history as item (item.interaction_id)}
                  <li class="rounded-lg border border-neutral-800 bg-neutral-950/50 px-3 py-2">
                    <div class="flex flex-wrap items-center justify-between gap-2">
                      <span class="text-[length:var(--vf-text-xs)] text-neutral-200">{item.title}</span>
                      <StatusBadge status={item.status} />
                    </div>
                    <p class="mt-1 text-[length:var(--vf-text-2xs)] text-neutral-500">{item.kind} · {formatDateTime(item.created_at)}</p>
                    {#if item.response?.comment}<p class="mt-1 text-[length:var(--vf-text-xs)] text-neutral-400">{item.response.comment}</p>{/if}
                  </li>
                {/each}
              </ul>
            {:else}
              <p class="mt-2 text-[length:var(--vf-text-xs)] text-neutral-500">No interactions yet.</p>
            {/if}
          </section>
        {/if}
      </main>

      <aside class="space-y-3">
        <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
          <p class="vf-label">Run details</p>
          <dl class="mt-2 space-y-2 text-[length:var(--vf-text-xs)]">
            <div><dt class="text-neutral-500">Source</dt><dd class="truncate font-mono text-neutral-300">{job.source || "—"}</dd></div>
            <div><dt class="text-neutral-500">Output</dt><dd class="truncate font-mono text-neutral-300">{job.output || "—"}</dd></div>
            <div><dt class="text-neutral-500">Created</dt><dd class="text-neutral-300">{formatDateTime(job.created_at)}</dd></div>
            <div><dt class="text-neutral-500">Duration</dt><dd class="text-neutral-300">{formatDuration(job.duration_ms)}</dd></div>
          </dl>
        </section>
        <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
          <p class="vf-label">Recent runs</p>
          <p class="mt-2 text-[length:var(--vf-text-xs)] text-neutral-500">Use Open runs to switch between active runs and gates.</p>
        </section>
      </aside>
    </div>
  {:else}
    <div class="rounded-2xl border border-rose-500/30 bg-rose-950/20 p-4 text-[length:var(--vf-text-sm)] text-rose-200">
      This run is no longer available.
    </div>
  {/if}
</div>
