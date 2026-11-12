<script lang="ts">
  import { focusTrap } from "$lib/a11y";
  import Icon from "$lib/ui/Icon.svelte";
  import { portal } from "$lib/portal";
  import { formatDateTime } from "$lib/format";
  import { i18n } from "$lib/i18n.svelte";
  import type { HiltPending } from "$lib/api";

  let {
    open = false,
    items = [],
    onclose,
    onopen
  }: {
    open?: boolean;
    items?: HiltPending[];
    onclose: () => void;
    onopen: (jobId: string) => void;
  } = $props();

  const ordered = $derived(
    [...items].sort((left, right) => {
      const rank = { critical: 0, warning: 1, info: 2 } as Record<string, number>;
      const leftRank = rank[left.interaction.severity ?? "info"] ?? 2;
      const rightRank = rank[right.interaction.severity ?? "info"] ?? 2;
      if (leftRank !== rightRank) return leftRank - rightRank;
      return String(left.interaction.created_at).localeCompare(
        String(right.interaction.created_at)
      );
    })
  );
</script>

{#if open}
  <div use:portal class="fixed inset-0 z-[95]">
    <button
      type="button"
      class="absolute inset-0 bg-black/70 backdrop-blur-sm"
      aria-label={i18n.t("close")}
      onclick={onclose}
    ></button>
    <div
      class="absolute inset-y-0 right-0 flex w-full max-w-md flex-col border-l border-neutral-800 bg-neutral-950 shadow-2xl"
      role="dialog"
      aria-modal="true"
      aria-label="Needs you"
      data-testid="hitl-inbox"
      use:focusTrap
    >
      <header class="flex items-start justify-between gap-3 border-b border-neutral-800 px-4 py-3">
        <div>
          <p class="vf-label text-amber-300/80">Needs you</p>
          <h2 class="mt-1 text-[length:var(--vf-text-lg)] font-semibold text-white">Pending gates</h2>
          <p class="mt-1 text-[length:var(--vf-text-xs)] text-neutral-500">{items.length} waiting for a human decision.</p>
        </div>
        <button type="button" class="rounded-lg border border-white/10 px-2.5 py-1 text-[length:var(--vf-text-2xs)] text-neutral-400 hover:text-neutral-100" onclick={onclose}>{i18n.t("close")}</button>
      </header>

      <div class="flex-1 space-y-2 overflow-auto p-3">
        {#if ordered.length}
          {#each ordered as item (item.interaction.interaction_id)}
            <button
              type="button"
              onclick={() => onopen(item.job_id)}
              class="w-full rounded-xl border border-neutral-800 bg-neutral-900/50 px-3 py-3 text-left transition-colors hover:border-amber-400/40"
            >
              <div class="flex items-start justify-between gap-2">
                <span class="text-[length:var(--vf-text-xs)] font-semibold text-neutral-100">{item.interaction.title}</span>
                <span class={`rounded-full border px-2 py-0.5 text-[length:var(--vf-text-2xs)] uppercase ${item.interaction.severity === "critical" ? "border-rose-400/30 bg-rose-400/10 text-rose-200" : item.interaction.severity === "warning" ? "border-amber-400/30 bg-amber-400/10 text-amber-200" : "border-sky-400/30 bg-sky-400/10 text-sky-200"}`}>
                  {item.interaction.severity ?? "info"}
                </span>
              </div>
              <p class="mt-1 truncate text-[length:var(--vf-text-2xs)] text-neutral-500">{item.interaction.recipe_id || item.interaction.gate_id}</p>
              <p class="mt-1 line-clamp-2 text-[length:var(--vf-text-xs)] leading-5 text-neutral-400">{item.interaction.summary || item.interaction.description || item.job_message}</p>
              <div class="mt-2 flex items-center justify-between gap-2 text-[length:var(--vf-text-2xs)] text-neutral-600">
                <span>{item.interaction.kind}</span>
                <span>{formatDateTime(item.interaction.created_at)}</span>
              </div>
            </button>
          {/each}
        {:else}
          <div class="rounded-xl border border-dashed border-neutral-800 px-4 py-10 text-center">
            <Icon name="check" size={20} class="mx-auto text-emerald-300" />
            <p class="mt-2 text-[length:var(--vf-text-sm)] text-neutral-200">Nothing is waiting.</p>
            <p class="mt-1 text-[length:var(--vf-text-xs)] text-neutral-500">Start a run or continue editing.</p>
          </div>
        {/if}
      </div>
    </div>
  </div>
{/if}
