<script lang="ts">
  import { onMount } from "svelte";
  import { loadArtifactJson } from "$lib/artifactData";

  let {
    jobId,
    title = "Documentary pipeline"
  }: {
    jobId: string;
    title?: string;
  } = $props();

  let script = $state<Record<string, any> | null>(null);
  let factcheck = $state<Record<string, any> | null>(null);
  let units = $state<Record<string, any> | null>(null);
  let licenses = $state<Record<string, any> | null>(null);

  const sections = $derived((script?.sections ?? []) as Array<Record<string, any>>);
  const storyboard = $derived((units?.units ?? []) as Array<Record<string, any>>);
  const claims = $derived((factcheck?.claims ?? []) as Array<Record<string, any>>);

  onMount(() => {
    void Promise.all([
      loadArtifactJson(jobId, "script_json").then((value) => (script = value)),
      loadArtifactJson(jobId, "factcheck").then((value) => (factcheck = value)),
      loadArtifactJson(jobId, "storyboard_units").then((value) => (units = value)),
      loadArtifactJson(jobId, "assets_licenses").then((value) => (licenses = value))
    ]);
  });
</script>

<div class="space-y-4" data-testid="documentary-overview">
  <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
    <p class="vf-label text-sky-300/80">{title}</p>
    <div class="mt-3 grid gap-3 md:grid-cols-4">
      <div class="rounded-xl border border-white/10 bg-black/20 px-3 py-2"><p class="vf-label">Script</p><p class="mt-1 text-[length:var(--vf-text-sm)] text-neutral-100">{sections.length} sections</p></div>
      <div class="rounded-xl border border-white/10 bg-black/20 px-3 py-2"><p class="vf-label">Units</p><p class="mt-1 text-[length:var(--vf-text-sm)] text-neutral-100">{storyboard.length}</p></div>
      <div class="rounded-xl border border-white/10 bg-black/20 px-3 py-2"><p class="vf-label">Claims</p><p class="mt-1 text-[length:var(--vf-text-sm)] text-neutral-100">{claims.length}</p></div>
      <div class="rounded-xl border border-white/10 bg-black/20 px-3 py-2"><p class="vf-label">Licenses</p><p class="mt-1 text-[length:var(--vf-text-sm)] text-neutral-100">{licenses?.entries?.length ?? 0}</p></div>
    </div>
  </section>

  <div class="grid gap-4 lg:grid-cols-2">
    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
      <p class="vf-label">Script and research</p>
      {#if sections.length}
        <ol class="mt-3 max-h-80 space-y-2 overflow-auto">
          {#each sections.slice(0, 14) as section, index}
            <li class="rounded-lg border border-neutral-800 bg-neutral-950/40 px-3 py-2">
              <p class="text-[length:var(--vf-text-xs)] font-medium text-neutral-200">{index + 1}. {section.title || "Section"}</p>
              <p class="mt-1 line-clamp-2 text-[length:var(--vf-text-2xs)] leading-5 text-neutral-500">{section.narration || ""}</p>
              <p class="mt-1 text-[length:var(--vf-text-2xs)] text-neutral-600">{section.visual || ""}</p>
            </li>
          {/each}
        </ol>
      {:else}
        <p class="mt-3 text-[length:var(--vf-text-xs)] text-neutral-500">The dual script appears after research approval.</p>
      {/if}
    </section>

    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
      <p class="vf-label">Unit storyboard</p>
      {#if storyboard.length}
        <ol class="mt-3 max-h-80 space-y-2 overflow-auto">
          {#each storyboard.slice(0, 14) as unit}
            <li class="flex items-start justify-between gap-2 rounded-lg border border-neutral-800 bg-neutral-950/40 px-3 py-2">
              <div class="min-w-0">
                <p class="truncate text-[length:var(--vf-text-xs)] text-neutral-200">{unit.title || unit.unit_id}</p>
                <p class="mt-1 text-[length:var(--vf-text-2xs)] text-neutral-500">{unit.layout || "layout"} · {unit.visual || ""}</p>
              </div>
              <span class="shrink-0 font-mono text-[length:var(--vf-text-2xs)] text-neutral-500">{unit.start_sec}–{unit.end_sec}s</span>
            </li>
          {/each}
        </ol>
      {:else}
        <p class="mt-3 text-[length:var(--vf-text-xs)] text-neutral-500">Units appear after the timeline is built.</p>
      {/if}
    </section>
  </div>

  {#if claims.length}
    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
      <p class="vf-label">Fact-check</p>
      <ul class="mt-3 grid gap-2 md:grid-cols-2">
        {#each claims.slice(0, 10) as claim}
          <li class="rounded-lg border border-neutral-800 bg-neutral-950/40 px-3 py-2 text-[length:var(--vf-text-xs)] text-neutral-300">
            <span class={claim.status === "supported" ? "text-emerald-300" : "text-amber-300"}>{claim.status}</span> · {claim.claim}
          </li>
        {/each}
      </ul>
    </section>
  {/if}
</div>
