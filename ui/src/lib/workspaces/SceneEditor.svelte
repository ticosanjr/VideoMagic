<script lang="ts">
  import { onMount } from "svelte";
  import { loadArtifactJson } from "$lib/artifactData";
  import { errorMessage, updateJobArtifact } from "$lib/api";
  import Icon from "$lib/ui/Icon.svelte";

  let {
    jobId,
    onSaved
  }: {
    jobId: string;
    onSaved?: (payload: Record<string, any>) => void;
  } = $props();

  let payload = $state<Record<string, any> | null>(null);
  let busy = $state(false);
  let status = $state("");
  let error = $state("");
  const scenes = $derived((payload?.scenes ?? []) as Array<Record<string, any>>);

  onMount(async () => {
    const loaded = await loadArtifactJson<Record<string, any>>(jobId, "motion_scenes");
    if (loaded && Array.isArray(loaded.scenes)) payload = loaded;
  });

  async function save() {
    if (!payload) return;
    busy = true;
    status = "";
    error = "";
    try {
      const result = await updateJobArtifact(jobId, "motion_scenes", payload);
      status = result.note;
      onSaved?.(payload);
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }
</script>

{#if payload && scenes.length}
  <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4" data-testid="scene-editor">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div>
        <p class="vf-label">Scene editor</p>
        <p class="mt-1 text-[length:var(--vf-text-2xs)] text-neutral-500">Edit the scene plan, then re-run scene codegen/render to apply it.</p>
      </div>
      <button
        type="button"
        onclick={() => void save()}
        disabled={busy}
        class="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-1 text-[length:var(--vf-text-xs)] text-emerald-200 disabled:opacity-40"
      >{busy ? "Saving…" : "Save scene plan"}</button>
    </div>
    <ol class="mt-3 max-h-96 space-y-2 overflow-auto">
      {#each scenes.slice(0, 12) as scene, index (scene.scene_id ?? index)}
        <li class="rounded-lg border border-neutral-800 bg-neutral-950/40 p-3">
          <div class="flex items-center justify-between gap-2">
            <span class="font-mono text-[length:var(--vf-text-2xs)] text-sky-200">{scene.scene_id ?? `SCENE-${index + 1}`}</span>
            <span class="text-[length:var(--vf-text-2xs)] text-neutral-500">{scene.unit_id ?? ""}</span>
          </div>
          <label class="mt-2 block text-[length:var(--vf-text-2xs)] text-neutral-400">Title
            <input bind:value={scene.title} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[length:var(--vf-text-xs)] text-neutral-100" />
          </label>
          <label class="mt-1.5 block text-[length:var(--vf-text-2xs)] text-neutral-400">Narration
            <textarea bind:value={scene.narration} rows="2" class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[length:var(--vf-text-xs)] text-neutral-100"></textarea>
          </label>
          <label class="mt-1.5 block text-[length:var(--vf-text-2xs)] text-neutral-400">Duration (s)
            <input type="number" min="1" step="0.5" bind:value={scene.duration_sec} class="mt-1 w-28 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[length:var(--vf-text-xs)] text-neutral-100" />
          </label>
        </li>
      {/each}
    </ol>
    {#if status}<p class="mt-2 flex items-center gap-1.5 text-[length:var(--vf-text-2xs)] text-emerald-300"><Icon name="check" size={11} />{status}</p>{/if}
    {#if error}<p class="mt-2 text-[length:var(--vf-text-2xs)] text-rose-300">{error}</p>{/if}
  </section>
{/if}
