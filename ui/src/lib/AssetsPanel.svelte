<script lang="ts">
  import HelpTip from "$lib/HelpTip.svelte";
  import Icon from "$lib/ui/Icon.svelte";
  import EmptyState from "$lib/EmptyState.svelte";
  import ErrorBanner from "$lib/ErrorBanner.svelte";
  import { onMount } from "svelte";
  import PathPicker from "$lib/PathPicker.svelte";
  import {
    assetFileUrl,
    errorMessage,
    listAssets,
    removeAsset,
    scanAssets,
    updateAssetTags,
    type AssetRecord
  } from "$lib/api";

  let assets = $state<AssetRecord[]>([]);
  let query = $state("");
  let kind = $state("");
  let scanDir = $state("");
  let tags = $state("");
  let picker = $state(false);
  let busy = $state(false);
  let error = $state("");
  let status = $state("");

  const filtered = $derived(
    assets.filter((asset) => {
      const needle = query.trim().toLocaleLowerCase();
      if (kind && asset.kind !== kind) return false;
      if (!needle) return true;
      return (
        asset.name.toLocaleLowerCase().includes(needle) ||
        asset.path.toLocaleLowerCase().includes(needle) ||
        asset.tags.some((tag) => tag.toLocaleLowerCase().includes(needle))
      );
    })
  );

  onMount(() => void refresh());

  async function refresh() {
    error = "";
    try {
      assets = await listAssets();
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function scan() {
    if (!scanDir.trim()) {
      error = "Choose a folder to scan.";
      return;
    }
    busy = true;
    error = "";
    try {
      await scanAssets(
        scanDir.trim(),
        tags.split(",").map((item) => item.trim()).filter(Boolean)
      );
      await refresh();
      status = `Indexed ${scanDir}`;
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  async function remove(id: string) {
    try {
      await removeAsset(id);
      await refresh();
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function saveTags(asset: AssetRecord, value: string) {
    try {
      const updated = await updateAssetTags(
        asset.id,
        value.split(",").map((item) => item.trim()).filter(Boolean)
      );
      assets = assets.map((item) => (item.id === updated.id ? updated : item));
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  function size(value: number): string {
    if (value > 1_000_000) return `${(value / 1_000_000).toFixed(1)} MB`;
    if (value > 1_000) return `${(value / 1_000).toFixed(1)} KB`;
    return `${value} B`;
  }
</script>

<div class="space-y-4">
  <ErrorBanner message={error} onDismiss={() => (error = "")} />
  <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <div class="flex items-center gap-1.5"><h2 class="text-sm font-semibold text-white">Media</h2> <HelpTip label="Media" body="Source media, audio, images, and fonts. Allowed roots gate every path." doc="docs/api.md" /></div>
        <p class="mt-1 text-xs text-neutral-500">Local media, audio, images, and fonts with tags and license metadata.</p>
      </div>
      <div class="flex flex-wrap gap-2">
        <input bind:value={query} placeholder="Search assets…" class="rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-1.5 text-xs text-neutral-200" />
        <select bind:value={kind} class="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-200">
          <option value="">All kinds</option>
          <option value="video">Video</option>
          <option value="audio">Audio</option>
          <option value="image">Image</option>
          <option value="font">Font</option>
        </select>
      </div>
    </div>
    <div class="mt-4 grid gap-2 sm:grid-cols-4" data-testid="media-summary">
      <div class="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2"><p class="vf-label">Assets</p><p class="mt-1 text-[length:var(--vf-text-lg)] font-semibold text-neutral-100">{assets.length}</p></div>
      <div class="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2"><p class="vf-label">Video</p><p class="mt-1 text-[length:var(--vf-text-lg)] font-semibold text-neutral-100">{assets.filter((item) => item.kind === "video").length}</p></div>
      <div class="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2"><p class="vf-label">Audio</p><p class="mt-1 text-[length:var(--vf-text-lg)] font-semibold text-neutral-100">{assets.filter((item) => item.kind === "audio").length}</p></div>
      <div class="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2"><p class="vf-label">Images</p><p class="mt-1 text-[length:var(--vf-text-lg)] font-semibold text-neutral-100">{assets.filter((item) => item.kind === "image").length}</p></div>
    </div>
    <div class="mt-3 grid gap-2 md:grid-cols-[1fr_auto_auto]">
      <input bind:value={scanDir} placeholder="/path/to/assets" class="rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 font-mono text-xs text-neutral-200" />
      <button type="button" onclick={() => (picker = true)} class="rounded-lg border border-neutral-700 px-3 py-2 text-xs text-neutral-300 hover:border-sky-500">Choose folder</button>
      <button type="button" onclick={() => void scan()} disabled={busy} class="rounded-lg bg-sky-500 px-3 py-2 text-xs font-medium text-neutral-950 disabled:opacity-40">{busy ? "Scanning…" : "Scan into library"}</button>
    </div>
    <input bind:value={tags} placeholder="tags: interview, b-roll, music" class="mt-2 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-1.5 text-xs text-neutral-200" />
    {#if status}<p class="mt-2 text-[11px] text-emerald-300">{status}</p>{/if}
  </section>

  <section class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
    {#each filtered as asset}
      <article class="overflow-hidden rounded-2xl border border-neutral-800 bg-neutral-900/50">
        <div class="flex h-32 items-center justify-center bg-neutral-950">
          {#if asset.kind === "image"}
            <img src={assetFileUrl(asset.id)} alt={asset.name} class="h-full w-full object-cover" />
          {:else}
            <span class="text-neutral-600"><Icon name={asset.kind === "video" ? "film" : asset.kind === "audio" ? "music" : asset.kind === "font" ? "type" : "image"} size={34} /></span>
          {/if}
        </div>
        <div class="p-3">
          <p class="truncate text-xs font-medium text-neutral-200" title={asset.name}>{asset.name}</p>
          <p class="mt-1 truncate font-mono text-[9px] text-neutral-600" title={asset.path}>{asset.path}</p>
          <div class="mt-2 flex items-center justify-between gap-2 text-[10px] text-neutral-500">
            <span>{asset.kind} · {size(asset.size_bytes)}</span>
            <span class="rounded bg-white/5 px-1.5 py-0.5">{asset.license}</span>
          </div>
          <input
            value={asset.tags.join(", ")}
            placeholder="tags"
            onchange={(event) => void saveTags(asset, event.currentTarget.value)}
            class="mt-2 w-full rounded border border-neutral-800 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-300"
          />
          <div class="mt-2 flex gap-2">
            <a href={assetFileUrl(asset.id)} download class="rounded border border-neutral-700 px-2 py-1 text-[10px] text-neutral-300 hover:border-sky-500">Download</a>
            <button type="button" onclick={() => void remove(asset.id)} class="rounded border border-rose-500/30 px-2 py-1 text-[10px] text-rose-300">Remove</button>
          </div>
        </div>
      </article>
    {/each}
    {#if filtered.length === 0}
      <div class="col-span-full">
        <EmptyState
          title="No assets yet"
          description="Scan a folder to build the library, then tag and license each asset."
          action="Scan a folder"
          icon="image"
          onaction={() => (picker = true)}
        />
      </div>
    {/if}
  </section>
</div>

{#if picker}
  <PathPicker open={true} mode="directory" title="Choose asset folder" initialPath={scanDir} onclose={() => (picker = false)} onselect={(path) => { scanDir = path; picker = false; }} />
{/if}
