<script lang="ts">
  import { onMount } from "svelte";
  import Icon from "$lib/ui/Icon.svelte";
  import { artifactUrl, loadArtifactJson } from "$lib/artifactData";

  let {
    jobId,
    artifacts
  }: {
    jobId: string;
    artifacts: Record<string, string>;
  } = $props();

  let script = $state<Record<string, any> | null>(null);
  let factcheck = $state<Record<string, any> | null>(null);
  let units = $state<Record<string, any> | null>(null);
  let manifest = $state<Record<string, any> | null>(null);
  let qa = $state<Record<string, any> | null>(null);
  let audioQa = $state<Record<string, any> | null>(null);
  let words = $state<Record<string, any> | null>(null);

  const sections = $derived((script?.sections ?? []) as Array<Record<string, any>>);
  const storyboard = $derived((units?.units ?? []) as Array<Record<string, any>>);
  const scenes = $derived((manifest?.scenes ?? []) as Array<Record<string, any>>);
  const issues = $derived((qa?.issues ?? []) as Array<Record<string, any>>);
  const claims = $derived((factcheck?.claims ?? []) as Array<Record<string, any>>);

  onMount(() => {
    void Promise.all([
      loadArtifactJson(jobId, "script_json").then((value) => (script = value)),
      loadArtifactJson(jobId, "factcheck").then((value) => (factcheck = value)),
      loadArtifactJson(jobId, "storyboard_units").then((value) => (units = value)),
      loadArtifactJson(jobId, "motion_manifest").then((value) => (manifest = value)),
      loadArtifactJson(jobId, "qa_frames").then((value) => (qa = value)),
      loadArtifactJson(jobId, "audio_qa").then((value) => (audioQa = value)),
      loadArtifactJson(jobId, "narration_words").then((value) => (words = value))
    ]);
  });
</script>

