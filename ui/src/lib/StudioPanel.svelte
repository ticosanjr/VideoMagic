<script lang="ts">
  import { analyzeShortLlm, type Job, type ShortClip, type ShortVisionAnalysis } from "$lib/api";

  let {
    job,
    config,
    onEdit
  }: {
    job: Job | null;
    config: any;
    onEdit: (index: number, short: ShortClip) => void;
  } = $props();

  type StudioTab = "ai" | "timeline" | "keyframes" | "tracks" | "transitions";
  let tab = $state<StudioTab>("ai");
  let index = $state(0);
  let baseUrl = $state("");
  let model = $state("gpt-4o-mini");
  let busy = $state(false);
  let error = $state("");
  let analysis = $state<ShortVisionAnalysis | null>(null);

  const shorts = $derived(job?.result?.shorts ?? []);
  const selected = $derived(shorts[index] ?? null);

  async function analyze() {
    if (!job || !selected || busy) return;
    busy = true;
    error = "";
    try {
      const response = await analyzeShortLlm(job.job_id, index, {
        base_url: baseUrl.trim() || undefined,
        model,
        allow_external_services: Boolean(config.allow_external_services),
        allowed_external_hosts: String(config.allowed_external_hosts || "")
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean)
      });
      analysis = response.analysis;
    } catch (reason) {
      error = String(reason instanceof Error ? reason.message : reason);
    } finally {
      busy = false;
    }
  }
</script>

