<script lang="ts">
  import type { AssetRecord } from "$lib/api";

  let { assets }: { assets: AssetRecord[] } = $props();
</script>

<div class="flex flex-wrap items-center gap-1.5 rounded-xl border border-neutral-800 bg-neutral-900/40 px-2 py-1.5" data-testid="asset-rail">
  <span class="text-[10px] uppercase tracking-wide text-neutral-500">Assets</span>
  {#each assets.slice(0, 12) as asset (asset.id)}
    <span
      draggable="true"
      role="button"
      tabindex="0"
      title={`Drag ${asset.name} onto the timeline`}
      class="cursor-grab rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-0.5 text-[10px] text-neutral-300"
      ondragstart={(event) => {
        event.dataTransfer?.setData(
          "application/x-videoflow-asset",
          JSON.stringify({ id: asset.id, name: asset.name, path: asset.path, kind: asset.kind })
        );
        if (event.dataTransfer) event.dataTransfer.effectAllowed = "copy";
      }}
    >{asset.name}</span>
  {/each}
  {#if !assets.length}<span class="text-[10px] text-neutral-600">Scan assets in the Assets tab to drag them here.</span>{/if}
</div>
