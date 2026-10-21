<script lang="ts">
  import { onMount } from "svelte";
  import { errorMessage, getFonts, uploadFont, type FontAsset } from "$lib/api";

  let { onSelect }: { onSelect: (family: string) => void } = $props();
  let fonts = $state<FontAsset[]>([]);
  let loading = $state(true);
  let busy = $state(false);
  let error = $state("");
  let input: HTMLInputElement | undefined = $state();

  async function refresh() {
    loading = true;
    try {
      fonts = await getFonts();
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
      const asset = await uploadFont(file);
      await refresh();
      onSelect(asset.family);
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
      <p class="text-[11px] uppercase tracking-wide text-neutral-500">Custom fonts</p>
      <p class="mt-1 text-[10px] text-neutral-500">
        Upload a TTF/OTF. The internal family name is used by libass.
      </p>
    </div>
    <input
      bind:this={input}
      type="file"
      accept=".ttf,.otf"
      onchange={upload}
      class="hidden"
    />
    <button
      type="button"
      onclick={() => input?.click()}
      disabled={busy}
      class="rounded-lg border border-neutral-700 px-2.5 py-1.5 text-[10px] text-neutral-300 hover:border-sky-500/60 hover:text-sky-200 disabled:opacity-40"
    >
      {busy ? "Uploading…" : "Upload font"}
    </button>
  </div>

  {#if error}
    <p class="mt-2 text-[10px] text-rose-300">{error}</p>
  {/if}

  {#if loading}
    <p class="mt-2 text-[10px] text-neutral-500">Reading fonts…</p>
  {:else if fonts.length === 0}
    <p class="mt-2 text-[10px] text-neutral-500">No uploaded fonts yet.</p>
  {:else}
    <div class="mt-2 flex flex-wrap gap-1.5">
      {#each fonts as font}
        <button
          type="button"
          onclick={() => onSelect(font.family)}
          title={`Use ${font.family}`}
          class="rounded-full border border-neutral-700 px-2 py-1 text-[10px] text-neutral-300 hover:border-sky-500/60 hover:text-sky-200"
        >
          {font.family}
        </button>
      {/each}
    </div>
  {/if}
</div>
