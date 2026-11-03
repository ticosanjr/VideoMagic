<script lang="ts">
  import { onMount, type Snippet } from "svelte";

  let {
    inspect,
    effects,
    class: className = ""
  }: {
    inspect: Snippet;
    effects: Snippet;
    class?: string;
  } = $props();

  let activeTab = $state<"inspect" | "effects">("inspect");

  onMount(() => {
    try {
      const saved = localStorage.getItem("videoflow.timelineInspectorTab");
      if (saved === "effects") activeTab = "effects";
    } catch {
      /* private mode */
    }
  });

  function choose(tab: "inspect" | "effects") {
    activeTab = tab;
    try {
      localStorage.setItem("videoflow.timelineInspectorTab", tab);
    } catch {
      /* private mode */
    }
  }
</script>

<div class={`flex min-h-0 flex-col rounded-xl border border-neutral-800 bg-neutral-900/40 ${className}`} data-testid="timeline-inspector">
  <div class="flex shrink-0 items-center gap-1 border-b border-neutral-800 p-2" role="tablist" aria-label="Timeline inspector">
    <button
      type="button"
      role="tab"
      aria-selected={activeTab === "inspect"}
      onclick={() => choose("inspect")}
      class={`rounded-lg px-2.5 py-1 text-[10px] ${activeTab === "inspect" ? "bg-sky-500/15 text-sky-200 ring-1 ring-inset ring-sky-400/30" : "text-neutral-400 hover:text-neutral-200"}`}
    >Inspect</button>
    <button
      type="button"
      role="tab"
      aria-selected={activeTab === "effects"}
      onclick={() => choose("effects")}
      class={`rounded-lg px-2.5 py-1 text-[10px] ${activeTab === "effects" ? "bg-violet-500/15 text-violet-200 ring-1 ring-inset ring-violet-400/30" : "text-neutral-400 hover:text-neutral-200"}`}
    >Effects</button>
  </div>
  <div class="min-h-0 flex-1 space-y-2 overflow-y-auto p-1 pr-1">
    {#if activeTab === "inspect"}
      {@render inspect()}
    {:else}
      {@render effects()}
    {/if}
  </div>
</div>
