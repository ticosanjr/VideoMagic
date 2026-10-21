<script lang="ts">
  import { tick } from "svelte";
  import {
    createDirectory,
    errorMessage,
    listDirectory,
    type FsEntry,
    type FsListing
  } from "$lib/api";
  import { formatBytes, formatDateTime } from "$lib/format";

  type PickerMode = "file" | "directory";

  let {
    open,
    mode,
    title,
    extensions = [],
    initialPath = "",
    suggestedName = "",
    onclose,
    onselect
  }: {
    open: boolean;
    mode: PickerMode;
    title: string;
    extensions?: string[];
    initialPath?: string;
    suggestedName?: string;
    onclose: () => void;
    onselect: (path: string, entry?: FsEntry) => void;
  } = $props();

  let listing = $state<FsListing | null>(null);
  let loading = $state(false);
  let creating = $state(false);
  let error = $state("");
  let selected = $state<FsEntry | null>(null);
  let query = $state("");
  let showHidden = $state(false);
  let newFolder = $state("");
  let dialog = $state<HTMLDivElement | null>(null);
  let loadedKey = $state("");
  let failedPath = $state("");

  const filtered = $derived(
    listing?.entries.filter((entry) => {
      if (!query.trim()) return true;
      return entry.name.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase());
    }) ?? []
  );

  const selectedPath = $derived(selected?.path ?? (mode === "directory" ? listing?.path : ""));

  $effect(() => {
    const key = `${mode}:${initialPath}:${extensions.join(",")}`;
    if (!open) {
      loadedKey = "";
      return;
    }
    if (loadedKey === key) return;
    loadedKey = key;
    newFolder = suggestedName;
    void load(initialPath || undefined);
    void tick().then(() => dialog?.focus());
  });

  async function load(path?: string, keepFocus = false) {
    loading = true;
    error = "";
    selected = null;
    if (!keepFocus) query = "";
    try {
      listing = await listDirectory({
        path,
        mode,
        extensions,
        showHidden,
        limit: 500
      });
    } catch (reason) {
      failedPath = path ?? "";
      error = errorMessage(reason);
    } finally {
      loading = false;
    }
  }

  async function openFirstAllowedFolder() {
    await load(undefined);
  }

  async function toggleHidden() {
    showHidden = !showHidden;
    await load(listing?.path, true);
  }

  function openEntry(entry: FsEntry) {
    if (entry.kind === "directory") {
      void load(entry.path);
    } else {
      selected = entry;
    }
  }

  function choose(entry?: FsEntry) {
    const path = entry?.path ?? selectedPath;
    if (!path) return;
    onselect(path, entry ?? selected ?? undefined);
    onclose();
  }

  async function makeFolder() {
    if (!listing || !newFolder.trim() || creating) return;
    creating = true;
    error = "";
    try {
      const created = await createDirectory(listing.path, newFolder.trim());
      newFolder = "";
      await load(created.path);
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      creating = false;
    }
  }

  function handleKeydown(event: KeyboardEvent) {
    if (event.key === "Escape") {
      event.stopPropagation();
      onclose();
      return;
    }
    if (event.key !== "Tab" || !dialog) return;
    const focusable = Array.from(
      dialog.querySelectorAll<HTMLElement>(
        'button:not([disabled]), input:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )
    ).filter((element) => element.offsetParent !== null);
    if (focusable.length === 0) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }
</script>

{#if open}
  <div
    class="fixed inset-0 z-50 flex items-end justify-center bg-black/70 p-3 backdrop-blur-sm sm:items-center"
    role="presentation"
    onclick={(event) => {
      if (event.target === event.currentTarget) onclose();
    }}
  >
    <div
      bind:this={dialog}
      role="dialog"
      aria-modal="true"
      aria-label={title}
      tabindex="-1"
      data-testid="path-picker"
      onkeydown={handleKeydown}
      class="flex max-h-[88vh] w-full max-w-3xl flex-col overflow-hidden rounded-3xl border border-white/10 bg-neutral-950 shadow-2xl shadow-black/50 outline-none"
    >
      <header class="flex items-start justify-between gap-4 border-b border-white/10 px-5 py-4">
        <div>
          <p class="text-[10px] font-semibold uppercase tracking-[0.2em] text-sky-400">
            {mode === "file" ? "Local file" : "Output folder"}
          </p>
          <h2 class="mt-1 text-lg font-semibold text-neutral-100">{title}</h2>
          <p class="mt-1 text-xs text-neutral-500">
            {mode === "file"
              ? "Choose a file on the machine running VideoFlow. Nothing is uploaded."
              : "Choose a writable folder for the project output."}
          </p>
        </div>
        <button
          type="button"
          onclick={onclose}
          aria-label="Close picker"
          class="rounded-xl border border-white/10 p-2 text-neutral-400 transition hover:border-white/20 hover:text-neutral-100"
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
            <path d="m6 6 12 12M18 6 6 18" />
          </svg>
        </button>
      </header>

      <div class="border-b border-white/10 px-5 py-3">
        <div class="flex flex-wrap gap-2">
          {#each listing?.roots ?? [] as root}
            <button
              type="button"
              onclick={() => void load(root.path)}
              disabled={!root.exists}
              class="rounded-full border border-white/10 px-3 py-1 text-[11px] text-neutral-400 transition hover:border-sky-500/50 hover:text-sky-300 disabled:opacity-40"
            >
              {root.name}
            </button>
          {/each}
          {#if mode === "file"}
            <span class="ml-auto self-center text-[10px] uppercase tracking-wide text-neutral-600">
              {extensions.length ? extensions.join(" · ") : "All files"}
            </span>
          {/if}
        </div>

        <div class="mt-3 flex items-center gap-2 overflow-x-auto pb-1 text-xs text-neutral-500">
          <button
            type="button"
            onclick={() => listing?.parent && void load(listing.parent.path)}
            disabled={!listing?.parent || loading}
            aria-label="Go to parent folder"
            class="rounded-lg border border-white/10 p-1.5 text-neutral-400 transition hover:border-white/20 hover:text-neutral-100 disabled:opacity-30"
          >
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <path d="M12 19V5M5 12l7-7 7 7" />
            </svg>
          </button>
          <div class="flex min-w-0 items-center gap-1">
            {#each listing?.breadcrumbs ?? [] as crumb, index}
              {#if index > 0}<span class="text-neutral-700">/</span>{/if}
              <button
                type="button"
                onclick={() => void load(crumb.path)}
                class="max-w-40 truncate rounded px-1.5 py-1 transition hover:bg-white/5 hover:text-neutral-200"
              >
                {crumb.name}
              </button>
            {/each}
          </div>
        </div>

        <div class="mt-3 flex flex-col gap-2 sm:flex-row">
          <label class="relative flex-1">
            <span class="sr-only">Search this folder</span>
            <svg class="pointer-events-none absolute left-3 top-2.5 text-neutral-600" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
              <circle cx="11" cy="11" r="7" />
              <path d="m20 20-4-4" />
            </svg>
            <input
              bind:value={query}
              data-testid="picker-search"
              placeholder="Search this folder"
              class="w-full rounded-xl border border-white/10 bg-neutral-900 py-2 pl-9 pr-3 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-sky-500 focus:outline-none"
            />
          </label>
          <div class="flex gap-2">
            <button
              type="button"
              onclick={() => void toggleHidden()}
              class="rounded-xl border border-white/10 px-3 py-2 text-xs text-neutral-400 transition hover:border-white/20 hover:text-neutral-200"
            >
              {showHidden ? "Hide hidden" : "Show hidden"}
            </button>
            {#if mode === "directory"}
              <div class="flex min-w-0 flex-1 gap-1 sm:flex-none">
                <input
                  bind:value={newFolder}
                  data-testid="picker-new-folder"
                  placeholder="New folder"
                  aria-label="New folder name"
                  onkeydown={(event) => {
                    if (event.key === "Enter") void makeFolder();
                  }}
                  class="min-w-0 flex-1 rounded-xl border border-white/10 bg-neutral-900 px-3 py-2 text-sm text-neutral-200 placeholder:text-neutral-600 focus:border-sky-500 focus:outline-none"
                />
                <button
                  type="button"
                  data-testid="picker-create-folder"
                  onclick={() => void makeFolder()}
                  disabled={creating || !newFolder.trim() || !listing?.can_write}
                  class="rounded-xl bg-white/10 px-3 py-2 text-xs font-medium text-neutral-200 transition hover:bg-white/15 disabled:opacity-40"
                >
                  {creating ? "Creating…" : "Create"}
                </button>
              </div>
            {/if}
          </div>
        </div>
      </div>

      <div class="min-h-48 flex-1 overflow-y-auto px-3 py-2">
        {#if loading}
          <div class="space-y-2 p-2" aria-label="Loading folder">
            {#each [1, 2, 3, 4] as row}
              <div class="h-12 animate-pulse rounded-xl bg-white/5" aria-hidden="true"></div>
            {/each}
          </div>
        {:else if error && !listing}
          <div class="m-2 rounded-xl border border-rose-500/20 bg-rose-950/30 p-4 text-sm text-rose-300">
            <p class="font-medium">Could not open this folder.</p>
            {#if failedPath}<p class="mt-1 break-all font-mono text-[10px] text-rose-300/60">{failedPath}</p>{/if}
            <p class="mt-1 break-words text-xs opacity-80">{error}</p>
            <div class="mt-3 flex flex-wrap gap-2">
              <button
                type="button"
                onclick={() => void load(initialPath || undefined)}
                class="rounded-lg border border-rose-400/30 px-3 py-1.5 text-xs transition hover:bg-rose-500/10"
              >
                Try again
              </button>
              <button
                type="button"
                onclick={() => void openFirstAllowedFolder()}
                class="rounded-lg border border-white/15 px-3 py-1.5 text-xs text-neutral-300 transition hover:bg-white/5"
              >
                Open Home folder
              </button>
            </div>
          </div>
        {:else if filtered.length === 0}
          <div class="flex min-h-48 flex-col items-center justify-center text-center">
            <div class="rounded-2xl border border-white/10 bg-white/5 p-3 text-neutral-500">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" />
              </svg>
            </div>
            <p class="mt-3 text-sm text-neutral-400">Nothing here.</p>
            <p class="mt-1 text-xs text-neutral-600">
              {query ? "Try another search." : "This folder has no matching entries."}
            </p>
          </div>
        {:else}
          <div class="space-y-1">
            {#each filtered as entry}
              <button
                type="button"
                data-testid="picker-entry"
                data-name={entry.name}
                onclick={() => openEntry(entry)}
                ondblclick={() => {
                  if (entry.kind === "file") choose(entry);
                  else void load(entry.path);
                }}
                aria-pressed={selected?.path === entry.path}
                class={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition ${
                  selected?.path === entry.path
                    ? "bg-sky-500/10 ring-1 ring-inset ring-sky-500/30"
                    : "hover:bg-white/5"
                }`}
              >
                <span class={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl ${entry.kind === "directory" ? "bg-amber-400/10 text-amber-300" : "bg-sky-400/10 text-sky-300"}`}>
                  {#if entry.kind === "directory"}
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                      <path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" />
                    </svg>
                  {:else}
                    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                      <rect x="3" y="5" width="18" height="14" rx="2" />
                      <path d="m10 9 5 3-5 3V9Z" />
                    </svg>
                  {/if}
                </span>
                <span class="min-w-0 flex-1">
                  <span class="block truncate text-sm text-neutral-200">{entry.name}</span>
                  <span class="mt-0.5 block text-[10px] text-neutral-600">
                    {entry.kind === "directory" ? "Folder" : formatBytes(entry.size_bytes)}
                    {#if entry.modified_at} · {formatDateTime(entry.modified_at)}{/if}
                    {#if entry.is_symlink} · link{/if}
                  </span>
                </span>
                {#if entry.kind === "directory"}
                  <svg class="text-neutral-600" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
                    <path d="m9 18 6-6-6-6" />
                  </svg>
                {:else if selected?.path === entry.path}
                  <svg class="text-sky-400" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true">
                    <path d="m5 12 4 4L19 6" />
                  </svg>
                {/if}
              </button>
            {/each}
          </div>
          {#if listing?.truncated}
            <p class="px-2 py-3 text-center text-[11px] text-neutral-600">
              Showing the first 500 entries. Refine the search to narrow the list.
            </p>
          {/if}
        {/if}
      </div>

      {#if error && listing}
        <p class="border-t border-rose-500/20 bg-rose-950/20 px-5 py-2 text-xs text-rose-300">{error}</p>
      {/if}

      <footer class="flex flex-col gap-3 border-t border-white/10 bg-white/[0.02] px-5 py-4 sm:flex-row sm:items-center">
        <div class="min-w-0 flex-1">
          <p class="text-[10px] uppercase tracking-wide text-neutral-600">
            {mode === "directory" ? "Selected folder" : "Selected file"}
          </p>
          <p class="mt-1 break-all font-mono text-[11px] text-neutral-300">
            {selectedPath || "Choose a file to continue"}
          </p>
          {#if mode === "directory" && listing && !listing.can_write}
            <p class="mt-1 text-[10px] text-amber-300">This folder is not writable.</p>
          {/if}
        </div>
        <div class="flex shrink-0 gap-2">
          <button
            type="button"
            onclick={onclose}
            class="rounded-xl border border-white/10 px-4 py-2 text-sm text-neutral-400 transition hover:border-white/20 hover:text-neutral-200"
          >
            Cancel
          </button>
          <button
            type="button"
            data-testid="picker-select"
            onclick={() => choose()}
            disabled={!selectedPath || loading || (mode === "directory" && !listing?.can_write)}
            class="rounded-xl bg-sky-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-sky-500 disabled:opacity-40"
          >
            {mode === "directory" ? "Use this folder" : "Select file"}
          </button>
        </div>
      </footer>
    </div>
  </div>
{/if}
