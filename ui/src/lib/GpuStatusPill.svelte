<script lang="ts">
  import { onMount } from "svelte";
  import {
    getGpuStatus,
    patchGpuSettings,
    type GpuWorkerStatus
  } from "$lib/api";
  import { gpuPill } from "$lib/gpuStatus";

  let { onopen = () => {} }: { onopen?: () => void } = $props();

  let status = $state<GpuWorkerStatus | null>(null);
  let open = $state(false);
  let busy = $state(false);
  let error = $state("");

  const view = $derived(gpuPill(status));

  async function refresh() {
    try {
      const payload = await getGpuStatus();
      status = payload.status;
      error = "";
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    }
  }

  async function setMode(mode: "auto" | "local_only" | "local_gpu") {
    busy = true;
    try {
      const payload = await patchGpuSettings({ mode });
      status = payload.status;
      error = "";
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    } finally {
      busy = false;
    }
  }

  onMount(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 30_000);
    return () => clearInterval(timer);
  });
</script>

<div class="relative">
  <button
    type="button"
    data-testid="gpu-status-pill"
    aria-haspopup="dialog"
    aria-expanded={open}
    aria-label={`GPU status: ${view.label}`}
    title={view.label}
    onclick={() => (open = !open)}
    class={`inline-flex h-9 items-center gap-1.5 rounded-lg border px-2.5 text-left text-[length:var(--vf-text-2xs)] font-medium transition-colors ${
      view.tone === "ready"
        ? "border-emerald-400/25 bg-emerald-500/10 text-emerald-100"
        : view.tone === "busy"
          ? "border-sky-400/25 bg-sky-500/10 text-sky-100"
          : view.tone === "local"
            ? "border-white/10 bg-white/[0.03] text-neutral-300"
            : "border-amber-400/25 bg-amber-500/10 text-amber-100"
    }`}
  >
    <span
      class={`h-1.5 w-1.5 shrink-0 rounded-full ${
        view.tone === "ready"
          ? "bg-emerald-400"
          : view.tone === "busy"
            ? "animate-pulse bg-sky-400"
            : view.tone === "local"
              ? "bg-neutral-400"
              : "bg-amber-400"
      }`}
      aria-hidden="true"
    ></span>
    <span class="hidden max-w-44 truncate sm:inline">{view.label}</span>
    <span class="sm:hidden" aria-hidden="true">GPU</span>
  </button>

  {#if open}
    <div
      role="dialog"
      aria-label="GPU acceleration"
      data-testid="gpu-popover"
      class="absolute right-0 z-40 mt-2 w-72 rounded-xl border border-white/10 bg-neutral-950 p-3 text-[length:var(--vf-text-xs)] shadow-2xl shadow-black/50"
    >
      <div class="flex items-start justify-between gap-2">
        <div>
          <p class="font-semibold text-neutral-100">{view.label}</p>
          <p class="mt-0.5 text-neutral-500">
            {status?.mode === "local_gpu"
              ? `CUDA/NVENC local${status.gpu_name ? `: ${status.gpu_name}` : ""}.`
              : status?.available
                ? `${status.hostname || status.worker_id || "worker"} · queue ${status.queue_depth}`
                : status?.mode === "local_only"
                  ? "Automatic GPU placement is disabled."
                  : "No worker is paired. Local execution stays available."}
          </p>
        </div>
        <button
          type="button"
          class="rounded p-1 text-neutral-500 hover:text-neutral-200"
          aria-label="Close GPU status"
          onclick={() => (open = false)}
        >×</button>
      </div>

      <div class="mt-3 grid gap-1.5">
        <button
          type="button"
          data-testid="gpu-mode-auto"
          disabled={busy}
          onclick={() => void setMode("auto")}
          class={`rounded-lg border px-2.5 py-2 text-left ${
            status?.mode === "auto"
              ? "border-sky-400/30 bg-sky-500/10 text-sky-100"
              : "border-white/10 text-neutral-300"
          }`}
        >
          Automatic — use GPU when available
        </button>
        <button
          type="button"
          data-testid="gpu-mode-local-gpu"
          disabled={busy}
          onclick={() => void setMode("local_gpu")}
          class={`rounded-lg border px-2.5 py-2 text-left ${
            status?.mode === "local_gpu"
              ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-100"
              : "border-white/10 text-neutral-300"
          }`}
        >
          Local GPU — CUDA/NVENC on this computer
        </button>
        <button
          type="button"
          data-testid="gpu-mode-local"
          disabled={busy}
          onclick={() => void setMode("local_only")}
          class={`rounded-lg border px-2.5 py-2 text-left ${
            status?.mode === "local_only"
              ? "border-emerald-400/30 bg-emerald-500/10 text-emerald-100"
              : "border-white/10 text-neutral-300"
          }`}
        >
          Force local — run everything on this computer
        </button>
        <button
          type="button"
          data-testid="gpu-open-settings"
          onclick={() => {
            open = false;
            onopen();
          }}
          class="rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-2 text-left text-sky-200"
        >
          Open GPU settings
        </button>
      </div>
      {#if error}
        <p class="mt-2 text-amber-300" role="status">{error}</p>
      {/if}
    </div>
  {/if}
</div>
