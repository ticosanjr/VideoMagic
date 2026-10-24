<script lang="ts">
  import { filterCommands, moveActiveIndex, type Command } from "$lib/commandPalette";

  let {
    open = false,
    commands = [],
    onrun,
    onclose
  }: {
    open?: boolean;
    commands?: Command[];
    onrun: (command: Command) => void;
    onclose: () => void;
  } = $props();

  let query = $state("");
  let active = $state(0);
  let input = $state<HTMLInputElement | null>(null);

  const results = $derived(filterCommands(commands, query));

  $effect(() => {
    if (open) {
      query = "";
      active = 0;
      requestAnimationFrame(() => input?.focus());
    }
  });

  $effect(() => {
    if (active >= results.length) active = Math.max(0, results.length - 1);
  });

  function run(command: Command | undefined) {
    if (!command) return;
    onrun(command);
  }

  function onKeydown(event: KeyboardEvent) {
    if (event.key === "ArrowDown") {
      event.preventDefault();
      active = moveActiveIndex(active, results.length, 1);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      active = moveActiveIndex(active, results.length, -1);
    } else if (event.key === "Enter") {
      event.preventDefault();
      run(results[active]);
    } else if (event.key === "Escape") {
      event.preventDefault();
      onclose();
    }
  }
</script>

{#if open}
  <div class="fixed inset-0 z-[75] flex items-start justify-center px-4 pt-[12vh]" role="presentation">
    <button type="button" class="absolute inset-0 bg-black/50 backdrop-blur-sm" aria-label="Close command palette" onclick={onclose}></button>
    <div
      class="relative w-full max-w-xl overflow-hidden rounded-2xl border border-neutral-700 bg-neutral-950 shadow-2xl shadow-black/60"
      role="dialog"
      aria-modal="true"
      aria-label="Command palette"
      data-testid="command-palette"
    >
      <div class="border-b border-neutral-800 px-4 py-3">
        <input
          bind:this={input}
          bind:value={query}
          onkeydown={onKeydown}
          type="text"
          class="w-full bg-transparent text-sm text-white placeholder:text-neutral-500 focus:outline-none"
          placeholder="Type a command…"
          aria-label="Search commands"
          autocomplete="off"
          spellcheck="false"
        />
      </div>
      <ul class="max-h-[50vh] overflow-auto p-2" role="listbox" aria-label="Commands">
        {#if results.length === 0}
          <li class="px-3 py-6 text-center text-xs text-neutral-500">No matching command.</li>
        {/if}
        {#each results as command, index (command.id)}
          <li role="option" aria-selected={index === active}>
            <button
              type="button"
              class={`flex w-full items-center justify-between gap-3 rounded-xl px-3 py-2 text-left text-xs ${index === active ? "bg-sky-500/15 text-sky-100 ring-1 ring-inset ring-sky-400/25" : "text-neutral-300 hover:bg-white/5"}`}
              onmouseenter={() => (active = index)}
              onclick={() => run(command)}
            >
              <span class="min-w-0">
                <span class="block truncate font-medium">{command.title}</span>
                {#if command.hint}
                  <span class="mt-0.5 block truncate text-[10px] text-neutral-500">{command.hint}</span>
                {/if}
              </span>
              <span class="flex shrink-0 items-center gap-2">
                {#if command.group}
                  <span class="rounded-full border border-white/10 px-2 py-0.5 text-[10px] text-neutral-500">{command.group}</span>
                {/if}
                {#if command.shortcut}
                  <kbd class="rounded border border-neutral-700 px-1.5 py-0.5 font-mono text-[10px] text-neutral-400">{command.shortcut}</kbd>
                {/if}
              </span>
            </button>
          </li>
        {/each}
      </ul>
      <footer class="flex items-center justify-between border-t border-neutral-800 px-4 py-2 text-[10px] text-neutral-500">
        <span>↑ ↓ to move · Enter to run · Esc to close</span>
        <span>Ctrl/Cmd + K</span>
      </footer>
    </div>
  </div>
{/if}
