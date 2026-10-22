<script lang="ts">
  import { Handle, Position } from "@xyflow/svelte";

  let {
    data,
    selected = false
  }: {
    data: { title: string; type: string; params: Record<string, unknown> };
    selected?: boolean;
  } = $props();
</script>

<div
  class={`min-w-[190px] rounded-2xl border px-3 py-2.5 text-left shadow-xl transition ${
    selected
      ? "border-sky-400/70 bg-sky-950/80 ring-2 ring-sky-400/20"
      : "border-neutral-700 bg-neutral-900/95"
  }`}
>
  <Handle type="target" position={Position.Left} class="!h-2.5 !w-2.5 !border-neutral-500 !bg-neutral-800" />
  <p class="text-xs font-semibold text-neutral-100">{data.title}</p>
  <p class="mt-0.5 font-mono text-[10px] text-sky-300/80">{data.type}</p>
  <p class="mt-1 text-[10px] text-neutral-500">
    {Object.keys(data.params ?? {}).length} parameter{Object.keys(data.params ?? {}).length === 1 ? "" : "s"}
  </p>
  <Handle type="source" position={Position.Right} class="!h-2.5 !w-2.5 !border-neutral-500 !bg-sky-500" />
</div>
