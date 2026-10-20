<script lang="ts">
  import { errorMessage, getLogs, logDownloadUrl, type LogLine } from "$lib/api";
  import { formatDateTime } from "$lib/format";
  import { modules } from "$lib/modules";

  let {
    jobId,
    module,
    open,
    onclose
  }: {
    jobId: string | null;
    module: string | null;
    open: boolean;
    onclose: () => void;
  } = $props();

  let logs = $state<LogLine[]>([]);
  let selectedModule = $state("all");
  let level = $state("all");
  let loading = $state(false);
  let error = $state("");
  let copied = $state(false);

  const levels = ["all", "debug", "info", "warning", "error"];
  const moduleOptions = modules.map((item) => ({ id: item.id, name: item.name }));

  $effect(() => {
    if (open) {
      selectedModule = module ?? "all";
    }
  });

  $effect(() => {
    if (!open || !jobId) return;
    void load();
    const timer = setInterval(() => void load(), 1200);
    return () => clearInterval(timer);
  });

  async function load() {
    if (!jobId) return;
    loading = true;
    try {
      logs = await getLogs(
        jobId,
        selectedModule === "all" ? undefined : selectedModule,
        level === "all" ? undefined : level
      );
      error = "";
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      loading = false;
    }
  }

  function copy() {
    const text = logs
      .map(
        (line) =>
          `${line.timestamp} ${line.level.toUpperCase()} ${line.module}: ${line.message}`
      )
      .join("\n");
    if (text) {
      void navigator.clipboard.writeText(text);
      copied = true;
      setTimeout(() => (copied = false), 1200);
    }
  }

  function onkeydown(event: KeyboardEvent) {
    if (open && event.key === "Escape") onclose();
  }

  const levelClass: Record<string, string> = {
    debug: "text-neutral-500",
    info: "text-neutral-300",
    warning: "text-amber-300",
    error: "text-rose-300"
  };
</script>

<svelte:window onkeydown={onkeydown} />

{#if open}
  <div
    class="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm"
    role="presentation"
    onclick={(event) => {
      if (event.target === event.currentTarget) onclose();
    }}
  >
    <div
      class="flex h-full w-full max-w-3xl flex-col border-l border-neutral-800 bg-neutral-950 shadow-2xl"
      role="dialog"
      aria-modal="true"
      aria-label="Job logs"
      tabindex="-1"
    >
      <div class="flex flex-wrap items-center gap-3 border-b border-neutral-800 p-4">
        <div class="min-w-0 flex-1">
          <h2 class="text-sm font-semibold">Logs</h2>
          <p class="mt-1 truncate font-mono text-[11px] text-neutral-500">
            {jobId ?? "no job"} · {selectedModule} · {logs.length} lines
          </p>
        </div>
        <button
          type="button"
          onclick={copy}
          class="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300 hover:border-neutral-500"
        >
          {copied ? "Copied" : "Copy"}
        </button>
        {#if jobId}
          <a
            class="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300 hover:border-neutral-500"
            href={logDownloadUrl(jobId, selectedModule === "all" ? undefined : selectedModule)}
          >
            Download
          </a>
        {/if}
        <button
          type="button"
          onclick={onclose}
          class="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300 hover:border-neutral-500"
          aria-label="Close logs"
        >
          Close
        </button>
      </div>

      <div class="flex flex-wrap gap-2 border-b border-neutral-800 px-4 py-3">
        <select
          bind:value={selectedModule}
          aria-label="Filter logs by module"
          class="rounded-lg border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-xs text-neutral-200"
        >
          <option value="all">All modules</option>
          {#each moduleOptions as item}
            <option value={item.id}>{item.name}</option>
          {/each}
        </select>
        <select
          bind:value={level}
          aria-label="Filter logs by level"
          class="rounded-lg border border-neutral-700 bg-neutral-900 px-3 py-1.5 text-xs text-neutral-200"
        >
          {#each levels as item}
            <option value={item}>{item}</option>
          {/each}
        </select>
        {#if loading}
          <span class="self-center text-[11px] text-neutral-500">refreshing…</span>
        {/if}
      </div>

      {#if error}
        <p class="m-4 rounded-lg bg-rose-950/40 p-3 text-xs text-rose-300">{error}</p>
      {/if}

      <div class="min-h-0 flex-1 overflow-auto p-3 font-mono text-[11px] leading-5">
        {#if logs.length === 0}
          <p class="p-3 text-neutral-500">No log lines yet.</p>
        {:else}
          {#each logs as line}
            <div class="grid grid-cols-[auto_auto_auto_1fr] gap-2 border-b border-neutral-900/80 px-2 py-1">
              <span class="text-neutral-600">{formatDateTime(line.timestamp)}</span>
              <span class="w-16 uppercase {levelClass[line.level] ?? 'text-neutral-400'}">{line.level}</span>
              <span class="w-20 text-sky-400/80">{line.module}</span>
              <span class="whitespace-pre-wrap break-words text-neutral-300">{line.message}</span>
            </div>
          {/each}
        {/if}
      </div>
    </div>
  </div>
{/if}
