<script lang="ts">
  import { onMount } from "svelte";
  import {
    cancelJob,
    errorMessage,
    listJobs,
    retryJob,
    type Job
  } from "$lib/api";
  import ErrorBanner from "$lib/ErrorBanner.svelte";
  import { elapsedMs, formatDateTime, formatDuration, statusText } from "$lib/format";
  import {
    filterJobs,
    jobCounts,
    jobDisplayName,
    jobNextAction,
    type JobFilter
  } from "$lib/jobsView";
  import { notifications } from "$lib/notifications.svelte";

  let {
    onreview,
    onopentimeline
  }: {
    onreview?: (job: Job) => void;
    onopentimeline?: (job: Job) => void;
  } = $props();

  let jobs = $state<Job[]>([]);
  let filter = $state<JobFilter>("all");
  let query = $state("");
  let error = $state("");
  let loading = $state(true);
  let busy = $state("");
  let confirmCancel = $state("");

  const counts = $derived(jobCounts(jobs));
  const visible = $derived(filterJobs(jobs, { filter, query }));
  const filters: { id: JobFilter; label: string; count: number }[] = $derived([
    { id: "all", label: "All", count: counts.total },
    { id: "active", label: "Running", count: counts.active },
    { id: "queued", label: "Queued", count: counts.queued },
    { id: "attention", label: "Needs attention", count: counts.waiting + counts.failed },
    { id: "failed", label: "Failed", count: counts.failed },
    { id: "succeeded", label: "Succeeded", count: counts.succeeded }
  ]);

  let timer: ReturnType<typeof setInterval> | undefined;

  onMount(() => {
    void refresh();
    timer = setInterval(() => void refresh(), 4000);
    return () => clearInterval(timer);
  });

  async function refresh() {
    try {
      jobs = await listJobs();
      error = "";
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      loading = false;
    }
  }

  function tone(status: string): string {
    switch (status) {
      case "failed":
        return "border-rose-500/30 bg-rose-950/40 text-rose-200";
      case "waiting_approval":
        return "border-amber-400/30 bg-amber-950/30 text-amber-200";
      case "running":
        return "border-sky-400/25 bg-sky-950/30 text-sky-200";
      case "queued":
        return "border-neutral-700 bg-white/[0.03] text-neutral-300";
      case "succeeded":
        return "border-emerald-400/25 bg-emerald-950/30 text-emerald-200";
      default:
        return "border-neutral-700 bg-white/[0.03] text-neutral-400";
    }
  }

  async function cancel(job: Job) {
    busy = job.job_id;
    try {
      await cancelJob(job.job_id);
      notifications.push({ kind: "info", title: "Job cancelled", message: jobDisplayName(job) });
      await refresh();
    } catch (reason) {
      error = errorMessage(reason);
      notifications.push({
        kind: "error",
        title: "Could not cancel the job",
        message: errorMessage(reason),
        actionLabel: "Open the jobs tab",
        actionId: "tab:jobs"
      });
    } finally {
      busy = "";
      confirmCancel = "";
    }
  }

  async function retry(job: Job) {
    busy = job.job_id;
    try {
      const retried = await retryJob(job.job_id);
      notifications.push({
        kind: "success",
        title: "Job retried",
        message: `New job ${retried.job_id}`,
        actionLabel: "Open",
        actionId: `job:${retried.job_id}`
      });
      await refresh();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = "";
    }
  }
</script>

