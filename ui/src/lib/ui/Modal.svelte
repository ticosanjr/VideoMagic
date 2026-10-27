<script lang="ts">
  import type { Snippet } from "svelte";
  import { focusTrap } from "$lib/a11y";
  import Icon from "$lib/ui/Icon.svelte";

  let {
    open = false,
    title,
    description = "",
    label = "",
    testid = "",
    width = "w-[min(720px,96vw)]",
    height = "",
    bodyClass = "p-4",
    onclose,
    footer,
    children
  }: {
    open?: boolean;
    title: string;
    description?: string;
    label?: string;
    testid?: string;
    width?: string;
    height?: string;
    bodyClass?: string;
    onclose: () => void;
    footer?: Snippet;
    children?: Snippet;
  } = $props();

  let host = $state<HTMLDivElement | null>(null);

  $effect(() => {
    if (!open || !host) return;
    document.body.appendChild(host);
    return () => host?.remove();
  });
</script>

{#if open}
  <div bind:this={host}>
    <div class="fixed inset-0 z-[100] flex items-center justify-center bg-black/75 p-2 sm:p-4" role="presentation">
      <button
        type="button"
        class="absolute inset-0 cursor-default"
        aria-label={`Dismiss ${title}`}
        onclick={onclose}
      ></button>
      <div
        class={`relative flex max-h-[92vh] flex-col overflow-hidden rounded-2xl border border-neutral-700 bg-neutral-950 shadow-2xl ${width} ${height}`}
        role="dialog"
        aria-modal="true"
        aria-label={label || title}
        data-testid={testid || undefined}
        use:focusTrap
      >
        <header class="flex items-start justify-between gap-3 border-b border-neutral-800 px-4 py-3">
          <div class="min-w-0">
            <h3 class="truncate text-sm font-semibold text-white">{title}</h3>
            {#if description}<p class="mt-0.5 text-[10px] leading-4 text-neutral-500">{description}</p>{/if}
          </div>
          <button
            type="button"
            onclick={onclose}
            class="rounded p-1 text-neutral-500 hover:text-neutral-200"
            aria-label={`Close ${label || title}`}
            title="Close"
          ><Icon name="close" size={14} /></button>
        </header>
        <div class={`min-h-0 flex-1 overflow-auto ${bodyClass}`}>
          {@render children?.()}
        </div>
        {#if footer}
          <footer class="border-t border-neutral-800 px-4 py-3">{@render footer()}</footer>
        {/if}
      </div>
    </div>
  </div>
{/if}
