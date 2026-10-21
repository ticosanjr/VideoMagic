<script lang="ts">
  import { onMount } from "svelte";
  import { errorMessage, getImages, uploadImage, type ImageAsset } from "$lib/api";

  let {
    selected = "",
    onSelect
  }: { selected?: string; onSelect: (name: string) => void } = $props();
  let images = $state<ImageAsset[]>([]);
  let loading = $state(true);
  let busy = $state(false);
  let error = $state("");
  let input: HTMLInputElement | undefined = $state();

  async function refresh() {
    loading = true;
    try {
      images = await getImages();
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
      const asset = await uploadImage(file);
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
      <p class="text-[11px] uppercase tracking-wide text-neutral-500">Watermark / overlay</p>
      <p class="mt-1 text-[10px] text-neutral-500">PNG or JPEG, max 15 MB.</p>
    </div>
    <input bind:this={input} type="file" accept=".png,.jpg,.jpeg" onchange={upload} class="hidden" />
    <button
      type="button"
      onclick={() => input?.click()}
      disabled={busy}
      class="rounded-lg border border-neutral-700 px-2.5 py-1.5 text-[10px] text-neutral-300 hover:border-sky-500/60 hover:text-sky-200 disabled:opacity-40"
    >
      {busy ? "Uploading…" : "Upload image"}
    </button>
  </div>
  {#if error}<p class="mt-2 text-[10px] text-rose-300">{error}</p>{/if}
  {#if loading}
    <p class="mt-2 text-[10px] text-neutral-500">Reading images…</p>
  {:else if images.length === 0}
    <p class="mt-2 text-[10px] text-neutral-500">No uploaded images yet.</p>
  {:else}
    <div class="mt-2 flex flex-wrap gap-1.5">
      {#each images as image}
        <button
          type="button"
          onclick={() => onSelect(image.name)}
          class={`rounded-full border px-2 py-1 text-[10px] ${selected === image.name ? "border-sky-500/60 text-sky-200" : "border-neutral-700 text-neutral-300 hover:border-sky-500/60 hover:text-sky-200"}`}
        >
          {image.name}
        </button>
      {/each}
    </div>
  {/if}
</div>
