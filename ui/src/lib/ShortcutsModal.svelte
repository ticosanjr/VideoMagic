<script lang="ts">
  import { focusTrap } from "$lib/a11y";
  import { i18n } from "$lib/i18n.svelte";

  let { open = false, onclose }: { open?: boolean; onclose: () => void } = $props();

  const SHORTCUTS: { keys: string; action: string }[] = [
    { keys: "Ctrl/Cmd + K", action: "Open the command palette" },
    { keys: "?", action: "Show this shortcut reference" },
    { keys: "Esc", action: "Close the palette, drawer, or dialog" },
    { keys: "g then r", action: "Produce · Recipes" },
    { keys: "g then c", action: "Produce · Assistant" },
    { keys: "g then t", action: "Edit · Timeline" },
    { keys: "g then j", action: "Runs · Jobs" },
    { keys: "g then u", action: "Runs · Schedules" },
    { keys: "g then a", action: "Library · Media" },
    { keys: "g then l", action: "Library · Brand" },
    { keys: "g then m", action: "Setup · AI models" },
    { keys: "g then p", action: "Setup · AI providers" },
    { keys: "g then e", action: "Setup · Extensions" },
    { keys: "g then i", action: "Setup · Connect" },
    { keys: "g then s", action: "Setup · Settings" },
    { keys: "n", action: "Open the notification center" },
    { keys: "u", action: "Open the activity drawer" },
    { keys: "Space / K", action: "Timeline: play or pause" },
    { keys: "J / L", action: "Timeline: step back or forward 1 second" },
    { keys: "Shift + J / L", action: "Timeline: previous or next segment" },
    { keys: "← / →", action: "Timeline: one frame" },
    { keys: "Shift + ← / →", action: "Timeline: one second" },
    { keys: "Home / End", action: "Timeline: jump to start or end" },
    { keys: "S", action: "Timeline: split at the playhead" },
    { keys: "Delete / Shift+Delete", action: "Timeline: delete or ripple delete" },
    { keys: "M", action: "Timeline: add marker" },
    { keys: "+ / -", action: "Timeline: zoom" },
    { keys: "F", action: "Timeline: fit" },
    { keys: "[ / ]", action: "Timeline: speed down or up 0.5x" },
    { keys: "Ctrl/Cmd + S", action: "Timeline: save a version" },
    { keys: "Ctrl/Cmd + O", action: "Timeline: open saved versions" }
  ];
</script>

{#if open}
  <div class="fixed inset-0 z-[110] flex items-center justify-center px-4" role="presentation">
    <button type="button" class="absolute inset-0 bg-black/50" aria-label="Close shortcuts" onclick={onclose}></button>
    <div
      class="relative w-full max-w-lg overflow-hidden rounded-2xl border border-neutral-700 bg-neutral-950 shadow-2xl shadow-black/60"
      use:focusTrap
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
      data-testid="shortcuts-modal"
    >
      <header class="flex items-center justify-between border-b border-neutral-800 px-4 py-3">
        <div>
          <h2 class="text-sm font-medium text-white">{i18n.t("shortcuts")}</h2>
          <p class="mt-0.5 text-[11px] text-neutral-500">Every critical action is reachable without the mouse.</p>
        </div>
        <button type="button" class="rounded-lg border border-white/10 px-2 py-1 text-[11px] text-neutral-400 hover:text-neutral-100" onclick={onclose}>{i18n.t("close")}</button>
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