<section class="space-y-4">
  <header class="flex flex-wrap items-end justify-between gap-3">
    <div>
      <h2 class="text-lg font-semibold text-white">Jobs</h2>
      <p class="mt-1 text-xs text-neutral-500">Every queued, running, waiting, and finished job with the next action to take.</p>
    </div>
    <div class="flex items-center gap-2">
      <input
        bind:value={query}
        type="search"
        placeholder="Search id, recipe, stage, source…"
        aria-label="Search jobs"
        class="w-56 rounded-xl border border-neutral-700 bg-neutral-950 px-3 py-1.5 text-xs text-neutral-200 placeholder:text-neutral-600 focus:border-sky-500/50 focus:outline-none"
      />
      <button
        type="button"
        onclick={() => void refresh()}
        class="rounded-xl border border-white/10 px-3 py-1.5 text-xs text-neutral-300 hover:border-sky-500/40 hover:text-sky-200"
      >Refresh</button>
    </div>
  </header>

  <ErrorBanner message={error} title="Could not load jobs" onDismiss={() => (error = "")} testId="jobs-error" />

  <div class="flex flex-wrap gap-1.5" role="tablist" aria-label="Job filters">
    {#each filters as item}
      <button
        type="button"
        role="tab"
        aria-selected={filter === item.id}
        onclick={() => (filter = item.id)}
        class={`rounded-full px-3 py-1 text-[11px] font-medium transition ${filter === item.id ? "bg-sky-500/15 text-sky-200 ring-1 ring-inset ring-sky-400/25" : "border border-neutral-800 text-neutral-400 hover:text-neutral-200"}`}
      >{item.label} <span class="ml-1 font-mono opacity-70">{item.count}</span></button>
    {/each}
  </div>

  {#if loading}
    <div class="space-y-2" aria-hidden="true">
      {#each [0, 1, 2] as row (row)}
        <div class="h-20 animate-pulse rounded-2xl border border-neutral-800 bg-white/[0.02]"></div>
      {/each}
    </div>
  {:else if visible.length === 0}
    <p class="rounded-2xl border border-dashed border-neutral-800 px-4 py-10 text-center text-xs text-neutral-500">
      No job matches this filter. Run a recipe or clear the search.
    </p>
  {:else}
    <ul class="space-y-2" data-testid="job-list">
      {#each visible as job (job.job_id)}
        <li class="rounded-2xl border border-neutral-800 bg-white/[0.02] p-4">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0">
              <div class="flex flex-wrap items-center gap-2">
                <p class="truncate text-sm font-medium text-neutral-100">{jobDisplayName(job)}</p>
                <span class={`rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${tone(job.status)}`}>{statusText(job.status)}</span>
                {#if job.result?.recipe_id}
                  <span class="rounded-full border border-white/10 px-2 py-0.5 font-mono text-[10px] text-neutral-400">{job.result.recipe_id}</span>
                {/if}
              </div>
              <p class="mt-1 truncate font-mono text-[10px] text-neutral-600">{job.job_id}</p>
            </div>
            <div class="text-right text-[10px] text-neutral-500">
              <p>created {formatDateTime(job.created_at)}</p>
              <p>{formatDuration(elapsedMs(job.started_at, job.finished_at))}</p>
            </div>
          </div>

          <div class="mt-3">
            <div class="flex items-center justify-between text-[11px] text-neutral-400">
              <span class="truncate">{job.stage}: {job.message || "—"}</span>
              <span class="ml-2 font-mono">{job.progress}%</span>
            </div>
            <div class="mt-1 h-1.5 overflow-hidden rounded-full bg-neutral-800">
              <div
                class={`h-full rounded-full ${job.status === "failed" ? "bg-rose-400" : job.status === "waiting_approval" ? "bg-amber-400" : "bg-sky-400"} transition-all`}
                style={`width: ${Math.max(0, Math.min(100, job.progress))}%`}
              ></div>
            </div>
          </div>

          {#if job.error}
            <p class="mt-2 rounded-lg border border-rose-500/20 bg-rose-950/30 px-2.5 py-1.5 text-[11px] text-rose-200">
              {job.error.title || job.error.code}: {job.error.message}
            </p>
          {/if}

          <div class="mt-3 flex flex-wrap items-center justify-between gap-2">
            <p class="text-[11px] text-neutral-500">Next: <span class="text-neutral-300">{jobNextAction(job)}</span></p>
            <div class="flex flex-wrap gap-1.5">
              {#if job.status === "waiting_approval"}
                <button type="button" class="rounded-lg bg-amber-400/15 px-2.5 py-1 text-[11px] font-medium text-amber-200 ring-1 ring-inset ring-amber-400/25 hover:bg-amber-400/20" onclick={() => onreview?.(job)}>Review</button>
              {:else if job.status === "failed" || job.status === "cancelled"}
                <button type="button" disabled={busy === job.job_id} class="rounded-lg bg-sky-500/15 px-2.5 py-1 text-[11px] font-medium text-sky-200 ring-1 ring-inset ring-sky-400/25 hover:bg-sky-500/20 disabled:opacity-40" onclick={() => void retry(job)}>
                  {busy === job.job_id ? "Retrying…" : "Retry"}
                </button>
              {:else if job.status === "succeeded"}
                {#if job.result?.artifacts && Object.keys(job.result.artifacts).length}
                  <button type="button" class="rounded-lg border border-white/10 px-2.5 py-1 text-[11px] text-neutral-300 hover:text-sky-200" onclick={() => onopentimeline?.(job)}>Open in Timeline</button>
                {/if}
              {/if}
              {#if ["running", "queued"].includes(job.status)}
                {#if confirmCancel === job.job_id}
                  <button type="button" class="rounded-lg border border-rose-400/30 bg-rose-500/10 px-2.5 py-1 text-[11px] text-rose-200" onclick={() => void cancel(job)}>Confirm cancel</button>
                  <button type="button" class="rounded-lg border border-white/10 px-2.5 py-1 text-[11px] text-neutral-400" onclick={() => (confirmCancel = "")}>Keep</button>
                {:else}
                  <button type="button" class="rounded-lg border border-rose-500/20 px-2.5 py-1 text-[11px] text-rose-300 hover:border-rose-400/40" onclick={() => (confirmCancel = job.job_id)}>Cancel</button>
                {/if}
              {/if}
            </div>
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</section>
