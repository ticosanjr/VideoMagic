<script lang="ts">
  import { onMount } from "svelte";
  import ErrorBanner from "$lib/ErrorBanner.svelte";
  import PathPicker from "$lib/PathPicker.svelte";
  import {
    deleteSchedule,
    errorMessage,
    listRecipes,
    listSchedules,
    runScheduleNow,
    saveSchedule,
    type RecipeSchedule,
    type RecipeSummary
  } from "$lib/api";

  let schedules = $state<RecipeSchedule[]>([]);
  let recipes = $state<RecipeSummary[]>([]);
  let error = $state("");
  let status = $state("");
  let busy = $state("");
  let picker = $state<"source" | "output" | "watch" | null>(null);
  let draft = $state<RecipeSchedule>(blank());

  function blank(): RecipeSchedule {
    return {
      id: Math.random().toString(16).slice(2, 12),
      kind: "interval",
      recipe_id: "",
      source: "",
      output: "",
      interval_seconds: 3600,
      watch_dir: "",
      pattern: "*.mp4",
      enabled: true,
      last_run: "",
      status: "idle",
      last_error: "",
      created_at: "",
      seen_paths: []
    };
  }

  async function refresh() {
    try {
      schedules = await listSchedules();
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function save() {
    busy = "save";
    error = "";
    status = "";
    try {
      const saved = await saveSchedule(draft);
      status = `Schedule ${saved.id} saved.`;
      draft = blank();
      await refresh();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = "";
    }
  }

  async function runNow(schedule: RecipeSchedule) {
    busy = schedule.id;
    error = "";
    try {
      const updated = await runScheduleNow(schedule.id);
      status = `Schedule ${schedule.id}: ${updated.status}.`;
      await refresh();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = "";
    }
  }

  async function remove(schedule: RecipeSchedule) {
    busy = schedule.id;
    try {
      await deleteSchedule(schedule.id);
      if (draft.id === schedule.id) draft = blank();
      status = `Schedule ${schedule.id} removed.`;
      await refresh();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = "";
    }
  }

  function pick(path: string) {
    if (picker === "source") draft.source = path;
    else if (picker === "output") draft.output = path;
    else if (picker === "watch") draft.watch_dir = path;
    picker = null;
  }

  onMount(async () => {
    try {
      recipes = await listRecipes();
      if (!draft.recipe_id) draft.recipe_id = recipes[0]?.id ?? "";
    } catch (reason) {
      error = errorMessage(reason);
    }
    await refresh();
  });
</script>

<div class="space-y-4" data-testid="automation-panel">
  <ErrorBanner message={error} onDismiss={() => (error = "")} testId="automation-error" />

  <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div>
        <h2 class="text-sm font-semibold text-white">Automation</h2>
        <p class="mt-1 text-xs text-neutral-500">
          Persistent recipe schedules and watch folders. The local scheduler polls every 20 seconds.
        </p>
      </div>
      <button type="button" onclick={() => void refresh()} class="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300 hover:border-sky-500">Refresh</button>
    </div>
    {#if status}<p class="mt-2 text-[11px] text-emerald-300" role="status">{status}</p>{/if}
  </section>

  <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
    <h3 class="text-xs font-semibold text-neutral-100">New schedule</h3>
    <div class="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      <label class="text-[10px] uppercase tracking-wide text-neutral-500">Kind
        <select bind:value={draft.kind} class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100">
          <option value="interval">Every N seconds</option>
          <option value="once">Once</option>
          <option value="watch">Watch folder</option>
        </select>
      </label>
      <label class="text-[10px] uppercase tracking-wide text-neutral-500">Recipe
        <select bind:value={draft.recipe_id} class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100">
          {#each recipes as recipe}<option value={recipe.id}>{recipe.name}</option>{/each}
        </select>
      </label>
      {#if draft.kind === "interval"}
        <label class="text-[10px] uppercase tracking-wide text-neutral-500">Interval (s)
          <input type="number" min="30" step="30" bind:value={draft.interval_seconds} class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100" />
        </label>
      {/if}
      {#if draft.kind !== "watch"}
        <label class="text-[10px] uppercase tracking-wide text-neutral-500 sm:col-span-2">Source
          <div class="mt-1 flex gap-1">
            <input bind:value={draft.source} placeholder="/media/source.mp4" class="min-w-0 flex-1 rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" />
            <button type="button" onclick={() => (picker = "source")} class="rounded-lg border border-neutral-700 px-2 text-[10px] text-neutral-300">Pick</button>
          </div>
        </label>
      {:else}
        <label class="text-[10px] uppercase tracking-wide text-neutral-500 sm:col-span-2">Watch folder
          <div class="mt-1 flex gap-1">
            <input bind:value={draft.watch_dir} placeholder="/media/inbox" class="min-w-0 flex-1 rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" />
            <button type="button" onclick={() => (picker = "watch")} class="rounded-lg border border-neutral-700 px-2 text-[10px] text-neutral-300">Pick</button>
          </div>
        </label>
        <label class="text-[10px] uppercase tracking-wide text-neutral-500">Pattern
          <input bind:value={draft.pattern} class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" />
        </label>
      {/if}
      <label class="text-[10px] uppercase tracking-wide text-neutral-500 sm:col-span-2">Output
        <div class="mt-1 flex gap-1">
          <input bind:value={draft.output} placeholder="/media/out" class="min-w-0 flex-1 rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" />
          <button type="button" onclick={() => (picker = "output")} class="rounded-lg border border-neutral-700 px-2 text-[10px] text-neutral-300">Pick</button>
        </div>
      </label>
      <label class="flex items-end gap-2 pb-1 text-[10px] text-neutral-400">
        <input type="checkbox" bind:checked={draft.enabled} class="h-3.5 w-3.5 rounded border-neutral-700 bg-neutral-800" />
        enabled
      </label>
    </div>
    <button type="button" onclick={() => void save()} disabled={busy === "save" || !draft.recipe_id} class="mt-3 rounded-lg border border-sky-500/40 px-3 py-1.5 text-[11px] text-sky-200 disabled:opacity-40">
      {busy === "save" ? "Saving…" : "Save schedule"}
    </button>
  </section>

  <section class="space-y-2">
    {#each schedules as schedule}
      <article class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-3">
        <div class="flex flex-wrap items-center gap-2">
          <span class="rounded bg-neutral-800 px-2 py-0.5 text-[9px] uppercase text-neutral-400">{schedule.kind}</span>
          <span class="font-mono text-[10px] text-neutral-500">{schedule.id}</span>
          <span class="text-xs text-sky-200">{schedule.recipe_id}</span>
          <span class={`rounded-full px-2 py-0.5 text-[9px] ${schedule.enabled ? "bg-emerald-500/10 text-emerald-300" : "bg-neutral-800 text-neutral-500"}`}>{schedule.enabled ? schedule.status : "disabled"}</span>
          <span class="ml-auto flex gap-1">
            <button type="button" onclick={() => (draft = { ...schedule, seen_paths: [...schedule.seen_paths] })} class="rounded border border-neutral-700 px-2 py-1 text-[10px] text-neutral-300">Edit</button>
            <button type="button" onclick={() => void runNow(schedule)} disabled={Boolean(busy)} class="rounded border border-sky-500/40 px-2 py-1 text-[10px] text-sky-200 disabled:opacity-40">Run now</button>
            <button type="button" onclick={() => void remove(schedule)} disabled={Boolean(busy)} class="rounded border border-rose-500/30 px-2 py-1 text-[10px] text-rose-300 disabled:opacity-40">Delete</button>
          </span>
        </div>
        {#if schedule.kind === "watch"}
          <p class="mt-1 break-all font-mono text-[10px] text-neutral-500">{schedule.watch_dir} / {schedule.pattern} → {schedule.output}</p>
        {:else}
          <p class="mt-1 break-all font-mono text-[10px] text-neutral-500">{schedule.source} → {schedule.output}</p>
        {/if}
        <p class="mt-1 text-[10px] text-neutral-600">
          Last run: {schedule.last_run || "never"}{#if schedule.kind === "interval"} · every {schedule.interval_seconds}s{/if}
          {#if schedule.seen_paths.length} · {schedule.seen_paths.length} seen{/if}
        </p>
        {#if schedule.last_error}<p class="mt-1 break-all text-[10px] text-rose-300">{schedule.last_error}</p>{/if}
      </article>
    {/each}
    {#if !schedules.length}<p class="rounded-2xl border border-dashed border-neutral-800 p-4 text-center text-xs text-neutral-500">No schedules yet.</p>{/if}
  </section>
</div>

<PathPicker
  open={picker !== null}
  mode={picker === "output" || picker === "watch" ? "directory" : "file"}
  title={picker === "source" ? "Choose source video" : picker === "watch" ? "Choose watch folder" : "Choose output folder"}
  extensions={picker === "source" ? ["mp4", "mov", "mkv", "webm", "m4v", "avi"] : []}
  onclose={() => (picker = null)}
  onselect={pick}
/>
