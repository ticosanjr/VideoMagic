<script lang="ts">
  let {
    open = $bindable(false),
    step = $bindable(0)
  }: {
    open?: boolean;
    step?: number;
  } = $props();
</script>

{#if open}
  <div class="fixed inset-0 z-[110] flex items-center justify-center bg-black/75 p-4" role="presentation"
    onclick={(event) => { if (event.currentTarget === event.target) open = false; }}>
    <div class="w-full max-w-md rounded-2xl border border-sky-500/30 bg-neutral-950 p-5 shadow-2xl" role="dialog" aria-modal="true" aria-label="Builder tour" data-testid="builder-tour">
      <div class="flex items-center justify-between">
        <p class="text-[10px] uppercase tracking-wide text-sky-300">Step {step + 1} of 3</p>
        <button type="button" onclick={() => (open = false)} class="rounded px-2 text-neutral-500 hover:text-neutral-200" aria-label="Close tour">×</button>
      </div>
      {#if step === 0}
        <h3 class="mt-3 text-base font-semibold text-white">Build the graph</h3>
        <p class="mt-2 text-xs leading-relaxed text-neutral-400">Use <span class="text-sky-300">Add step</span> to place nodes, then drag from a node's right handle to the next node's input. The More menu holds validation, history, batch, and export actions.</p>
      {:else if step === 1}
        <h3 class="mt-3 text-base font-semibold text-white">Inspect and edit</h3>
        <p class="mt-2 text-xs leading-relaxed text-neutral-400">Click a node to open the inspector. It shows every input, output, preset, and field with help text. Edits autosave; Ctrl/Cmd+Z undoes them.</p>
      {:else}
        <h3 class="mt-3 text-base font-semibold text-white">Stay oriented</h3>
        <p class="mt-2 text-xs leading-relaxed text-neutral-400">Use Find node to dim the rest of the graph, shift-drag to select several nodes, and the selection bar to align, duplicate, delete, or fit them. Ctrl/Cmd+K searches every builder action.</p>
      {/if}
      <div class="mt-5 flex items-center justify-between">
        <button type="button" onclick={() => (open = false)} class="text-[10px] text-neutral-500 hover:text-neutral-200">Skip</button>
        <div class="flex gap-1.5">
          {#if step > 0}<button type="button" onclick={() => (step -= 1)} class="rounded-lg border border-neutral-700 px-2.5 py-1 text-[11px] text-neutral-300">Back</button>{/if}
          {#if step < 2}
            <button type="button" onclick={() => (step += 1)} class="rounded-lg bg-sky-500 px-3 py-1 text-[11px] font-medium text-neutral-950">Next</button>
          {:else}
            <button type="button" onclick={() => (open = false)} class="rounded-lg bg-sky-500 px-3 py-1 text-[11px] font-medium text-neutral-950">Done</button>
          {/if}
        </div>
      </div>
    </div>
  </div>
{/if}
