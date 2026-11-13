<script lang="ts">
  import { onMount } from "svelte";
  import Icon from "$lib/ui/Icon.svelte";
  import CalloutEditor from "$lib/workspaces/CalloutEditor.svelte";
  import { loadArtifactJson } from "$lib/artifactData";

  let {
    jobId
  }: {
    jobId: string;
  } = $props();

  let ocr = $state<Record<string, any> | null>(null);
  let tracks = $state<Record<string, any> | null>(null);
  let callouts = $state<Record<string, any> | null>(null);
  let qa = $state<Record<string, any> | null>(null);
  let licenses = $state<Record<string, any> | null>(null);

  const frames = $derived((ocr?.frames ?? []) as Array<Record<string, any>>);
  const tracked = $derived((tracks?.tracks ?? []) as Array<Record<string, any>>);
  const cards = $derived((callouts?.callouts ?? []) as Array<Record<string, any>>);
  const issues = $derived((qa?.issues ?? []) as Array<Record<string, any>>);

  onMount(() => {
    void Promise.all([
      loadArtifactJson(jobId, "vision_ocr").then((value) => (ocr = value)),
      loadArtifactJson(jobId, "vision_tracks").then((value) => (tracks = value)),
      loadArtifactJson(jobId, "motion_callouts").then((value) => (callouts = value)),
      loadArtifactJson(jobId, "qa_frames").then((value) => (qa = value)),
      loadArtifactJson(jobId, "assets_licenses").then((value) => (licenses = value))
    ]);
  });
</script>

<div class="space-y-4" data-testid="footage-overview">
  <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
    <p class="vf-label text-emerald-300/80">Footage Intelligence Edit</p>
    <h3 class="mt-1 text-[length:var(--vf-text-lg)] font-semibold text-neutral-100">Footage → anchors → delivery</h3>
    <div class="mt-4 grid gap-3 md:grid-cols-4">
      <div class="rounded-xl border border-white/10 bg-black/20 px-3 py-2"><p class="vf-label">OCR</p><p class="mt-1 text-[length:var(--vf-text-sm)] text-neutral-100">{frames.length} frames</p></div>
      <div class="rounded-xl border border-white/10 bg-black/20 px-3 py-2"><p class="vf-label">Tracks</p><p class="mt-1 text-[length:var(--vf-text-sm)] text-neutral-100">{tracked.length}</p></div>
      <div class="rounded-xl border border-white/10 bg-black/20 px-3 py-2"><p class="vf-label">Callouts</p><p class="mt-1 text-[length:var(--vf-text-sm)] text-neutral-100">{cards.length}</p></div>
      <div class="rounded-xl border border-white/10 bg-black/20 px-3 py-2"><p class="vf-label">QA</p><p class="mt-1 text-[length:var(--vf-text-sm)] text-neutral-100">{qa ? `${qa.critical_count ?? 0} critical` : "pending"}</p></div>
    </div>
  </section>

  <div class="grid gap-4 lg:grid-cols-2">
    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
      <p class="vf-label">Vision anchors</p>
      {#if frames.length}
        <ul class="mt-3 max-h-72 space-y-2 overflow-auto">
          {#each frames.slice(0, 10) as frame}
            <li class="rounded-lg border border-neutral-800 bg-neutral-950/40 px-3 py-2">
              <div class="flex items-center justify-between gap-2">
                <p class="text-[length:var(--vf-text-xs)] text-neutral-200">{frame.frame}</p>
                <span class="font-mono text-[length:var(--vf-text-2xs)] text-neutral-500">{frame.time_sec}s</span>
              </div>
              <p class="mt-1 line-clamp-2 text-[length:var(--vf-text-2xs)] text-neutral-500">
                {(frame.boxes ?? []).map((box: Record<string, any>) => box.text).filter(Boolean).join(" · ") || "No text detected"}
              </p>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="mt-3 text-[length:var(--vf-text-xs)] text-neutral-500">OCR frames appear after the vision pass.</p>
      {/if}
    </section>

    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
      <p class="vf-label">Tracked anchors</p>
      {#if tracked.length}
        <ul class="mt-3 max-h-72 space-y-2 overflow-auto">
          {#each tracked.slice(0, 12) as track}
            <li class="rounded-lg border border-neutral-800 bg-neutral-950/40 px-3 py-2">
              <p class="truncate text-[length:var(--vf-text-xs)] text-neutral-200">{track.text}</p>
              <p class="mt-1 font-mono text-[length:var(--vf-text-2xs)] text-neutral-500">{(track.points ?? []).length} keyframes · start {track.start_sec}s</p>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="mt-3 text-[length:var(--vf-text-xs)] text-neutral-500">Tracks appear after OCR anchors are approved.</p>
      {/if}
    </section>

    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
      <p class="vf-label">Callout cards</p>
      {#if cards.length}
        <ul class="mt-3 max-h-72 space-y-2 overflow-auto">
          {#each cards.slice(0, 12) as card}
            <li class="rounded-lg border border-neutral-800 bg-neutral-950/40 px-3 py-2">
              <p class="truncate text-[length:var(--vf-text-xs)] text-neutral-200">{card.text}</p>
              <p class="mt-1 text-[length:var(--vf-text-2xs)] text-neutral-500">{card.start_sec}s · {card.duration_sec}s · x {card.position_x} / y {card.position_y}</p>
            </li>
          {/each}
        </ul>
      {:else}
        <p class="mt-3 text-[length:var(--vf-text-xs)] text-neutral-500">Callouts appear after the anchor review.</p>
      {/if}
    </section>

    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
      <p class="vf-label">Licenses and QA</p>
      <div class="mt-3 space-y-2 text-[length:var(--vf-text-xs)]">
        <p class="flex items-center gap-2 text-neutral-300"><Icon name="check" size={13} class="text-emerald-300" />{licenses?.entries?.length ?? 0} license record(s)</p>
        <p class="flex items-center gap-2 text-neutral-300"><Icon name={issues.length ? "warning" : "check"} size={13} class={issues.length ? "text-amber-300" : "text-emerald-300"} />{issues.length} QA issue(s)</p>
      </div>
      {#if issues.length}
        <ul class="mt-3 space-y-1">
          {#each issues.slice(0, 6) as issue}
            <li class="rounded border border-amber-400/15 bg-amber-950/10 px-2 py-1 text-[length:var(--vf-text-2xs)] text-amber-100/80">{issue.message || issue.kind} · {issue.start_sec ?? 0}s</li>
          {/each}
        </ul>
      {/if}
    </section>
  </div>

  <CalloutEditor {jobId} />
</div>