<div class="space-y-4" data-testid="synthetic-overview">
  <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
    <div class="flex items-start justify-between gap-3">
      <div>
        <p class="vf-label text-sky-300/80">Synthetic Code Studio</p>
        <h3 class="mt-1 text-[length:var(--vf-text-lg)] font-semibold text-neutral-100">Script → voice → scenes</h3>
      </div>
      <span class="rounded-full border border-white/10 px-2.5 py-1 text-[length:var(--vf-text-2xs)] text-neutral-400">{sections.length} sections · {scenes.length} scenes</span>
    </div>
    <div class="mt-4 grid gap-3 md:grid-cols-3">
      <div class="rounded-xl border border-white/10 bg-black/20 px-3 py-2">
        <p class="vf-label">Script</p>
        <p class="mt-1 text-[length:var(--vf-text-sm)] text-neutral-100">{sections.length} sections</p>
      </div>
      <div class="rounded-xl border border-white/10 bg-black/20 px-3 py-2">
        <p class="vf-label">Narration</p>
        <p class="mt-1 text-[length:var(--vf-text-sm)] text-neutral-100">{(words?.words ?? []).length} words</p>
      </div>
      <div class="rounded-xl border border-white/10 bg-black/20 px-3 py-2">
        <p class="vf-label">QA</p>
        <p class="mt-1 text-[length:var(--vf-text-sm)] text-neutral-100">{qa ? `${qa.critical_count ?? 0} critical` : "pending"}</p>
      </div>
    </div>
  </section>

  <div class="grid gap-4 lg:grid-cols-2">
    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
      <div class="flex items-center justify-between gap-2">
        <p class="vf-label">Script</p>
        <span class="text-[length:var(--vf-text-2xs)] text-neutral-500">{factcheck?.unsupported_count ?? 0} unsupported claims</span>
      </div>
      {#if sections.length}
        <ol class="mt-3 max-h-72 space-y-2 overflow-auto">
          {#each sections.slice(0, 12) as section, index}
            <li class="rounded-lg border border-neutral-800 bg-neutral-950/40 px-3 py-2">
              <p class="text-[length:var(--vf-text-xs)] font-medium text-neutral-200">{index + 1}. {section.title || "Section"}</p>
              <p class="mt-1 line-clamp-2 text-[length:var(--vf-text-2xs)] leading-5 text-neutral-500">{section.narration || ""}</p>
              <p class="mt-1 text-[length:var(--vf-text-2xs)] text-neutral-600">Visual: {section.visual || "—"}</p>
            </li>
          {/each}
        </ol>
      {:else}
        <p class="mt-3 text-[length:var(--vf-text-xs)] text-neutral-500">Script artifacts appear after the script step.</p>
      {/if}
    </section>

    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
      <p class="vf-label">Voice and timing</p>
      {#if artifacts.audio_narration || artifacts.audio_mix}
        <audio controls preload="metadata" src={artifactUrl(jobId, artifacts.audio_narration ? "audio_narration" : "audio_mix")} class="mt-3 w-full"></audio>
      {:else}
        <p class="mt-3 text-[length:var(--vf-text-xs)] text-neutral-500">Narration audio appears after synthesis.</p>
      {/if}
      <div class="mt-3 grid gap-2 sm:grid-cols-2">
        <div class="rounded-lg border border-white/10 px-3 py-2">
          <p class="vf-label">Words</p>
          <p class="mt-1 text-[length:var(--vf-text-sm)] text-neutral-100">{(words?.words ?? []).length}</p>
        </div>
        <div class="rounded-lg border border-white/10 px-3 py-2">
          <p class="vf-label">Audio QA</p>
          <p class="mt-1 text-[length:var(--vf-text-sm)] text-neutral-100">{audioQa?.integrated_lufs ?? "—"} LUFS</p>
        </div>
      </div>
    </section>

    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
      <p class="vf-label">Timed storyboard</p>
      {#if storyboard.length}
        <ol class="mt-3 max-h-72 space-y-2 overflow-auto">
          {#each storyboard.slice(0, 14) as unit}
            <li class="flex items-start justify-between gap-2 rounded-lg border border-neutral-800 bg-neutral-950/40 px-3 py-2">
              <div class="min-w-0">
                <p class="truncate text-[length:var(--vf-text-xs)] text-neutral-200">{unit.title || unit.unit_id}</p>
                <p class="mt-1 text-[length:var(--vf-text-2xs)] text-neutral-500">{unit.layout || "layout"} · {unit.visual || "visual"}</p>
              </div>
              <span class="shrink-0 font-mono text-[length:var(--vf-text-2xs)] text-neutral-500">{unit.start_sec}–{unit.end_sec}s</span>
            </li>
          {/each}
        </ol>
      {:else}
        <p class="mt-3 text-[length:var(--vf-text-xs)] text-neutral-500">Units appear after narration alignment.</p>
      {/if}
    </section>

    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
      <p class="vf-label">Rendered scenes</p>
      {#if scenes.length}
        <ul class="mt-3 grid max-h-72 gap-2 overflow-auto sm:grid-cols-2">
          {#each scenes.slice(0, 16) as scene}
            <li class="rounded-lg border border-neutral-800 bg-neutral-950/40 px-3 py-2">
              <p class="truncate text-[length:var(--vf-text-xs)] text-neutral-200">{scene.scene_id}</p>
              <p class="mt-1 line-clamp-1 text-[length:var(--vf-text-2xs)] text-neutral-500">{scene.title || scene.unit_id}</p>
              <p class="mt-1 font-mono text-[length:var(--vf-text-2xs)] text-neutral-600">{scene.duration_sec}s</p>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="mt-3 text-[length:var(--vf-text-xs)] text-neutral-500">Scenes appear after rendering.</p>
      {/if}
    </section>
  </div>

  {#if issues.length || claims.length}
    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
      <p class="vf-label">Review queue</p>
      <ul class="mt-3 space-y-2">
        {#each issues.slice(0, 8) as issue}
          <li class="flex items-start gap-2 rounded-lg border border-amber-400/15 bg-amber-950/10 px-3 py-2 text-[length:var(--vf-text-xs)] text-amber-100/80">
            <Icon name="warning" size={14} class="mt-0.5 text-amber-300" />
            <span>{issue.message || issue.kind} <span class="text-amber-200/50">· {issue.start_sec ?? 0}s</span></span>
          </li>
        {/each}
        {#each claims.filter((item) => item.status !== "supported").slice(0, 6) as claim}
          <li class="flex items-start gap-2 rounded-lg border border-rose-400/15 bg-rose-950/10 px-3 py-2 text-[length:var(--vf-text-xs)] text-rose-100/80">
            <Icon name="info" size={14} class="mt-0.5 text-rose-300" />
            <span>{claim.claim}</span>
          </li>
        {/each}
      </ul>
    </section>
  {/if}
</div>
