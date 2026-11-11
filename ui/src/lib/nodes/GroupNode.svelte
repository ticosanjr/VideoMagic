<script lang="ts">
  let {
    data
  }: {
    data: { label: string; description?: string; color?: string };
  } = $props();

  const color = $derived(data.color || "#38bdf8");
</script>

<div
  class="pointer-events-none h-full w-full rounded-2xl border-2"
  style={`border-color:${color}55;background:${color}0a;`}
>
  <div
    class="m-2 inline-flex max-w-[calc(100%-1rem)] flex-col rounded-lg border px-2.5 py-1.5 shadow-lg"
    style={`border-color:${color}66;background:#09090bee;`}
  >
    <span class="text-[10px] font-semibold uppercase tracking-[0.12em]" style={`color:${color}`}>
      {data.label}
    </span>
    {#if data.description}
      <span class="mt-0.5 max-w-[900px] text-[9px] leading-4 text-neutral-400">
        {data.description}
      </span>
    {/if}
  </div>
</div>
