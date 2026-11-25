<script lang="ts">
  import { onMount } from "svelte";
  import {
    curationMediaUrl,
    errorMessage,
    getCurationBoard,
    listCurationBoards,
    submitCurationDecision,
    type CurationBoard,
    type CurationBoardSummary,
    type CurationDecision,
    type CurationItem
  } from "$lib/api";
  import EmptyState from "$lib/EmptyState.svelte";
  import ErrorBanner from "$lib/ErrorBanner.svelte";

  let { projectId = "" }: { projectId?: string } = $props();

  type CategoryTab = {
    id: string;
    label: string;
    categories: CurationItem["category"][];
  };

  const CATEGORY_TABS: CategoryTab[] = [
    { id: "style", label: "Styles", categories: ["style"] },
    { id: "music", label: "Music", categories: ["music"] },
    { id: "sfx", label: "SFX", categories: ["sfx"] },
    { id: "visual", label: "B-roll & Images", categories: ["broll", "image"] },
    { id: "short", label: "Shorts", categories: ["short"] },
    { id: "cut_review", label: "Cut review", categories: ["cut_review"] }
  ];

  let boards = $state<CurationBoardSummary[]>([]);
  let board = $state<CurationBoard | null>(null);
  let decisions = $state<CurationDecision | null>(null);
  let currentProject = $state("");
  let activeCategory = $state<string>("style");
  let selectedIds = $state<string[]>([]);
  let rejectedIds = $state<string[]>([]);
  let loading = $state(true);
  let busy = $state(false);
  let error = $state("");
  let notice = $state("");
  let previewErrors = $state<Record<string, string>>({});
  let previewRetries = $state<Record<string, number>>({});

  const statusLabel: Record<string, string> = {
    waiting_human: "Waiting for human",
    decided: "Decided",
    delegated_to_ai: "Delegated to AI"
  };

  const visibleCategories = $derived(
    CATEGORY_TABS.filter((tab) =>
      board?.items.some((item) => tab.categories.includes(item.category))
    )
  );
  const currentCategory = $derived(
    CATEGORY_TABS.find((tab) => tab.id === activeCategory) ?? CATEGORY_TABS[0]
  );
  const visibleItems = $derived(
    board?.items.filter((item) =>
      currentCategory.categories.includes(item.category)
    ) ?? []
  );
  const selectedCount = $derived(
    board?.items.filter((item) => selectedIds.includes(item.item_id)).length ?? 0
  );
  const rejectedCount = $derived(
    board?.items.filter((item) => rejectedIds.includes(item.item_id)).length ?? 0
  );

  function projectFromHash(): string {
    if (typeof window === "undefined") return "";
    const match = window.location.hash.match(/^#curation\/(.+)$/);
    return match ? decodeURIComponent(match[1]) : "";
  }

  function applySelection(next: CurationBoard, decision: CurationDecision | null) {
    board = next;
    decisions = decision;
    selectedIds = decision?.selected_ids ?? next.items.filter((item) => item.status === "selected").map((item) => item.item_id);
    rejectedIds = decision?.rejected_ids ?? next.items.filter((item) => item.status === "rejected").map((item) => item.item_id);
    const categories = CATEGORY_TABS.filter((tab) =>
      next.items.some((item) => tab.categories.includes(item.category))
    );
    if (!categories.some((tab) => tab.id === activeCategory)) {
      activeCategory = categories[0]?.id ?? "style";
    }
  }

  async function selectBoard(
    id: string,
    options: { updateHash?: boolean } = {}
  ) {
    if (!id) return;
    const updateHash = options.updateHash !== false;
    currentProject = id;
    loading = true;
    error = "";
    notice = "";
    try {
      const payload = await getCurationBoard(id);
      applySelection(payload.board, payload.decisions);
      if (updateHash && typeof window !== "undefined") {
        history.replaceState(null, "", `#curation/${encodeURIComponent(id)}`);
      }
    } catch (reason) {
      board = null;
      decisions = null;
      error = errorMessage(reason);
    } finally {
      loading = false;
    }
  }

  async function refreshBoards() {
    error = "";
    try {
      boards = await listCurationBoards(true);
      const target =
        projectFromHash() ||
        projectId ||
        currentProject ||
        boards.find((item) => item.status === "waiting_human")?.project_id ||
        boards[0]?.project_id ||
        "";
      if (target) await selectBoard(target);
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      loading = false;
    }
  }

  function mediaUrl(item: CurationItem): string {
    return item.media_url || curationMediaUrl(currentProject, item.item_id);
  }

  function posterUrl(item: CurationItem): string {
    return item.poster_url || "";
  }

  function clockLabel(seconds: number): string {
    const value = Math.max(0, Math.round(seconds));
    const minutes = Math.floor(value / 60);
    const rest = value % 60;
    return `${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
  }

  function rangeLabel(item: CurationItem): string {
    if (item.start_sec == null || item.end_sec == null) return "";
    return `${clockLabel(item.start_sec)}–${clockLabel(item.end_sec)}`;
  }

  function previewSrc(item: CurationItem): string {
    const retry = previewRetries[item.item_id] ?? 0;
    return retry ? `${mediaUrl(item)}?retry=${retry}` : mediaUrl(item);
  }

  function markPreviewError(item: CurationItem) {
    previewErrors = {
      ...previewErrors,
      [item.item_id]: "Preview indisponível (HTTP/arquivo)"
    };
  }

  function retryPreview(item: CurationItem) {
    previewRetries = {
      ...previewRetries,
      [item.item_id]: (previewRetries[item.item_id] ?? 0) + 1
    };
    const next = { ...previewErrors };
    delete next[item.item_id];
    previewErrors = next;
  }

  function toggle(item: CurationItem, status: "selected" | "rejected") {
    const source = status === "selected" ? selectedIds : rejectedIds;
    const other = status === "selected" ? rejectedIds : selectedIds;
    if (source.includes(item.item_id)) {
      if (status === "selected") selectedIds = selectedIds.filter((id) => id !== item.item_id);
      else rejectedIds = rejectedIds.filter((id) => id !== item.item_id);
      return;
    }
    if (status === "selected") {
      selectedIds = [...selectedIds, item.item_id];
      rejectedIds = other.filter((id) => id !== item.item_id);
    } else {
      rejectedIds = [...rejectedIds, item.item_id];
      selectedIds = other.filter((id) => id !== item.item_id);
    }
  }

  async function decide(delegate: boolean) {
    if (!board || busy) return;
    busy = true;
    error = "";
    notice = "";
    try {
      const payload = await submitCurationDecision(board.project_id, {
        selected_ids: delegate ? [] : selectedIds,
        rejected_ids: delegate ? [] : rejectedIds,
        delegate_to_ai: delegate
      });
      if (payload.board) applySelection(payload.board, payload.decisions);
      await refreshBoards();
      notice = "Saved! Return to OpenCode and type 'pronto'.";
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  onMount(() => {
    void refreshBoards();
    const onHash = () => {
      const target = projectFromHash();
      if (target && target !== currentProject) void selectBoard(target, { updateHash: false });
    };
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  });
</script>

<section class="grid gap-4 lg:grid-cols-[18rem_minmax(0,1fr)]" data-testid="curation-board">
  <aside class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-3">
    <div class="flex items-center justify-between gap-2">
      <div>
        <p class="vf-label text-sky-300/80">Curation</p>
        <h2 class="mt-1 text-[length:var(--vf-text-lg)] font-semibold text-white">Pending boards</h2>
      </div>
      <button
        type="button"
        onclick={() => void refreshBoards()}
        class="rounded-lg border border-white/10 px-2 py-1 text-[length:var(--vf-text-2xs)] text-neutral-300 hover:border-sky-500/40"
        title="Refresh boards"
      >Refresh</button>
    </div>
    {#if boards.length === 0}
      <p class="mt-4 text-[length:var(--vf-text-xs)] text-neutral-500">No pending boards.</p>
    {:else}
      <div class="mt-3 space-y-1.5">
        {#each boards as item (item.project_id)}
          <button
            type="button"
            onclick={() => void selectBoard(item.project_id)}
            class={`w-full rounded-xl border px-3 py-2 text-left transition-colors ${
              item.project_id === board?.project_id
                ? "border-sky-400/30 bg-sky-500/10"
                : "border-white/5 bg-white/[0.02] hover:border-white/15"
            }`}
          >
            <span class="flex items-center justify-between gap-2">
              <span class="truncate font-mono text-[length:var(--vf-text-2xs)] text-neutral-200">{item.project_id.slice(0, 12)}</span>
              <span class="rounded-full border border-white/10 px-1.5 py-0.5 text-[length:var(--vf-text-2xs)] text-neutral-400">{item.item_count}</span>
            </span>
            <span class="mt-1 block text-[length:var(--vf-text-2xs)] text-neutral-500">{statusLabel[item.status] ?? item.status}</span>
          </button>
        {/each}
      </div>
    {/if}
  </aside>

  <div class="min-w-0 space-y-3">
    <ErrorBanner message={error} title="Curation failed" onDismiss={() => (error = "")} />
    {#if notice}
      <div class="rounded-xl border border-emerald-400/20 bg-emerald-500/10 px-3 py-2 text-[length:var(--vf-text-xs)] text-emerald-100" role="status">{notice}</div>
    {/if}

    {#if loading}
      <div class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-6 text-sm text-neutral-400">Loading curation board…</div>
    {:else if !board}
      <EmptyState
        title="No board selected."
        description="Ask for an edit in curation mode to create one. The agent publishes the board and returns a deep link."
      />
    {:else}
      <div class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
        <div class="flex flex-wrap items-start justify-between gap-3">
          <div>
            <p class="vf-label text-sky-300/80">Board</p>
            <h2 class="mt-1 text-[length:var(--vf-text-xl)] font-semibold text-white">{board.project_id.slice(0, 12)}</h2>
            <p class="mt-1 text-[length:var(--vf-text-xs)] text-neutral-500">{statusLabel[board.status] ?? board.status} · {selectedCount} selected · {rejectedCount} excluded</p>
          </div>
          <div class="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy}
              onclick={() => void decide(true)}
              class="rounded-lg border border-sky-400/25 bg-sky-500/10 px-3 py-2 text-[length:var(--vf-text-xs)] font-medium text-sky-100 disabled:opacity-40"
            >Let AI choose the best</button>
            <button
              type="button"
              disabled={busy}
              onclick={() => void decide(false)}
              class="rounded-lg border border-emerald-400/25 bg-emerald-500/15 px-3 py-2 text-[length:var(--vf-text-xs)] font-medium text-emerald-100 disabled:opacity-40"
            >Confirm selections</button>
          </div>
        </div>

        <div class="mt-3 flex gap-1 overflow-x-auto border-t border-white/5 pt-3" role="tablist" aria-label="Curation categories">
          {#each visibleCategories as tab (tab.id)}
            <button
              type="button"
              role="tab"
              aria-selected={activeCategory === tab.id}
              onclick={() => (activeCategory = tab.id)}
              class={`shrink-0 rounded-lg px-2.5 py-1.5 text-[length:var(--vf-text-xs)] ${
                activeCategory === tab.id ? "bg-white/[0.08] text-neutral-100" : "text-neutral-500 hover:text-neutral-200"
              }`}
            >{tab.label}</button>
          {/each}
        </div>

        <div class="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {#each visibleItems as item (item.item_id)}
            <article class={`rounded-xl border p-3 ${selectedIds.includes(item.item_id) ? "border-emerald-400/40 bg-emerald-500/[0.06]" : rejectedIds.includes(item.item_id) ? "border-rose-400/20 bg-rose-500/[0.04] opacity-60" : "border-white/10 bg-white/[0.02]"}`}>
              <div class="flex items-start justify-between gap-2">
                <div class="min-w-0">
                  <h3 class="truncate text-[length:var(--vf-text-sm)] font-semibold text-neutral-100">{item.title}</h3>
                  <p class="mt-0.5 truncate text-[length:var(--vf-text-2xs)] text-neutral-500">{item.category}{item.scene_id ? ` · ${item.scene_id}` : ""}</p>
                </div>
                {#if item.recommended}
                  <span class="rounded-full border border-sky-400/20 bg-sky-400/10 px-1.5 py-0.5 text-[length:var(--vf-text-2xs)] text-sky-100">Recommended</span>
                {/if}
              </div>

              {#if item.start_sec != null && item.end_sec != null}
                <p class="mt-2 inline-flex rounded-full border border-sky-400/20 bg-sky-400/10 px-2 py-0.5 font-mono text-[length:var(--vf-text-2xs)] text-sky-100">
                  {rangeLabel(item)}
                </p>
              {/if}
              {#if item.spoken_context}
                <p class="mt-1 line-clamp-2 text-[length:var(--vf-text-2xs)] italic text-neutral-300">“{item.spoken_context}”</p>
              {/if}
              {#if item.note}
                <p class="mt-1 line-clamp-2 text-[length:var(--vf-text-2xs)] text-amber-200/80">{item.note}</p>
              {/if}

              {#if item.media_type === "style"}
                <div class="mt-3 rounded-lg border border-white/10 bg-black/20 p-2">
                  <div class="flex gap-1">
                    {#each (item.preview_meta.palette ?? []).slice(0, 6) as colour}
                      <span class="h-5 flex-1 rounded" style={`background:${colour}`}></span>
                    {/each}
                  </div>
                  <p class="mt-2 text-[length:var(--vf-text-2xs)] text-neutral-300">{item.preview_meta.fonts?.join(" · ") || "—"} · {item.preview_meta.aspect_ratio || "auto"}</p>
                </div>
              {:else if item.local_path && item.media_type === "audio"}
                <audio class="mt-3 w-full" controls preload="metadata" src={previewSrc(item)} onerror={() => markPreviewError(item)}></audio>
                {#if item.duration_sec}<p class="mt-1 text-[length:var(--vf-text-2xs)] text-neutral-500">{item.duration_sec.toFixed(1)}s</p>{/if}
              {:else if item.local_path && item.media_type === "video"}
                <video class="mt-3 w-full rounded-lg" controls muted playsinline preload="metadata" poster={posterUrl(item)} src={previewSrc(item)} onerror={() => markPreviewError(item)}></video>
              {:else if item.local_path && item.media_type === "image"}
                <img class="mt-3 aspect-video w-full rounded-lg object-cover" src={previewSrc(item)} alt={item.title} onerror={() => markPreviewError(item)} />
              {:else}
                <p class="mt-3 rounded-lg border border-dashed border-white/10 px-2 py-3 text-center text-[length:var(--vf-text-2xs)] text-neutral-500">No media preview</p>
              {/if}

              {#if previewErrors[item.item_id]}
                <div class="mt-2 rounded-lg border border-rose-400/20 bg-rose-500/10 px-2 py-1.5 text-[length:var(--vf-text-2xs)] text-rose-100">
                  <span>{previewErrors[item.item_id]}</span>
                  <button type="button" class="ml-2 underline" onclick={() => retryPreview(item)}>Recarregar</button>
                </div>
              {/if}

              {#if item.reason}
                <p class="mt-2 line-clamp-3 text-[length:var(--vf-text-2xs)] text-neutral-400">{item.reason}</p>
              {/if}

              <div class="mt-3 flex gap-2">
                <button
                  type="button"
                  onclick={() => toggle(item, "selected")}
                  class={`flex-1 rounded-lg border px-2 py-1.5 text-[length:var(--vf-text-2xs)] ${selectedIds.includes(item.item_id) ? "border-emerald-400/40 bg-emerald-500/15 text-emerald-100" : "border-white/10 text-neutral-300"}`}
                >Select</button>
                <button
                  type="button"
                  onclick={() => toggle(item, "rejected")}
                  class={`flex-1 rounded-lg border px-2 py-1.5 text-[length:var(--vf-text-2xs)] ${rejectedIds.includes(item.item_id) ? "border-rose-400/30 bg-rose-500/10 text-rose-100" : "border-white/10 text-neutral-400"}`}
                >Exclude</button>
              </div>
            </article>
          {/each}
        </div>
      </div>
    {/if}
  </div>
</section>
