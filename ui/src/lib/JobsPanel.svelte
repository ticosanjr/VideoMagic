<script lang="ts">
  import { onMount } from "svelte";
  import {
    cancelJob,
    errorMessage,
    listJobs,
    pauseJob,
    retryJob,
    setJobPriority,
    unpauseJob,
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
  import { i18n } from "$lib/i18n.svelte";

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
    { id: "all", label: i18n.t("all"), count: counts.total },
    { id: "active", label: i18n.t("running"), count: counts.active },
    { id: "queued", label: i18n.t("queued"), count: counts.queued },
    { id: "paused", label: i18n.t("paused"), count: counts.paused },
    { id: "attention", label: i18n.t("attention"), count: counts.waiting + counts.failed },
    { id: "failed", label: i18n.t("failed"), count: counts.failed },
    { id: "succeeded", label: i18n.t("succeeded"), count: counts.succeeded }
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

  async function togglePause(job: Job) {
    busy = job.job_id;
    try {
      if (job.status === "paused") {
        await unpauseJob(job.job_id);
        notifications.push({ kind: "info", title: "Job resumed" });
      } else {
        await pauseJob(job.job_id);
        notifications.push({ kind: "info", title: "Job paused" });
      }
      await refresh();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = "";
    }
  }

  async function changePriority(job: Job, value: number) {
    try {
      await setJobPriority(job.job_id, value);
      await refresh();
    } catch (reason) {
      error = errorMessage(reason);
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
      <h2 class="text-lg font-semibold text-white">{i18n.t("jobs_title")}</h2>
      <p class="mt-1 text-xs text-neutral-500">{i18n.t("jobs_subtitle")}</p>
    </div>
    <div class="flex items-center gap-2">
      <input
        bind:value={query}
        type="search"
        placeholder={i18n.t("search_jobs")}
        aria-label="Search jobs"
        class="w-56 rounded-xl border border-neutral-700 bg-neutral-950 px-3 py-1.5 text-xs text-neutral-200 placeholder:text-neutral-600 focus:border-sky-500/50 focus:outline-none"
      />
      <button
        type="button"
        onclick={() => void refresh()}
        class="rounded-xl border border-white/10 px-3 py-1.5 text-xs text-neutral-300 hover:border-sky-500/40 hover:text-sky-200"
      >{i18n.t("refresh")}</button>
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
      {i18n.t("no_jobs")}
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
            <p class="text-[11px] text-neutral-500">{i18n.t("next")}: <span class="text-neutral-300">{jobNextAction(job)}</span></p>
            <div class="flex flex-wrap gap-1.5">
              {#if job.status === "waiting_approval"}
                <button type="button" class="rounded-lg bg-amber-400/15 px-2.5 py-1 text-[11px] font-medium text-amber-200 ring-1 ring-inset ring-amber-400/25 hover:bg-amber-400/20" onclick={() => onreview?.(job)}>{i18n.t("review")}</button>
              {:else if job.status === "failed" || job.status === "cancelled"}
                <button type="button" disabled={busy === job.job_id} class="rounded-lg bg-sky-500/15 px-2.5 py-1 text-[11px] font-medium text-sky-200 ring-1 ring-inset ring-sky-400/25 hover:bg-sky-500/20 disabled:opacity-40" onclick={() => void retry(job)}>
                  {busy === job.job_id ? "…" : i18n.t("retry")}
                </button>
              {:else if job.status === "succeeded"}
                {#if job.result?.artifacts && Object.keys(job.result.artifacts).length}
                  <button type="button" class="rounded-lg border border-white/10 px-2.5 py-1 text-[11px] text-neutral-300 hover:text-sky-200" onclick={() => onopentimeline?.(job)}>Open in Timeline</button>
                {/if}
              {/if}
              <label class="flex items-center gap-1 text-[10px] text-neutral-500">
                {i18n.t("priority")}
                <input
                  type="number"
                  min="-100"
                  max="100"
                  value={job.priority ?? 0}
                  onchange={(event) => void changePriority(job, Number(event.currentTarget.value))}
                  class="w-14 rounded border border-neutral-700 bg-neutral-950 px-1 py-0.5 text-[10px] text-neutral-200"
                  aria-label={`Priority for ${jobDisplayName(job)}`}
                />
              </label>
              {#if ["running", "queued"].includes(job.status)}
                <button type="button" disabled={busy === job.job_id} class="rounded-lg border border-white/10 px-2.5 py-1 text-[11px] text-neutral-300 disabled:opacity-40" onclick={() => void togglePause(job)}>{i18n.t("pause")}</button>
              {:else if job.status === "paused"}
                <button type="button" disabled={busy === job.job_id} class="rounded-lg border border-sky-500/30 px-2.5 py-1 text-[11px] text-sky-200 disabled:opacity-40" onclick={() => void togglePause(job)}>{i18n.t("resume")}</button>
              {/if}
              {#if ["running", "queued"].includes(job.status)}
                {#if confirmCancel === job.job_id}
                  <button type="button" class="rounded-lg border border-rose-400/30 bg-rose-500/10 px-2.5 py-1 text-[11px] text-rose-200" onclick={() => void cancel(job)}>{i18n.t("confirm_cancel")}</button>
                  <button type="button" class="rounded-lg border border-white/10 px-2.5 py-1 text-[11px] text-neutral-400" onclick={() => (confirmCancel = "")}>{i18n.t("keep")}</button>
                {:else}
                  <button type="button" class="rounded-lg border border-rose-500/20 px-2.5 py-1 text-[11px] text-rose-300 hover:border-rose-400/40" onclick={() => (confirmCancel = job.job_id)}>{i18n.t("cancel")}</button>
                {/if}
              {/if}
            </div>
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</section>