<section class="space-y-3">
  <div class="flex flex-wrap gap-1 rounded-2xl border border-neutral-800 bg-neutral-900/60 p-1" role="tablist" aria-label="Studio sections">
    {#each [["ai", "AI Analysis"], ["timeline", "Timeline"], ["keyframes", "Keyframes"], ["tracks", "Tracks"], ["transitions", "Transitions"]] as [id, label]}
      <button
        type="button"
        role="tab"
        aria-selected={tab === id}
        onclick={() => (tab = id as StudioTab)}
        class={`rounded-xl px-3 py-2 text-xs font-medium ${tab === id ? "bg-sky-500/15 text-sky-200 ring-1 ring-inset ring-sky-400/20" : "text-neutral-400 hover:text-neutral-200"}`}
      >
        {label}
      </button>
    {/each}
  </div>

  {#if !job || !shorts.length}
    <div class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4 text-xs text-neutral-500">
      Run a project with Shorts to use the Studio.
    </div>
  {:else if tab === "ai"}
    <div class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
      <div class="flex flex-wrap items-end gap-2">
        <label class="text-xs text-neutral-300">
          <span class="block text-[10px] uppercase tracking-wide text-neutral-500">Short</span>
          <select value={index} onchange={(event) => (index = Number(event.currentTarget.value))} class="mt-1 rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100">
            {#each shorts as clip, i}<option value={i}>{i + 1}. {clip.title}</option>{/each}
          </select>
        </label>
        <label class="flex-1 text-xs text-neutral-300">
          <span class="block text-[10px] uppercase tracking-wide text-neutral-500">Vision base URL</span>
          <input type="text" value={baseUrl} oninput={(event) => (baseUrl = event.currentTarget.value)} placeholder="https://api.openai.com/v1" class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[11px] text-neutral-100" />
        </label>
        <label class="text-xs text-neutral-300">
          <span class="block text-[10px] uppercase tracking-wide text-neutral-500">Model</span>
          <input type="text" value={model} oninput={(event) => (model = event.currentTarget.value)} class="mt-1 rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[11px] text-neutral-100" />
        </label>
        <button type="button" onclick={analyze} disabled={busy || !config.allow_external_services} class="rounded-lg border border-violet-500/40 bg-violet-500/10 px-3 py-2 text-xs text-violet-200 disabled:opacity-40">
          {busy ? "Analyzing…" : "Analyze frames"}
        </button>
      </div>
      {#if !config.allow_external_services}<p class="mt-2 text-[10px] text-amber-300">Enable external services in Providers.</p>{/if}
      {#if error}<p class="mt-2 text-[10px] text-rose-300">{error}</p>{/if}
      {#if analysis}
        <div class="mt-3 grid gap-2 text-xs text-neutral-300 sm:grid-cols-2">
          <p>Mood: <span class="text-neutral-100">{analysis.mood}</span></p>
          <p>Scene: <span class="text-neutral-100">{analysis.scene}</span></p>
          <p>People: <span class="text-neutral-100">{analysis.people}</span></p>
          <p>Energy: <span class="text-neutral-100">{analysis.energy}</span></p>
          <p>Objects: <span class="text-neutral-100">{analysis.objects.join(", ") || "—"}</span></p>
          <p>Confidence: <span class="text-neutral-100">{analysis.confidence}</span></p>
        </div>
        <p class="mt-2 text-[10px] text-neutral-500">{analysis.evidence}</p>
      {/if}
    </div>
  {:else if tab === "timeline"}
    <div class="space-y-2">
      {#each shorts as clip, i}
        <div class="flex items-center gap-2 rounded-xl border border-neutral-800 bg-neutral-900/50 p-3 text-xs">
          <span class="font-mono text-neutral-500">{String(i + 1).padStart(2, "0")}</span>
          <div class="min-w-0 flex-1">
            <p class="truncate text-neutral-200">{clip.title}</p>
            <p class="text-[10px] text-neutral-500">{clip.duration_sec.toFixed(1)} s · {clip.aspect_ratio ?? "9:16"} · {clip.crop_focus_x ?? 0.5}</p>
          </div>
          <button type="button" onclick={() => onEdit(i, clip)} class="rounded-lg border border-neutral-700 px-2 py-1 text-[10px] text-neutral-300 hover:text-sky-200">Edit</button>
        </div>
      {/each}
    </div>
  {:else if tab === "keyframes"}
    <div class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4 text-xs text-neutral-400">
      <p>Reframe mode: <span class="text-neutral-200">{config.shorts_reframe_mode}</span></p>
      <p class="mt-2">Selected Short crop focus: <span class="text-neutral-200">{selected?.crop_focus_x ?? 0.5}</span> / <span class="text-neutral-200">{selected?.crop_focus_y ?? 0.5}</span></p>
      <p class="mt-2 text-[10px] text-neutral-500">Per-clip trim and reframe are available in Timeline → Edit. Keyframed NLE zoom export is still pending.</p>
    </div>
  {:else if tab === "tracks"}
    <div class="grid gap-2 rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4 text-xs text-neutral-400 sm:grid-cols-2">
      <p>Watermark: <span class="text-neutral-200">{config.overlay_enabled ? config.overlay_asset : "off"}</span></p>
      <p>Music: <span class="text-neutral-200">{config.music_enabled ? config.music_asset : "off"}</span></p>
      <p>Intro: <span class="text-neutral-200">{config.intro_enabled ? config.intro_asset : "off"}</span></p>
      <p>Outro: <span class="text-neutral-200">{config.outro_enabled ? config.outro_asset : "off"}</span></p>
    </div>
  {:else}
    <div class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4 text-xs text-neutral-400">
      <p>Audio crossfade: <span class="text-neutral-200">{config.crossfade_ms} ms</span></p>
      <p class="mt-1">Audio fade in/out: <span class="text-neutral-200">{config.fade_in_ms}/{config.fade_out_ms} ms</span></p>
      <p class="mt-1">Audio energy boost: <span class="text-neutral-200">{config.shorts_audio_energy_boost ? "on" : "off"}</span></p>
      <p class="mt-1">Scene boost: <span class="text-neutral-200">{config.shorts_scene_change_boost ? "on" : "off"}</span></p>
      <p class="mt-2 text-[10px] text-neutral-500">Video transition tracks and keyframed NLE exports are still pending.</p>
    </div>
  {/if}
</section>
