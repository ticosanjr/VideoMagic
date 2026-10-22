<script lang="ts">
  import { Handle, Position } from "@xyflow/svelte";

  let {
    data,
    selected = false
  }: {
    data: {
      title: string;
      type: string;
      params: Record<string, unknown>;
      status?: "idle" | "running" | "cached" | "executed" | "failed";
    };
    selected?: boolean;
  } = $props();
</script>

<div
  data-testid={`step-${data.type}`}
  class={`min-w-[190px] rounded-2xl border px-3 py-2.5 text-left shadow-xl transition ${
    selected
      ? "border-sky-400/70 bg-sky-950/80 ring-2 ring-sky-400/20"
      : data.status === "failed"
        ? "border-rose-500/60 bg-rose-950/60"
        : data.status === "running"
          ? "border-amber-400/60 bg-amber-950/40"
          : "border-neutral-700 bg-neutral-900/95"
  }`}
>
  <Handle type="target" position={Position.Left} class="!h-2.5 !w-2.5 !border-neutral-500 !bg-neutral-800" />
  <div class="flex items-start justify-between gap-2">
    <div class="min-w-0">
      <p class="truncate text-xs font-semibold text-neutral-100">{data.title}</p>
      <p class="mt-0.5 font-mono text-[10px] text-sky-300/80">{data.type}</p>
    </div>
    {#if data.status && data.status !== "idle"}
      <span
        class={`shrink-0 rounded-full px-1.5 py-0.5 text-[8px] font-medium uppercase tracking-wide ${
          data.status === "cached"
            ? "bg-emerald-500/15 text-emerald-300"
            : data.status === "executed"
              ? "bg-sky-500/15 text-sky-300"
              : data.status === "running"
                ? "animate-pulse bg-amber-500/15 text-amber-300"
                : "bg-rose-500/15 text-rose-300"
        }`}
      >
        {data.status}
      </span>
    {/if}
  </div>
  <p class="mt-1 text-[10px] text-neutral-500">
    {Object.keys(data.params ?? {}).length} parameter{Object.keys(data.params ?? {}).length === 1 ? "" : "s"}
  </p>
  <Handle type="source" position={Position.Right} class="!h-2.5 !w-2.5 !border-neutral-500 !bg-sky-500" />
</div>
