<script lang="ts">
  import { onMount } from "svelte";
  import { errorMessage, getMusic, uploadMusic, type MusicAsset } from "$lib/api";

  let {
    selected = "",
    onSelect
  }: { selected?: string; onSelect: (name: string) => void } = $props();
  let tracks = $state<MusicAsset[]>([]);
  let loading = $state(true);
  let busy = $state(false);
  let error = $state("");
  let input: HTMLInputElement | undefined = $state();

  async function refresh() {
    loading = true;
    try {
      tracks = await getMusic();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      loading = false;
    }
  }

  async function upload(event: Event) {
    const target = event.currentTarget as HTMLInputElement;
    const file = target.files?.[0];
    if (!file) return;
    busy = true;
    error = "";
    try {
      const asset = await uploadMusic(file);
      await refresh();
      onSelect(asset.name);
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
      target.value = "";
    }
  }

  onMount(() => {
    void refresh();
  });
</script>

<div class="rounded-xl border border-neutral-800 bg-neutral-950/60 p-3">
  <div class="flex flex-wrap items-center justify-between gap-2">
    <div>
      <p class="text-[11px] uppercase tracking-wide text-neutral-500">Background music</p>
      <p class="mt-1 text-[10px] text-neutral-500">MP3, WAV, M4A, AAC, or OGG; max 100 MB.</p>
    </div>
    <input bind:this={input} type="file" accept=".mp3,.wav,.m4a,.aac,.ogg" onchange={upload} class="hidden" />
    <button
      type="button"
      onclick={() => input?.click()}
      disabled={busy}
      class="rounded-lg border border-neutral-700 px-2.5 py-1.5 text-[10px] text-neutral-300 hover:border-sky-500/60 hover:text-sky-200 disabled:opacity-40"
    >
      {busy ? "Uploading…" : "Upload music"}
    </button>
  </div>
  {#if error}<p class="mt-2 text-[10px] text-rose-300">{error}</p>{/if}
  {#if loading}
    <p class="mt-2 text-[10px] text-neutral-500">Reading music…</p>
  {:else if tracks.length === 0}
    <p class="mt-2 text-[10px] text-neutral-500">No uploaded tracks yet.</p>
  {:else}
    <div class="mt-2 flex flex-wrap gap-1.5">
      {#each tracks as track}
        <button
          type="button"
          onclick={() => onSelect(track.name)}
          class={`rounded-full border px-2 py-1 text-[10px] ${selected === track.name ? "border-sky-500/60 text-sky-200" : "border-neutral-700 text-neutral-300 hover:border-sky-500/60 hover:text-sky-200"}`}
        >
          {track.name}
        </button>
      {/each}
    </div>
  {/if}
</div>
