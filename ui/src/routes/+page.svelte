<script lang="ts">
  import { onMount } from "svelte";
  import {
    cancelJob,
    createJob,
    errorMessage,
    getJob,
    getSystem,
    type Job,
    type SystemInfo
  } from "$lib/api";
  import { modules, statusStyles, type RackModule, type Status } from "$lib/modules";
  import "../app.css";

  let system = $state<SystemInfo | null>(null);
  let source = $state("");
  let output = $state("");
  let noiseDb = $state(-30);
  let minSilence = $state(400);
  let jcut = $state(true);
  let zoom = $state(true);
  let job = $state<Job | null>(null);
  let error = $state("");
  let busy = $state(false);
  let timer: ReturnType<typeof setTimeout> | undefined;

  onMount(() => {
    getSystem()
      .then((payload) => (system = payload))
      .catch((reason) => (error = errorMessage(reason)));
    return () => clearTimeout(timer);
  });

  const terminal = (status: string | undefined) =>
    status === "succeeded" || status === "failed" || status === "cancelled";

  const active = $derived(job?.status === "queued" || job?.status === "running");

  function suggestOutput() {
    if (!source.trim()) return;
    const trimmed = source.replace(/\.[^./\\]+$/, "");
    output = `${trimmed}-videoflow`;
  }

  async function start() {
    error = "";
    if (!source.trim() || !output.trim()) {
      error = "Source and output are required.";
      return;
    }
    busy = true;
    clearTimeout(timer);
    try {
      job = await createJob({
        source: source.trim(),
        output: output.trim(),
        noise_db: Number(noiseDb),
        min_silence_ms: Number(minSilence),
        jcut,
        lcut: false,
        zooms: zoom,
        dialect: "1.9"
      });
      schedule();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  function schedule() {
    clearTimeout(timer);
    if (!job || terminal(job.status)) return;
    timer = setTimeout(refresh, 600);
  }

  async function refresh() {
    if (!job) return;
    try {
      job = await getJob(job.job_id);
      if (!terminal(job.status)) {
        schedule();
      }
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function cancel() {
    if (!job) return;
    try {
      job = await cancelJob(job.job_id);
      schedule();
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  function statusFor(module: RackModule): Status {
    if (!module.portable) return "bypassed";
    if (module.id === "jl_cuts" && !jcut) return "bypassed";
    if (module.id === "zooms" && !zoom) return "bypassed";
    const current = job?.status;
    if (!current) return "dirty";
    const stage = job?.stage ?? "";
    if (current === "queued" || current === "running") {
      if ((stage === "probe" || stage === "extract") && module.id === "ingest") return "running";
      if (stage === "vad" && module.id === "vad") return "running";
      if (stage === "timeline" && (module.id === "jl_cuts" || module.id === "zooms"))
        return "running";
      if ((stage === "export" || stage === "state") && module.id === "export") return "running";
      return "dirty";
    }
    if (current === "succeeded") return "cached";
    if (current === "failed") {
      const stageModule: Record<string, string> = {
        probe: "ingest",
        extract: "ingest",
        vad: "vad",
        timeline: "jl_cuts",
        export: "export",
        state: "export"
      };
      return stageModule[stage] === module.id ? "failed" : "dirty";
    }
    return "dirty";
  }

  const artifacts = $derived(
    job?.result?.artifacts ? Object.entries(job.result.artifacts) : []
  );
</script>

<svelte:head>
  <title>VideoFlow — Rack</title>
  <meta name="description" content="Local, non-destructive video pre-edit pipeline." />
</svelte:head>

<div class="mx-auto flex min-h-screen max-w-6xl flex-col gap-6 px-4 py-8">
  <header class="rounded-2xl border border-neutral-800 bg-neutral-900/60 p-5">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <p class="text-xs font-semibold uppercase tracking-[0.2em] text-sky-400">VideoFlow</p>
        <h1 class="mt-1 text-2xl font-semibold tracking-tight">Portable rack</h1>
        <p class="mt-2 max-w-2xl text-sm text-neutral-400">
          Model-free pre-edit: silence detection, J-cuts, punch-ins, and three NLE exports. The
          neural modules are visible but bypassed in this build.
        </p>
      </div>
      <div class="text-right text-xs text-neutral-400">
        <p class="font-mono text-neutral-300">{system?.version ?? "offline"}</p>
        <p class="mt-1">FFmpeg: {system?.ffmpeg ? "ready" : "missing"}</p>
        <p>Home: <span class="font-mono text-[11px]">{system?.home ?? "—"}</span></p>
      </div>
    </div>
  </header>

  <section class="rounded-2xl border border-sky-500/30 bg-sky-500/5 p-5">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 class="text-sm font-semibold text-sky-200">Portable run</h2>
        <p class="mt-1 text-xs text-neutral-400">
          Paths are checked against the server allowlist. Output is a project folder with state and
          exports.
        </p>
      </div>
      <span class="rounded-full bg-neutral-950/60 px-3 py-1 text-[11px] text-neutral-400">
        {active ? `${job?.stage} · ${job?.progress}%` : "idle"}
      </span>
    </div>

    <div class="mt-4 grid gap-3 md:grid-cols-2">
      <label class="block text-xs text-neutral-400">
        Source video
        <input
          bind:value={source}
          placeholder="/media/interview.mp4"
          class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100 placeholder:text-neutral-600 focus:border-sky-500 focus:outline-none"
        />
      </label>
      <label class="block text-xs text-neutral-400">
        Output project
        <span class="mt-1 flex gap-2">
          <input
            bind:value={output}
            placeholder="/projects/interview-edit"
            class="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100 placeholder:text-neutral-600 focus:border-sky-500 focus:outline-none"
          />
          <button
            type="button"
            onclick={suggestOutput}
            class="shrink-0 rounded-lg border border-neutral-700 px-2 py-1 text-[11px] text-neutral-400 hover:text-neutral-200"
          >
            Default
          </button>
        </span>
      </label>
    </div>

    <div class="mt-4 flex flex-wrap gap-2">
      {#each [
        { id: "youtube", label: "YouTube", noise: -30, silence: 400, cuts: true, zoom: true },
        { id: "lecture", label: "Lecture", noise: -30, silence: 700, cuts: false, zoom: false },
        { id: "shorts", label: "Shorts", noise: -30, silence: 250, cuts: true, zoom: true }
      ] as preset}
        <button
          type="button"
          onclick={() => {
            noiseDb = preset.noise;
            minSilence = preset.silence;
            jcut = preset.cuts;
            zoom = preset.zoom;
          }}
          class="rounded-full border border-neutral-700 px-3 py-1 text-[11px] text-neutral-300 hover:border-sky-500 hover:text-sky-300"
        >
          {preset.label}
        </button>
      {/each}
    </div>

    <div class="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      <label class="block text-xs text-neutral-400">
        Noise threshold (dB)
        <input
          type="number"
          bind:value={noiseDb}
          min={-80}
          max={-5}
          step={1}
          class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm"
        />
      </label>
      <label class="block text-xs text-neutral-400">
        Minimum silence (ms)
        <input
          type="number"
          bind:value={minSilence}
          min={100}
          max={5000}
          step={50}
          class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm"
        />
      </label>
      <label class="flex items-center gap-2 self-end rounded-lg border border-neutral-800 px-3 py-2 text-xs text-neutral-300">
        <input type="checkbox" bind:checked={jcut} class="h-4 w-4" />
        J-cuts
      </label>
      <label class="flex items-center gap-2 self-end rounded-lg border border-neutral-800 px-3 py-2 text-xs text-neutral-300">
        <input type="checkbox" bind:checked={zoom} class="h-4 w-4" />
        Punch-ins
      </label>
    </div>

    <div class="mt-4 flex flex-wrap items-center gap-2">
      <button
        type="button"
        onclick={start}
        disabled={busy || active}
        class="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-40"
      >
        {active ? "Running…" : "Run pipeline"}
      </button>
      <button
        type="button"
        onclick={cancel}
        disabled={!active}
        class="rounded-lg border border-neutral-700 px-4 py-2 text-sm text-neutral-300 disabled:opacity-40"
      >
        Cancel
      </button>
      {#if job}
        <span class="text-xs text-neutral-500">job {job.job_id.slice(0, 8)}</span>
      {/if}
    </div>

    {#if job}
      <div class="mt-4">
        <div class="h-2 overflow-hidden rounded-full bg-neutral-800">
          <div
            class="h-full rounded-full bg-sky-500 transition-all"
            style={`width: ${job.progress}%`}
          ></div>
        </div>
        <p class="mt-2 text-xs text-neutral-400" aria-live="polite">
          {job.status} · {job.stage} · {job.message}
        </p>
        {#if job.error}
          <pre class="mt-3 overflow-x-auto rounded-lg bg-rose-950/40 p-3 text-xs text-rose-300">{JSON.stringify(
              job.error,
              null,
              2
            )}</pre>
        {/if}
        {#if artifacts.length > 0}
          <div class="mt-3 grid gap-2 sm:grid-cols-3">
            {#each artifacts as [target, path]}
              <a
                class="rounded-lg border border-neutral-800 bg-neutral-950/60 p-3 hover:border-emerald-500/50"
                href={`/api/v1/jobs/${job.job_id}/artifacts/${target}`}
                download
              >
                <p class="text-[11px] uppercase tracking-wide text-neutral-500">{target}</p>
                <p class="mt-1 break-all font-mono text-[11px] text-emerald-300">{path}</p>
                <p class="mt-1 text-[10px] text-neutral-500">Download</p>
              </a>
            {/each}
          </div>
        {/if}
      </div>
    {/if}

    {#if error}
      <p class="mt-3 rounded-lg bg-rose-950/40 p-3 text-xs text-rose-300">{error}</p>
    {/if}
  </section>

  <section aria-label="Pipeline modules" class="card-grid">
    {#each modules as module}
      {@const status = statusFor(module)}
      <article class="rounded-xl border border-neutral-800 bg-neutral-900/50" data-module={module.id}>
        <div class="flex flex-wrap items-center gap-3 p-4">
          <span class="w-8 text-xs font-mono text-neutral-500">{module.index}</span>
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <h2 class="text-sm font-semibold">{module.name}</h2>
              <span
                class="rounded-full px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ring-1 {statusStyles[
                  status
                ]}"
              >
                {status}
              </span>
              {#if !module.portable}
                <span class="rounded-full bg-neutral-800 px-2 py-0.5 text-[10px] uppercase text-neutral-500">
                  later
                </span>
              {/if}
            </div>
            <p class="mt-1 text-xs text-neutral-400">{module.summary}</p>
          </div>
          <label class="flex items-center gap-2 text-xs text-neutral-500">
            <input
              type="checkbox"
              checked={module.portable && (module.id !== "jl_cuts" || jcut) && (module.id !== "zooms" || zoom)}
              disabled
              class="h-4 w-4 rounded border-neutral-700 bg-neutral-800"
            />
            Enabled
          </label>
          <button
            type="button"
            disabled
            title="Per-block runs arrive with the rack runner"
            class="rounded-lg border border-neutral-800 px-3 py-1.5 text-xs text-neutral-500"
          >
            Run this block
          </button>
        </div>

        <details class="border-t border-neutral-800">
          <summary class="cursor-pointer px-4 py-2 text-xs font-medium text-neutral-400 hover:text-neutral-200">
            Parameters
          </summary>
          <div class="grid gap-2 px-4 pb-4 sm:grid-cols-3">
            {#each module.settings as setting}
              <div class="rounded-lg bg-neutral-950/60 p-3">
                <p class="text-[11px] uppercase tracking-wide text-neutral-500">{setting.label}</p>
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
          The portable path has no transcript yet. Silence and retake decisions are visible in
          <span class="font-mono text-neutral-300">project_state.json</span> and
          <span class="font-mono text-neutral-300">run.json</span>.
        </p>
      </div>
      <span class="rounded-full bg-neutral-800 px-3 py-1 text-[11px] text-neutral-400">
        {job?.result ? `${job.result.video_segment_count ?? 0} segments` : "No run"}
      </span>
    </div>
    {#if job?.result}
      <div class="mt-4 grid gap-2 sm:grid-cols-3 text-xs text-neutral-300">
        <p>Speech intervals: {job.result.speech_interval_count ?? "—"}</p>
        <p>Segments: {job.result.video_segment_count ?? "—"}</p>
        <p>Elapsed: {job.result.elapsed_seconds?.toFixed(2) ?? "—"} s</p>
      </div>
      {#if job.result.warnings?.length}
        <ul class="mt-3 list-disc pl-5 text-xs text-amber-300">
          {#each job.result.warnings as warning}
            <li>{warning}</li>
          {/each}
        </ul>
      {/if}
    {:else}
      <p class="mt-4 text-xs text-neutral-500">
        Start a run to populate the segment count and warnings. Word-level kept/cut highlighting
        arrives with transcription.
      </p>
    {/if}
  </section>

  <footer class="pb-4 text-xs text-neutral-500">
    <p>
      Local only. The server binds to 127.0.0.1. Neural modules, retakes, and shorts are specified
      and tracked as expected failures in the test suite.
    </p>
  </footer>
</div>
