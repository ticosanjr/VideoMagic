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
  const callouts = $derived((payload?.callouts ?? []) as Array<Record<string, any>>);

  onMount(async () => {
    const loaded = await loadArtifactJson<Record<string, any>>(jobId, "motion_callouts");
    if (loaded && Array.isArray(loaded.callouts)) payload = loaded;
  });

  async function save() {
    if (!payload) return;
    busy = true;
    status = "";
    error = "";
    try {
      const result = await updateJobArtifact(jobId, "motion_callouts", payload);
      status = result.note;
      onSaved?.(payload);
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }
</script>

{#if payload && callouts.length}
  <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4" data-testid="callout-editor">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div>
        <p class="vf-label">Callout editor</p>
        <p class="mt-1 text-[length:var(--vf-text-2xs)] text-neutral-500">Edit the anchored cards, then re-run motion.callout to apply them.</p>
      </div>
      <button
        type="button"
        onclick={() => void save()}
        disabled={busy}
        class="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-1 text-[length:var(--vf-text-xs)] text-emerald-200 disabled:opacity-40"
      >{busy ? "Saving…" : "Save callout plan"}</button>
    </div>
    <ol class="mt-3 max-h-96 space-y-2 overflow-auto">
      {#each callouts.slice(0, 12) as callout, index (callout.callout_id ?? index)}
        <li class="rounded-lg border border-neutral-800 bg-neutral-950/40 p-3">
          <div class="flex items-center justify-between gap-2">
            <span class="font-mono text-[length:var(--vf-text-2xs)] text-emerald-200">{callout.callout_id ?? `CALLOUT-${index + 1}`}</span>
            <span class="text-[length:var(--vf-text-2xs)] text-neutral-500">{callout.unit_id ?? ""}</span>
          </div>
          <label class="mt-2 block text-[length:var(--vf-text-2xs)] text-neutral-400">Text
            <input bind:value={callout.text} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[length:var(--vf-text-xs)] text-neutral-100" />
          </label>
          <div class="mt-1.5 grid grid-cols-2 gap-2">
            <label class="block text-[length:var(--vf-text-2xs)] text-neutral-400">Start (s)
              <input type="number" min="0" step="0.1" bind:value={callout.start_sec} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[length:var(--vf-text-xs)] text-neutral-100" />
            </label>
            <label class="block text-[length:var(--vf-text-2xs)] text-neutral-400">Duration (s)
              <input type="number" min="0.5" step="0.1" bind:value={callout.duration_sec} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[length:var(--vf-text-xs)] text-neutral-100" />
            </label>
            <label class="block text-[length:var(--vf-text-2xs)] text-neutral-400">X
              <input type="number" min="0" max="1" step="0.01" bind:value={callout.position_x} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[length:var(--vf-text-xs)] text-neutral-100" />
            </label>
            <label class="block text-[length:var(--vf-text-2xs)] text-neutral-400">Y
              <input type="number" min="0" max="1" step="0.01" bind:value={callout.position_y} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[length:var(--vf-text-xs)] text-neutral-100" />
            </label>
          </div>
        </li>
      {/each}
    </ol>
    {#if status}<p class="mt-2 flex items-center gap-1.5 text-[length:var(--vf-text-2xs)] text-emerald-300"><Icon name="check" size={11} />{status}</p>{/if}
    {#if error}<p class="mt-2 text-[length:var(--vf-text-2xs)] text-rose-300">{error}</p>{/if}
  </section>
{/if}
