<script lang="ts">
  import type { VariantComparison } from "$lib/api";
  type MaybeAsync = void | Promise<void>;

  let {
    variants,
    busy = false,
    onLoad,
    onPick
  }: {
    variants: VariantComparison | null;
    busy?: boolean;
    onLoad: () => MaybeAsync;
    onPick: (name: string) => MaybeAsync;
  } = $props();
</script>

<div class="mt-3 rounded-xl border border-neutral-800 bg-neutral-950/50 p-3" data-testid="variant-compare">
  <div class="flex items-center justify-between gap-2">
    <p class="text-[10px] uppercase tracking-wide text-neutral-500">Variant comparison</p>
    <button type="button" onclick={() => void onLoad()} disabled={busy} class="rounded border border-neutral-700 px-2 py-1 text-[10px] text-neutral-300 disabled:opacity-40">{busy ? "Loading…" : "Compare variants"}</button>
  </div>
  {#if variants}
    {#if variants.items.length}
      <div class="mt-2 grid gap-2 md:grid-cols-2">
        {#each variants.items as item (item.id)}
          <div class={`rounded-lg border p-2 ${variants.winner === item.id || variants.winner === item.name ? "border-emerald-400/40" : "border-neutral-800"}`}>
            <div class="flex items-center justify-between gap-2">
              <p class="truncate text-[11px] text-neutral-200">{item.name}</p>
              <button type="button" onclick={() => void onPick(item.name)} class="rounded border border-emerald-500/30 px-1.5 py-0.5 text-[9px] text-emerald-200">Winner</button>
            </div>
            <p class="mt-1 font-mono text-[9px] text-neutral-500">{item.kind} · {JSON.stringify(item.metrics)}</p>
          </div>
        {/each}
      </div>
    {:else}
      <p class="mt-2 text-[10px] text-neutral-600">No variants or Shorts in this run.</p>
    {/if}
    {#if variants.winner}<p class="mt-2 text-[10px] text-emerald-300">Selected winner: {variants.winner}</p>{/if}
  {/if}
</div>
