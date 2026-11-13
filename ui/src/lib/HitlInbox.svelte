<script lang="ts">
  import { focusTrap } from "$lib/a11y";
  import Icon from "$lib/ui/Icon.svelte";
  import { portal } from "$lib/portal";
  import { formatDateTime } from "$lib/format";
  import { i18n } from "$lib/i18n.svelte";
  import { bulkApproveInteractions, errorMessage, type HiltPending } from "$lib/api";

  let {
    open = false,
    items = [],
    onclose,
    onopen,
    onrefresh
  }: {
    open?: boolean;
    items?: HiltPending[];
    onclose: () => void;
    onopen: (jobId: string) => void;
    onrefresh?: () => void;
  } = $props();

  let selected = $state<string[]>([]);
  let bulkBusy = $state(false);
  let bulkStatus = $state("");
  let bulkError = $state("");

  function toggleSelected(interactionId: string, value: boolean) {
    selected = value
      ? [...new Set([...selected, interactionId])]
      : selected.filter((id) => id !== interactionId);
  }

  function toggleAll() {
    selected = allSelected
      ? []
      : approvalItems.map((item) => item.interaction.interaction_id);
  }

  async function approveSelected() {
    if (!selected.length) return;
    const chosen = new Set(selected);
    const payload = ordered
      .filter((item) => chosen.has(item.interaction.interaction_id))
      .map((item) => ({
        job_id: item.job_id,
        interaction_id: item.interaction.interaction_id
      }));
    bulkBusy = true;
    bulkError = "";
    bulkStatus = "";
    try {
      const result = await bulkApproveInteractions(payload);
      selected = [];
      bulkStatus =
        result.failed.length > 0
          ? `${result.approved.length} approved, ${result.failed.length} failed.`
          : `${result.approved.length} gate(s) approved.`;
      onrefresh?.();
    } catch (reason) {
      bulkError = errorMessage(reason);
    } finally {
      bulkBusy = false;
    }
  }

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
  const approvalItems = $derived(
    ordered.filter((item) => item.interaction.kind === "approval")
  );
  const allSelected = $derived(
    approvalItems.length > 0 &&
      approvalItems.every((item) =>
        selected.includes(item.interaction.interaction_id)
      )
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

      {#if approvalItems.length}
        <div class="space-y-2 border-b border-neutral-800 px-3 py-2">
          <div class="flex items-center justify-between gap-2">
            <label class="flex items-center gap-2 text-[length:var(--vf-text-2xs)] text-neutral-400">
              <input
                type="checkbox"
                checked={allSelected}
                onchange={toggleAll}
                class="h-3.5 w-3.5"
              />
              Select all approvals ({approvalItems.length})
            </label>
            <button
              type="button"
              onclick={() => void approveSelected()}
              disabled={!selected.length || bulkBusy}
              class="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-2.5 py-1 text-[length:var(--vf-text-2xs)] text-emerald-200 disabled:opacity-40"
            >{bulkBusy ? "Approving…" : `Approve selected (${selected.length})`}</button>
          </div>
          {#if bulkStatus}<p class="text-[length:var(--vf-text-2xs)] text-emerald-300">{bulkStatus}</p>{/if}
          {#if bulkError}<p class="text-[length:var(--vf-text-2xs)] text-rose-300">{bulkError}</p>{/if}
        </div>
      {/if}

      <div class="flex-1 space-y-2 overflow-auto p-3">
        {#if ordered.length}
          {#each ordered as item (item.interaction.interaction_id)}
            <div class="flex items-start gap-2 rounded-xl border border-neutral-800 bg-neutral-900/50 px-3 py-3 transition-colors hover:border-amber-400/40">
              {#if item.interaction.kind === "approval"}
                <input
                  type="checkbox"
                  checked={selected.includes(item.interaction.interaction_id)}
                  onchange={(event) => toggleSelected(item.interaction.interaction_id, event.currentTarget.checked)}
                  aria-label={`Select ${item.interaction.title}`}
                  class="mt-0.5 h-3.5 w-3.5 shrink-0"
                />
              {/if}
              <button
                type="button"
                onclick={() => onopen(item.job_id)}
                class="min-w-0 flex-1 text-left"
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
            </div>
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
