<script lang="ts">
  import type { Node } from "@xyflow/svelte";
  import Icon from "$lib/ui/Icon.svelte";

  let {
    nodes,
    selectedId,
    nodeData,
    onSelect
  }: {
    nodes: Node[];
    selectedId: string | null;
    nodeData: (node: Node) => { title: string; type: string };
    onSelect: (id: string) => void;
  } = $props();
</script>

<div class="space-y-2 rounded-xl border border-neutral-800 bg-neutral-950 p-3" data-testid="recipe-step-list">
  <p class="vf-label">Step list</p>
  <p class="text-[length:var(--vf-text-xs)] text-neutral-500">Tap a step to edit its parameters. The graph editor needs a wider screen.</p>
  <ol class="space-y-1.5">
    {#each nodes.filter((node) => node.type === "step") as node (node.id)}
      <li>
        <button type="button" onclick={() => onSelect(node.id)} class={`flex w-full items-center justify-between gap-2 rounded-lg border px-3 py-2 text-left ${selectedId === node.id ? "border-sky-500/40 bg-sky-500/10" : "border-neutral-800 bg-neutral-900/50"}`}>
          <span class="min-w-0">
            <span class="block truncate text-[length:var(--vf-text-xs)] font-medium text-neutral-100">{nodeData(node).title}</span>
            <span class="block truncate font-mono text-[length:var(--vf-text-2xs)] text-neutral-500">{nodeData(node).type}</span>
          </span>
          <Icon name="chevron" size={14} class="shrink-0 -rotate-90 text-neutral-500" />
        </button>
      </li>
    {/each}
  </ol>
</div>
