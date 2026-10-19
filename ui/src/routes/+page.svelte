<script lang="ts">
  import { modules, statusStyles } from "$lib/modules";
  import "../app.css";

  const speakingModules = modules.filter((item) => item.enabled && item.status === "dirty");
</script>

<svelte:head>
  <title>VideoFlow — Rack</title>
  <meta
    name="description"
    content="Local, non-destructive video pre-edit pipeline."
  />
</svelte:head>

<div class="mx-auto flex min-h-screen max-w-5xl flex-col gap-6 px-4 py-8">
  <header class="rounded-2xl border border-neutral-800 bg-neutral-900/60 p-5">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <p class="text-xs font-semibold uppercase tracking-[0.2em] text-sky-400">VideoFlow</p>
        <h1 class="mt-1 text-2xl font-semibold tracking-tight">Rack scaffold</h1>
        <p class="mt-2 max-w-2xl text-sm text-neutral-400">
          Static shell for the sequential pre-edit pipeline. The engine is specified; this page is
          not wired to it yet.
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <button
          type="button"
          disabled
          class="rounded-lg border border-dashed border-neutral-700 px-4 py-2 text-sm text-neutral-400"
        >
          Drop media
        </button>
        <select
          aria-label="Preset"
          disabled
          class="rounded-lg border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm text-neutral-300"
        >
          <option>youtube-talking-head</option>
        </select>
        <button
          type="button"
          disabled
          class="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white opacity-60"
        >
          Run pipeline
        </button>
      </div>
    </div>

    <div class="mt-5">
      <div class="flex items-center justify-between text-xs text-neutral-400">
        <span>Project: none</span>
        <span>{speakingModules.length} modules would run</span>
      </div>
      <div class="mt-2 h-2 overflow-hidden rounded-full bg-neutral-800">
        <div class="h-full w-1/3 rounded-full bg-sky-500/70"></div>
      </div>
    </div>
  </header>

  <section aria-label="Pipeline modules" class="card-grid">
    {#each modules as module}
      <article
        class="rounded-xl border border-neutral-800 bg-neutral-900/50"
        data-module={module.id}
      >
        <div class="flex flex-wrap items-center gap-3 p-4">
          <span class="w-8 text-xs font-mono text-neutral-500">{module.index}</span>
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <h2 class="text-sm font-semibold">{module.name}</h2>
              <span
                class="rounded-full px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ring-1 {statusStyles[
                  module.status
                ]}"
              >
                {module.status}
              </span>
            </div>
            <p class="mt-1 text-xs text-neutral-400">{module.summary}</p>
          </div>
          <label class="flex items-center gap-2 text-xs text-neutral-400">
            <span class="sr-only">Enable {module.name}</span>
            <input
              type="checkbox"
              checked={module.enabled}
              disabled
              class="h-4 w-4 rounded border-neutral-600 bg-neutral-800"
            />
            Enabled
          </label>
          <button
            type="button"
            disabled
            class="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-400"
          >
            Run this block
          </button>
        </div>

        <details class="border-t border-neutral-800">
          <summary
            class="cursor-pointer px-4 py-2 text-xs font-medium text-neutral-400 hover:text-neutral-200"
          >
            Parameters
          </summary>
          <div class="grid gap-2 px-4 pb-4 sm:grid-cols-3">
            {#each module.settings as setting}
              <div class="rounded-lg bg-neutral-950/60 p-3">
                <p class="text-[11px] uppercase tracking-wide text-neutral-500">
                  {setting.label}
                </p>
                <p class="mt-1 text-sm text-neutral-200">{setting.value}</p>
              </div>
            {/each}
          </div>
        </details>
      </article>
    {/each}
  </section>

  <section class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-5">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 class="text-sm font-semibold">Inspector</h2>
        <p class="mt-1 text-xs text-neutral-400">
          Kept text, struck retakes, and removed silence. Word overrides arrive with the live
          transcript.
        </p>
      </div>
      <span class="rounded-full bg-neutral-800 px-3 py-1 text-[11px] text-neutral-400">
        No transcript loaded
      </span>
    </div>
    <div class="mt-4 space-y-2 text-sm">
      <p class="text-neutral-200">
        The first sentence is kept.
        <span class="text-rose-400 line-through">A failed attempt is struck through.</span>
        <span class="text-neutral-500"> [silence removed] </span>
      </p>
      <p class="text-xs text-neutral-500">
        This is sample text. The live inspector highlights the kept take and marks any sentence the
        retake guard restored.
      </p>
    </div>
  </section>

  <footer class="pb-4 text-xs text-neutral-500">
    <p>
      Scaffold only. Engines, exports, and API wiring are specified in the documentation and tracked
      as expected failures in the test suite.
    </p>
  </footer>
</div>
