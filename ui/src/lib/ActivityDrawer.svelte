<script lang="ts">
  import { focusTrap } from "$lib/a11y";
  import { cancelAllJobs, cancelJob, deleteJob, errorMessage, type Job } from "$lib/api";
  import { formatDateTime } from "$lib/format";
  import { portal } from "$lib/portal";
  import { jobDisplayName, jobNextAction } from "$lib/jobsView";
  import { i18n } from "$lib/i18n.svelte";

  type Changed = () => void;

  let {
    open = false,
    jobs = [],
    onclose,
    onopenjobs,
    onchanged
  }: {
    open?: boolean;
    jobs?: Job[];
    onclose: () => void;
    onopenjobs: () => void;
    onchanged?: Changed;
  } = $props();

  let busy = $state("");
  let error = $state("");

  const attention = $derived(jobs.filter((job) => ["waiting_approval", "failed"].includes(job.status)));
  const running = $derived(jobs.filter((job) => job.status === "running"));
  const queued = $derived(jobs.filter((job) => job.status === "queued"));
  const recent = $derived(
    jobs
      .filter((job) => ["succeeded", "cancelled"].includes(job.status))
      .slice(0, 4)
  );
  const finished = $derived(
    jobs.filter((job) => ["succeeded", "failed", "cancelled"].includes(job.status))
  );

  const sections = $derived([
    { title: "Needs attention", items: attention, tone: "text-amber-200" },
    { title: "Running", items: running, tone: "text-sky-200" },
    { title: "Queued", items: queued, tone: "text-neutral-300" },
    { title: "Recently finished", items: recent, tone: "text-emerald-200" }
  ]);

  async function cancel(job: Job, force = false) {
    busy = job.job_id;
    error = "";
    try {
      await cancelJob(job.job_id, force);
      await onchanged?.();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = "";
    }
  }

  async function remove(job: Job) {
    busy = job.job_id;
    error = "";
    try {
      await deleteJob(job.job_id, true);
      await onchanged?.();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = "";
    }
  }

  async function stopAll() {
    busy = "all";
    error = "";
    try {
      await cancelAllJobs(true);
      await onchanged?.();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = "";
    }
  }

  async function clearFinished() {
    busy = "clear";
    error = "";
    try {
      await Promise.allSettled(finished.map((job) => deleteJob(job.job_id)));
      await onchanged?.();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = "";
    }
  }
</script>

{#if open}
  <div class="fixed inset-0 z-[1000]" role="presentation" use:portal>
    <button type="button" class="absolute inset-0 bg-black/40" aria-label="Close activity" onclick={onclose}></button>
    <aside
      class="absolute right-0 top-0 flex h-full w-[min(24rem,100vw)] flex-col overflow-hidden border-l border-neutral-800 bg-neutral-950 shadow-2xl shadow-black/50"
      use:focusTrap
      aria-label="Activity drawer"
      data-testid="activity-drawer"
    >
      <header class="flex items-center justify-between border-b border-neutral-800 px-4 py-3">
        <div>
          <p class="text-sm font-medium text-white">Activity</p>
          <p class="mt-0.5 text-[11px] text-neutral-500">{running.length} running · {queued.length} queued · {attention.length} need attention</p>
        </div>
        <button type="button" class="rounded-lg border border-white/10 px-2 py-1 text-[11px] text-neutral-400 hover:text-neutral-100" onclick={onclose}>{i18n.t("close")}</button>
      </header>
      <div class="flex-1 space-y-4 overflow-auto p-3" aria-live="polite">
        {#if error}
          <p class="rounded-lg border border-rose-500/30 bg-rose-950/30 px-3 py-2 text-[10px] text-rose-200">{error}</p>
        {/if}
        {#each sections as section}
          {#if section.items.length}
            <section>
              <h3 class={`px-1 text-[10px] font-semibold uppercase tracking-wide ${section.tone}`}>{section.title}</h3>
              <ul class="mt-1.5 space-y-1.5">
                {#each section.items as job (job.job_id)}
                  <li class="rounded-xl border border-neutral-800 bg-white/[0.02] px-3 py-2">
                    <p class="truncate text-xs font-medium text-neutral-200">{jobDisplayName(job)}</p>
                    <p class="mt-0.5 truncate text-[11px] text-neutral-500">{job.message || job.stage}</p>
                    <div class="mt-1.5 flex items-center justify-between gap-2 text-[10px] text-neutral-500">
                      <span>{jobNextAction(job)}</span>
                      <span class="font-mono">{formatDateTime(job.created_at)}</span>
                    </div>
                    <div class="mt-2 flex flex-wrap justify-end gap-1.5">
                      {#if ["running", "queued", "waiting_approval", "paused"].includes(job.status)}
                        <button type="button" disabled={busy === job.job_id} class="rounded-lg border border-white/10 px-2 py-1 text-[10px] text-neutral-300 disabled:opacity-40" onclick={() => void cancel(job)}>{i18n.t("cancel")}</button>
                        <button type="button" disabled={busy === job.job_id} class="rounded-lg border border-rose-500/30 bg-rose-500/10 px-2 py-1 text-[10px] text-rose-200 disabled:opacity-40" onclick={() => void remove(job)}>Force stop</button>
                      {:else}
                        <button type="button" disabled={busy === job.job_id} class="rounded-lg border border-white/10 px-2 py-1 text-[10px] text-neutral-400 disabled:opacity-40" onclick={() => void remove(job)}>{i18n.t("dismiss")}</button>
                      {/if}
                    </div>
                  </li>
                {/each}
              </ul>
            </section>
          {/if}
        {/each}
        {#if jobs.length === 0}
          <p class="rounded-xl border border-dashed border-neutral-800 px-3 py-6 text-center text-xs text-neutral-500">
            No jobs yet. Run a recipe to populate the activity list.
          </p>
        {/if}
      </div>
      <footer class="border-t border-neutral-800 p-3">
        {#if running.length || queued.length || attention.length}
          <button type="button" disabled={busy === "all"} class="mb-2 w-full rounded-xl border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-xs font-medium text-rose-200 disabled:opacity-40" onclick={() => void stopAll()}>
            {busy === "all" ? "Stopping…" : "Stop all"}
          </button>
        {/if}
        {#if finished.length}
          <button type="button" disabled={busy === "clear"} class="mb-2 w-full rounded-xl border border-white/10 px-3 py-2 text-xs text-neutral-400 hover:text-neutral-100 disabled:opacity-40" onclick={() => void clearFinished()}>
            {busy === "clear" ? "Clearing…" : `Clear finished (${finished.length})`}
          </button>
        {/if}
        <button type="button" class="w-full rounded-xl bg-sky-500/15 px-3 py-2 text-xs font-medium text-sky-200 ring-1 ring-inset ring-sky-400/20 hover:bg-sky-500/20" onclick={onopenjobs}>
          {i18n.t("open_jobs")}
        </button>
      </footer>
    </aside>
  </div>
{/if}
