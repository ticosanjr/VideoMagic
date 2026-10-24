<script lang="ts">
  let { open = false, onclose }: { open?: boolean; onclose: () => void } = $props();

  const SHORTCUTS: { keys: string; action: string }[] = [
    { keys: "Ctrl/Cmd + K", action: "Open the command palette" },
    { keys: "?", action: "Show this shortcut reference" },
    { keys: "Esc", action: "Close the palette, drawer, or dialog" },
    { keys: "G then R", action: "Go to Recipes" },
    { keys: "G then J", action: "Go to Jobs" },
    { keys: "G then T", action: "Go to Timeline" },
    { keys: "G then A", action: "Go to Assets" },
    { keys: "G then S", action: "Go to Settings" },
    { keys: "N", action: "Open the notification center" },
    { keys: "U", action: "Open the activity drawer" }
  ];
</script>

{#if open}
  <div class="fixed inset-0 z-[70] flex items-center justify-center px-4" role="presentation">
    <button type="button" class="absolute inset-0 bg-black/50" aria-label="Close shortcuts" onclick={onclose}></button>
    <div
      class="relative w-full max-w-lg overflow-hidden rounded-2xl border border-neutral-700 bg-neutral-950 shadow-2xl shadow-black/60"
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
      data-testid="shortcuts-modal"
    >
      <header class="flex items-center justify-between border-b border-neutral-800 px-4 py-3">
        <div>
          <h2 class="text-sm font-medium text-white">Keyboard shortcuts</h2>
          <p class="mt-0.5 text-[11px] text-neutral-500">Every critical action is reachable without the mouse.</p>
        </div>
        <button type="button" class="rounded-lg border border-white/10 px-2 py-1 text-[11px] text-neutral-400 hover:text-neutral-100" onclick={onclose}>Close</button>
      </header>
      <dl class="divide-y divide-neutral-900 px-4 py-2">
        {#each SHORTCUTS as shortcut}
          <div class="flex items-center justify-between gap-4 py-2 text-xs">
            <dt class="text-neutral-300">{shortcut.action}</dt>
            <dd class="shrink-0"><kbd class="rounded border border-neutral-700 bg-white/[0.03] px-2 py-0.5 font-mono text-[10px] text-neutral-300">{shortcut.keys}</kbd></dd>
          </div>
        {/each}
      </dl>
    </div>
  </div>
{/if}
