<script lang="ts">
  import { onMount } from "svelte";
  import LogDrawer from "$lib/LogDrawer.svelte";
  import StatusIcon from "$lib/StatusIcon.svelte";
  import {
    cancelJob,
    createJob,
    errorMessage,
    getJob,
    getJobState,
    getSystem,
    listJobs,
    type Job,
    type JobState,
    type JobStage,
    type SystemInfo
  } from "$lib/api";
  import { elapsedMs, formatDateTime, formatDuration, statusText } from "$lib/format";
  import {
    defaultConfig,
    modules,
    statusLabel,
    statusStyles,
    type ConfigKey,
    type RackModule,
    type Status
  } from "$lib/modules";
  import "../app.css";

  let system = $state<SystemInfo | null>(null);
  let source = $state("");
  let output = $state("");
  let transcript = $state("");
  let config = $state<any>({ ...defaultConfig });
  let job = $state<Job | null>(null);
  let jobState = $state<JobState | null>(null);
  let history = $state<Job[]>([]);
  let error = $state("");
  let busy = $state(false);
  let logOpen = $state(false);
  let logModule = $state<string | null>(null);
  let overrides = $state<Record<number, "keep" | "discard">>({});
  let now = $state(Date.now());
  let timer: ReturnType<typeof setTimeout> | undefined;
  let clock: ReturnType<typeof setInterval> | undefined;

  onMount(() => {
    getSystem()
      .then((payload) => (system = payload))
      .catch((reason) => (error = errorMessage(reason)));
    void refreshHistory();
    clock = setInterval(() => (now = Date.now()), 1000);
    return () => {
      clearTimeout(timer);
      clearInterval(clock);
    };
  });

  const terminal = (status: string | undefined) =>
    status === "succeeded" || status === "failed" || status === "cancelled";

  const active = $derived(job?.status === "queued" || job?.status === "running");

  const jobDuration = $derived(
    job ? job.duration_ms ?? elapsedMs(job.started_at, job.finished_at, now) : null
  );

  const artifacts = $derived(
    job?.result?.artifacts ? Object.entries(job.result.artifacts) : []
  );

  function suggestOutput() {
    if (!source.trim()) return;
    const trimmed = source.replace(/\.[^./\\]+$/, "");
    output = `${trimmed}-videoflow`;
  }

  function setField(key: ConfigKey, value: unknown) {
    config[key] = value;
  }

  function toggleTarget(target: string) {
    const current: string[] = Array.isArray(config.export_targets)
      ? [...config.export_targets]
      : [];
    const next = current.includes(target)
      ? current.filter((item) => item !== target)
      : [...current, target];
    if (next.length > 0) config.export_targets = next;
  }

  function applyPreset(name: "youtube" | "lecture" | "shorts") {
    if (name === "youtube") {
      config.noise_db = -30;
      config.min_silence_ms = 400;
      config.jcut = true;
      config.lcut = false;
      config.zooms = true;
    } else if (name === "lecture") {
      config.noise_db = -30;
      config.min_silence_ms = 700;
      config.jcut = false;
      config.lcut = false;
      config.zooms = false;
    } else {
      config.noise_db = -30;
      config.min_silence_ms = 250;
      config.jcut = true;
      config.lcut = false;
      config.zooms = true;
    }
  }

  function buildPayload() {
    return {
      source: source.trim(),
      output: output.trim(),
      noise_db: Number(config.noise_db),
      min_silence_ms: Number(config.min_silence_ms),
      min_speech_ms: Number(config.min_speech_ms),
      jcut: Boolean(config.jcut),
      lcut: Boolean(config.lcut),
      offset_ms: Number(config.offset_ms),
      crossfade_ms: Number(config.crossfade_ms),
      handle_check: Boolean(config.handle_check),
      zooms: Boolean(config.zooms),
      zoom_mode: String(config.zoom_mode),
      punch_in_scale: Number(config.punch_in_scale),
      anchor_point: String(config.anchor_point),
      progressive_zoom: Boolean(config.progressive_zoom),
      pan_direction: String(config.pan_direction),
      dialect: String(config.dialect) as "1.9" | "1.10",
      export_targets: config.export_targets as string[],
      transcript: transcript.trim() || null,
      cull_retakes: Boolean(config.cull_retakes),
      strictness: String(config.strictness),
      retake_strategy: String(config.retake_strategy),
      context_window: Number(config.context_window),
      llm_base_url: String(config.llm_base_url || "").trim() || null,
      llm_model: String(config.llm_model || "qwen2.5:7b-instruct"),
      shorts: Boolean(config.shorts),
      shorts_count: Number(config.shorts_count),
      shorts_min_sec: Number(config.shorts_min_sec),
      shorts_max_sec: Number(config.shorts_max_sec),
      shorts_subtitles: Boolean(config.shorts_subtitles),
      transcribe: Boolean(config.transcribe),
      asr_base_url: String(config.asr_base_url || "").trim() || null,
      asr_model: String(config.asr_model || "whisper-1"),
      asr_language: String(config.asr_language || "pt"),
      whisper_model: String(config.whisper_model || "").trim() || null,
      overrides: Object.entries(overrides).map(([sentenceId, action]) => ({
        sentence_id: Number(sentenceId),
        action
      }))
    };
  }

  function setOverride(sentenceId: number, action: "keep" | "discard") {
    const next = { ...overrides };
    if (next[sentenceId] === action) delete next[sentenceId];
    else next[sentenceId] = action;
    overrides = next;
  }

  function effectiveAction(sentenceId: number): "keep" | "discard" {
    if (overrides[sentenceId]) return overrides[sentenceId];
    return jobState?.retake_culls.includes(sentenceId) ? "discard" : "keep";
  }

  async function applyOverrides() {
    if (!jobState || Object.keys(overrides).length === 0 || active) return;
    await start();
  }

  async function start() {
    error = "";
    if (!source.trim() || !output.trim()) {
      error = "Source and output are required.";
      return;
    }
    if (config.cull_retakes && !transcript.trim()) {
      error = "Retake culling needs an SRT transcript path.";
      return;
    }
    busy = true;
    jobState = null;
    clearTimeout(timer);
    try {
      job = await createJob(buildPayload());
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
      } else {
        if (job.status === "succeeded") await loadState();
        await refreshHistory();
      }
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function refreshHistory() {
    try {
      history = await listJobs();
    } catch {
      // The history panel is optional; the run flow stays usable.
    }
  }

  async function loadState() {
    if (!job) return;
    try {
      jobState = await getJobState(job.job_id);
    } catch {
      jobState = null;
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

  async function selectJob(entry: Job) {
    job = entry;
    jobState = null;
    error = "";
    overrides = {};
    source = entry.source;
    output = entry.output;
    transcript = entry.options.transcript ?? "";
    if (entry.status === "succeeded") await loadState();
  }

  function stageFor(moduleId: string): JobStage | undefined {
    return job?.stages?.find((item) => item.module === moduleId);
  }

  function statusFor(module: RackModule): Status {
    if (!module.portable) return "bypassed";
    if (module.id === "transcribe" && !transcript && !config.transcribe) return "bypassed";
    if (module.id === "shorts" && (!config.shorts || !transcript)) return "bypassed";
    if (module.id === "retakes" && (!config.cull_retakes || !transcript)) return "bypassed";
    if (module.id === "jl_cuts" && !config.jcut && !config.lcut) return "bypassed";
    if (module.id === "zooms" && !config.zooms) return "bypassed";
    const stage = stageFor(module.id);
    if (stage) return stage.status as Status;
    if (job?.status === "succeeded") return "bypassed";
    return "pending";
  }

  function progressFor(module: RackModule): number {
    const status = statusFor(module);
    if (status === "succeeded" || status === "cached") return 100;
    if (status === "bypassed" || status === "pending" || status === "cancelled") return 0;
    return stageFor(module.id)?.progress ?? 0;
  }

  function durationFor(module: RackModule): number | null {
    const stage = stageFor(module.id);
    if (!stage) return null;
    if (stage.duration_ms !== null) return stage.duration_ms;
    if (stage.status === "running") return elapsedMs(stage.started_at, null, now);
    return null;
  }

  function isEnabled(module: RackModule): boolean {
    if (!module.portable) return false;
    if (!module.toggleKey) return true;
    if (module.id === "jl_cuts") return Boolean(config.jcut || config.lcut);
    return Boolean(config[module.toggleKey]);
  }

  function toggleModule(module: RackModule) {
    if (!module.toggleKey) return;
    if (module.id === "jl_cuts") {
      const next = !(config.jcut || config.lcut);
      config.jcut = next;
      if (!next) config.lcut = false;
      return;
    }
    config[module.toggleKey] = !config[module.toggleKey];
  }

  function barClass(status: Status): string {
    if (status === "failed") return "bg-rose-500";
    if (status === "succeeded" || status === "cached") return "bg-emerald-500";
    if (status === "running") return "bg-sky-500";
    if (status === "blocked" || status === "dirty") return "bg-amber-500";
    return "bg-neutral-600";
  }

  function openLog(module?: string) {
    logModule = module ?? null;
    logOpen = true;
  }

  function sentenceText(id: number): string {
    return jobState?.transcript.find((item) => item.id === id)?.text ?? `sentence ${id}`;
  }

  const targetOptions = [
    { id: "resolve", label: "Resolve" },
    { id: "premiere", label: "Premiere" },
    { id: "kdenlive", label: "Kdenlive" }
  ];
</script>

<svelte:head>
  <title>VideoFlow — Rack</title>
  <meta name="description" content="Local, non-destructive video pre-edit pipeline." />
</svelte:head>

<div class="mx-auto flex min-h-screen max-w-7xl flex-col gap-5 px-4 py-6">
  <header class="flex flex-wrap items-start justify-between gap-4">
    <div>
      <p class="text-xs font-semibold uppercase tracking-[0.22em] text-sky-400">VideoFlow</p>
      <h1 class="mt-1 text-3xl font-semibold tracking-tight">Rack & telemetry</h1>
      <p class="mt-2 max-w-3xl text-sm text-neutral-400">
        Per-block progress, timing, logs, SRT/ASR transcripts, manual overrides, and vertical
        Shorts. Future modules stay visible and marked <span class="text-neutral-300">later</span>.
      </p>
    </div>
    <div class="flex flex-wrap items-center gap-3">
      <div class="text-right text-xs text-neutral-400">
        <p class="font-mono text-neutral-300">{system?.version ?? "offline"}</p>
        <p class="mt-1">FFmpeg: {system?.ffmpeg ? "ready" : "missing"}</p>
        <p>Home: <span class="font-mono text-[11px]">{system?.home ?? "—"}</span></p>
      </div>
      <button
        type="button"
        onclick={() => openLog()}
        disabled={!job}
        class="rounded-xl border border-neutral-700 bg-neutral-900 px-4 py-2 text-sm text-neutral-300 hover:border-sky-500 disabled:opacity-40"
      >
        Global log
        {#if job}<span class="ml-1 text-[11px] text-neutral-500">{job.log_count}</span>{/if}
      </button>
    </div>
  </header>

  <section class="rounded-2xl border border-neutral-800 bg-neutral-900/60 p-5">
    <div class="grid gap-3 lg:grid-cols-3">
      <label class="block text-xs text-neutral-400 lg:col-span-2">
        Source video
        <input
          bind:value={source}
          placeholder="/media/interview.mp4"
          class="mt-1 w-full rounded-xl border border-neutral-700 bg-neutral-950 px-3 py-2.5 text-sm text-neutral-100 placeholder:text-neutral-600 focus:border-sky-500 focus:outline-none"
        />
      </label>
      <label class="block text-xs text-neutral-400">
        Output project
        <span class="mt-1 flex gap-2">
          <input
            bind:value={output}
            placeholder="/projects/interview-edit"
            class="w-full rounded-xl border border-neutral-700 bg-neutral-950 px-3 py-2.5 text-sm text-neutral-100 placeholder:text-neutral-600 focus:border-sky-500 focus:outline-none"
          />
          <button
            type="button"
            onclick={suggestOutput}
            class="shrink-0 rounded-xl border border-neutral-700 px-2 py-1 text-[11px] text-neutral-400 hover:text-neutral-200"
          >
            Default
          </button>
        </span>
      </label>
      <label class="block text-xs text-neutral-400 lg:col-span-2">
        Transcript (optional SRT)
        <input
          bind:value={transcript}
          placeholder="/media/interview.srt"
          class="mt-1 w-full rounded-xl border border-neutral-700 bg-neutral-950 px-3 py-2.5 text-sm text-neutral-100 placeholder:text-neutral-600 focus:border-sky-500 focus:outline-none"
        />
      </label>
      <div class="flex flex-wrap items-end gap-2">
        {#each [
          { id: "youtube", label: "YouTube" },
          { id: "lecture", label: "Lecture" },
          { id: "shorts", label: "Shorts" }
        ] as preset}
          <button
            type="button"
            onclick={() => applyPreset(preset.id as "youtube" | "lecture" | "shorts")}
            class="rounded-full border border-neutral-700 px-3 py-1.5 text-[11px] text-neutral-300 hover:border-sky-500 hover:text-sky-300"
          >
            {preset.label}
          </button>
        {/each}
      </div>
    </div>

    <div class="mt-4 flex flex-wrap items-center gap-2">
      <button
        type="button"
        onclick={start}
        disabled={busy || active}
        class="rounded-xl bg-sky-600 px-5 py-2.5 text-sm font-medium text-white disabled:opacity-40"
      >
        {active ? "Running…" : "Run pipeline"}
      </button>
      <button
        type="button"
        onclick={cancel}
        disabled={!active}
        class="rounded-xl border border-neutral-700 px-4 py-2.5 text-sm text-neutral-300 disabled:opacity-40"
      >
        Cancel
      </button>
      {#if job}
        <span class="font-mono text-[11px] text-neutral-500">job {job.job_id.slice(0, 8)}</span>
      {/if}
    </div>

    {#if job}
      <div class="mt-4">
        <div
          class="h-2 overflow-hidden rounded-full bg-neutral-800"
          role="progressbar"
          aria-valuemin="0"
          aria-valuemax="100"
          aria-valuenow={job.progress}
        >
          <div
            class="h-full rounded-full bg-sky-500 transition-all"
            style={`width: ${job.progress}%`}
          ></div>
        </div>
        <div class="mt-3 grid gap-2 text-xs text-neutral-400 sm:grid-cols-4">
          <p class="flex items-center gap-2">
            <StatusIcon status={job.status === "queued" ? "pending" : job.status} />
            <span class="capitalize">{statusText(job.status)}</span>
          </p>
          <p>Started: {formatDateTime(job.started_at ?? job.created_at)}</p>
          <p>Duration: {formatDuration(jobDuration)}</p>
          <p>Stage: {job.stage}</p>
        </div>
        {#if job.error}
          <pre class="mt-3 overflow-x-auto rounded-xl bg-rose-950/40 p-3 text-xs text-rose-300">{JSON.stringify(
              job.error,
              null,
              2
            )}</pre>
        {/if}
      </div>
    {/if}

    {#if error}
      <p class="mt-3 rounded-xl bg-rose-950/40 p-3 text-xs text-rose-300">{error}</p>
    {/if}
  </section>

  <div class="grid gap-5 lg:grid-cols-[minmax(0,1fr)_310px]">
    <section aria-label="Pipeline modules" class="space-y-3">
      {#each modules as module}
        {@const status = statusFor(module)}
        {@const progress = progressFor(module)}
        {@const duration = durationFor(module)}
        {@const stage = stageFor(module.id)}
        <article class="rounded-2xl border border-neutral-800 bg-neutral-900/50" data-module={module.id}>
          <div class="p-4">
            <div class="flex flex-wrap items-center gap-3">
              <span class="w-8 font-mono text-xs text-neutral-500">{module.index}</span>
              <StatusIcon status={status} size={18} />
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-2">
                  <h2 class="text-sm font-semibold">{module.name}</h2>
                  <span
                    class="rounded-full px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ring-1 {statusStyles[
                      status
                    ]}"
                  >
                    {statusLabel[status]}
                  </span>
                  {#if module.tag}
                    <span class="rounded-full bg-neutral-800 px-2 py-0.5 text-[10px] uppercase text-neutral-500">
                      {module.tag}
                    </span>
                  {/if}
                </div>
                <p class="mt-1 text-xs text-neutral-400">{module.summary}</p>
              </div>
              {#if module.toggleKey}
                <label class="flex items-center gap-2 text-xs text-neutral-400">
                  <input
                    type="checkbox"
                    checked={isEnabled(module)}
                    disabled={!module.portable}
                    onchange={() => toggleModule(module)}
                    class="h-4 w-4 rounded border-neutral-700 bg-neutral-800"
                  />
                  {module.toggleLabel ?? "Enabled"}
                </label>
              {/if}
              <button
                type="button"
                onclick={() => openLog(module.id)}
                disabled={!job}
                class="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300 hover:border-sky-500 disabled:opacity-40"
              >
                Log
              </button>
            </div>

            <div class="mt-3 flex items-center gap-3">
              <div class="h-1.5 flex-1 overflow-hidden rounded-full bg-neutral-800">
                <div
                  class="h-full rounded-full transition-all {barClass(status)}"
                  style={`width: ${progress}%`}
                ></div>
              </div>
              <span class="w-10 text-right text-[11px] text-neutral-500">{progress}%</span>
            </div>
            <div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-neutral-500">
              <span>Started: {formatDateTime(stage?.started_at)}</span>
              <span>Duration: {formatDuration(duration)}</span>
              {#if stage?.message}<span class="truncate">{stage.message}</span>{/if}
            </div>
          </div>

          <details class="border-t border-neutral-800">
            <summary class="cursor-pointer px-4 py-2 text-xs font-medium text-neutral-400 hover:text-neutral-200">
              Parameters
            </summary>
            <div class="grid gap-3 px-4 pb-4 sm:grid-cols-2 lg:grid-cols-3">
              {#each module.fields as field}
                <div class="rounded-xl bg-neutral-950/60 p-3">
                  <div class="flex items-center justify-between gap-2">
                    <label class="text-[11px] uppercase tracking-wide text-neutral-500" for={`${module.id}-${field.key}`}>
                      {field.label}
                    </label>
                    {#if !field.implemented}
                      <span class="rounded bg-neutral-800 px-1.5 py-0.5 text-[9px] uppercase text-neutral-500">
                        later
                      </span>
                    {/if}
                  </div>
                  <div class="mt-2">
                    {#if field.type === "bool"}
                      <input
                        id={`${module.id}-${field.key}`}
                        type="checkbox"
                        checked={Boolean(config[field.key])}
                        disabled={!field.implemented}
                        onchange={(event) => setField(field.key, event.currentTarget.checked)}
                        class="h-4 w-4 rounded border-neutral-700 bg-neutral-800"
                      />
                    {:else if field.type === "number"}
                      <input
                        id={`${module.id}-${field.key}`}
                        type="number"
                        value={config[field.key]}
                        min={field.min}
                        max={field.max}
                        step={field.step}
                        disabled={!field.implemented}
                        oninput={(event) => setField(field.key, Number(event.currentTarget.value))}
                        class="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-sm text-neutral-100 disabled:opacity-50"
                      />
                    {:else if field.type === "select"}
                      <select
                        id={`${module.id}-${field.key}`}
                        value={config[field.key]}
                        disabled={!field.implemented}
                        onchange={(event) => setField(field.key, event.currentTarget.value)}
                        class="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-sm text-neutral-100 disabled:opacity-50"
                      >
                        {#each field.options ?? [] as option}
                          <option value={option.value}>{option.label}</option>
                        {/each}
                      </select>
                    {:else if field.type === "text"}
                      <input
                        id={`${module.id}-${field.key}`}
                        type="text"
                        value={config[field.key]}
                        disabled={!field.implemented}
                        oninput={(event) => setField(field.key, event.currentTarget.value)}
                        class="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-sm text-neutral-100 disabled:opacity-50"
                      />
                    {:else if field.type === "targets"}
                      <div class="flex flex-wrap gap-3">
                        {#each targetOptions as target}
                          <label class="flex items-center gap-1.5 text-xs text-neutral-300">
                            <input
                              type="checkbox"
                              checked={(config.export_targets as string[]).includes(target.id)}
                              onchange={() => toggleTarget(target.id)}
                              class="h-4 w-4 rounded border-neutral-700 bg-neutral-800"
                            />
                            {target.label}
                          </label>
                        {/each}
                      </div>
                    {:else}
                      <p class="text-sm text-neutral-400">{String(config[field.key])}</p>
                    {/if}
                  </div>
                  {#if field.help}
                    <p class="mt-2 text-[10px] leading-4 text-neutral-500">{field.help}</p>
                  {/if}
                </div>
              {/each}
            </div>
            {#if module.note}
              <p class="px-4 pb-4 text-[11px] leading-5 text-neutral-500">{module.note}</p>
            {/if}
          </details>
        </article>
      {/each}
    </section>

    <aside class="space-y-4">
      <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
        <h2 class="text-sm font-semibold">Run summary</h2>
        {#if job}
          <div class="mt-3 flex items-center gap-2 text-sm">
            <StatusIcon status={job.status === "queued" ? "pending" : job.status} size={18} />
            <span class="capitalize">{statusText(job.status)}</span>
          </div>
          <dl class="mt-3 space-y-2 text-xs text-neutral-400">
            <div><dt class="text-[10px] uppercase text-neutral-500">Started</dt><dd>{formatDateTime(job.started_at ?? job.created_at)}</dd></div>
            <div><dt class="text-[10px] uppercase text-neutral-500">Finished</dt><dd>{formatDateTime(job.finished_at)}</dd></div>
            <div><dt class="text-[10px] uppercase text-neutral-500">Duration</dt><dd>{formatDuration(jobDuration)}</dd></div>
            <div><dt class="text-[10px] uppercase text-neutral-500">Stages</dt><dd>{job.stages.filter((item) => item.status === "succeeded").length} ok · {job.stages.filter((item) => item.status === "failed").length} failed</dd></div>
          </dl>
          {#if artifacts.length > 0}
            <div class="mt-3 space-y-2">
              {#each artifacts as [target, path]}
                <a
                  class="block rounded-lg border border-neutral-800 bg-neutral-950/60 p-2 text-[11px] text-emerald-300 hover:border-emerald-500/50"
                  href={`/api/v1/jobs/${job.job_id}/artifacts/${target}`}
                  download
                >
                  <span class="block uppercase text-neutral-500">{target}</span>
                  <span class="break-all font-mono">{path}</span>
                </a>
              {/each}
            </div>
          {/if}
          {#if job.result?.shorts?.length}
            <div class="mt-3">
              <p class="text-[10px] uppercase tracking-wide text-neutral-500">Shorts</p>
              <div class="mt-2 space-y-2">
                {#each job.result.shorts as clip, index}
                  <a
                    class="block rounded-lg border border-neutral-800 bg-neutral-950/60 p-2 text-[11px] text-sky-300 hover:border-sky-500/50"
                    href={`/api/v1/jobs/${job.job_id}/shorts/${index}`}
                    download
                  >
                    <span class="block truncate">{clip.title}</span>
                    <span class="text-[10px] text-neutral-500">{clip.duration_sec.toFixed(1)} s · MP4</span>
                  </a>
                {/each}
              </div>
            </div>
          {/if}
        {:else}
          <p class="mt-3 text-xs text-neutral-500">Run the pipeline to see timing, logs, and artifacts.</p>
        {/if}
      </section>

      <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
        <h2 class="text-sm font-semibold">Recent jobs</h2>
        {#if history.length === 0}
          <p class="mt-2 text-xs text-neutral-500">No jobs yet.</p>
        {:else}
          <div class="mt-3 space-y-2">
            {#each history.slice(0, 6) as entry}
              <button
                type="button"
                onclick={() => selectJob(entry)}
                class="flex w-full items-center gap-2 rounded-lg border border-transparent px-2 py-2 text-left text-xs hover:border-neutral-700 hover:bg-neutral-950/60"
              >
                <StatusIcon status={entry.status === "queued" ? "pending" : entry.status} />
                <span class="min-w-0 flex-1">
                  <span class="block truncate text-neutral-300">{entry.source.split(/[\\/]/).pop()}</span>
                  <span class="block text-[10px] text-neutral-500">{formatDateTime(entry.created_at)} · {formatDuration(entry.duration_ms)}</span>
                </span>
              </button>
            {/each}
          </div>
        {/if}
      </section>

      <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4 text-xs text-neutral-400">
        <h2 class="text-sm font-semibold text-neutral-200">System</h2>
        <p class="mt-3">Version: <span class="font-mono text-neutral-300">{system?.version ?? "—"}</span></p>
        <p class="mt-1">FFmpeg: <span class="font-mono text-neutral-300">{system?.ffmpeg ?? "missing"}</span></p>
        <p class="mt-1">Home: <span class="break-all font-mono text-neutral-300">{system?.home ?? "—"}</span></p>
        <p class="mt-1">Roots: <span class="break-all font-mono text-neutral-300">{system?.allowed_roots.join(", ") || "—"}</span></p>
      </section>
    </aside>
  </div>

  <section class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-5">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 class="text-sm font-semibold">Inspector</h2>
        <p class="mt-1 text-xs text-neutral-400">
          Transcript and retake decisions from the current job.
        </p>
      </div>
      <span class="rounded-full bg-neutral-800 px-3 py-1 text-[11px] text-neutral-400">
        {job?.result ? `${job.result.video_segment_count ?? 0} segments` : "No run"}
      </span>
    </div>
    {#if jobState}
      <div class="mt-4 grid gap-2 text-xs text-neutral-300 sm:grid-cols-4">
        <p>Sentences: {jobState.transcript.length}</p>
        <p>Culled: {jobState.retake_culls.length}</p>
        <p>Restored: {jobState.retake_guard_restores.length}</p>
        <p>Overrides: {Object.keys(overrides).length}</p>
      </div>

      <div class="mt-4 flex flex-wrap items-center justify-between gap-2">
        <p class="text-[11px] uppercase tracking-wide text-neutral-500">Manual overrides</p>
        <button
          type="button"
          onclick={applyOverrides}
          disabled={Object.keys(overrides).length === 0 || active}
          class="rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40"
        >
          Apply overrides
        </button>
      </div>
      <div class="mt-2 max-h-80 space-y-1 overflow-auto rounded-xl border border-neutral-800 bg-neutral-950/50 p-2">
        {#each jobState.transcript.slice(0, 200) as sentence}
          {@const action = effectiveAction(sentence.id)}
          <div class="flex flex-wrap items-center gap-2 rounded-lg px-2 py-1.5 text-xs hover:bg-neutral-900/60">
            <span class="w-8 shrink-0 font-mono text-[10px] text-neutral-600">#{sentence.id}</span>
            <span class="min-w-0 flex-1 {action === 'discard' ? 'text-rose-300 line-through' : 'text-neutral-300'}">
              {sentence.text}
            </span>
            <button
              type="button"
              onclick={() => setOverride(sentence.id, "keep")}
              class="rounded px-2 py-0.5 text-[10px] {action === 'keep' ? 'bg-emerald-500/15 text-emerald-300' : 'text-neutral-500 hover:text-emerald-300'}"
            >
              Keep
            </button>
            <button
              type="button"
              onclick={() => setOverride(sentence.id, "discard")}
              class="rounded px-2 py-0.5 text-[10px] {action === 'discard' ? 'bg-rose-500/15 text-rose-300' : 'text-neutral-500 hover:text-rose-300'}"
            >
              Discard
            </button>
          </div>
        {/each}
      </div>
      {#if jobState.transcript.length > 200}
        <p class="mt-2 text-[10px] text-neutral-500">Showing the first 200 sentences.</p>
      {/if}
      {#if jobState.retake_guard_restores.length > 0}
        <div class="mt-4">
          <p class="text-[11px] uppercase tracking-wide text-neutral-500">Guard restorations</p>
          <ul class="mt-2 space-y-1 text-xs text-emerald-300">
            {#each jobState.retake_guard_restores as id}
              <li>{sentenceText(id)}</li>
            {/each}
          </ul>
        </div>
      {/if}
      {#if job?.result?.warnings?.length}
        <ul class="mt-3 list-disc pl-5 text-xs text-amber-300">
          {#each job.result.warnings as warning}
            <li>{warning}</li>
          {/each}
        </ul>
      {/if}
    {:else if job?.result}
      <div class="mt-4 grid gap-2 text-xs text-neutral-300 sm:grid-cols-3">
        <p>Speech intervals: {job.result.speech_interval_count ?? "—"}</p>
        <p>Segments: {job.result.video_segment_count ?? "—"}</p>
        <p>Elapsed: {job.result.elapsed_seconds?.toFixed(2) ?? "—"} s</p>
      </div>
    {:else}
      <p class="mt-4 text-xs text-neutral-500">
        Start a run to populate transcript decisions and warnings.
      </p>
    {/if}
  </section>

  <footer class="pb-4 text-xs text-neutral-500">
    <p>
      Local only. The server binds to 127.0.0.1. Every control shown is wired; future modules are
      marked later.
    </p>
  </footer>
</div>

<LogDrawer jobId={job?.job_id ?? null} module={logModule} open={logOpen} onclose={() => (logOpen = false)} />
