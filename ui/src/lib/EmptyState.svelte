<script lang="ts">
  import Icon from "$lib/ui/Icon.svelte";
  import type { IconName } from "$lib/ui/icons";

  let {
    title,
    description = "",
    action = "",
    onaction,
    testId = "",
    icon = "sparkles",
    hint = ""
  }: {
    title: string;
    description?: string;
    action?: string;
    onaction?: () => void;
    testId?: string;
    icon?: IconName;
    hint?: string;
  } = $props();
</script>

<div
  class="relative overflow-hidden rounded-2xl border border-dashed border-neutral-800 bg-neutral-950/40 px-4 py-10 text-center"
  data-testid={testId || undefined}
>
  <div class="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-sky-400/20 to-transparent"></div>
  <div class="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-2xl border border-sky-400/15 bg-gradient-to-br from-sky-400/15 to-indigo-500/10 text-sky-300/80 shadow-inner shadow-sky-500/5">
    <Icon name={icon} size={20} />
  </div>
  <p class="text-sm font-medium text-neutral-200">{title}</p>
  {#if description}
    <p class="mx-auto mt-1 max-w-md text-xs leading-relaxed text-neutral-500">{description}</p>
  {/if}
  {#if action && onaction}
    <button
      type="button"
      class="mt-4 rounded-xl bg-sky-500/15 px-3 py-1.5 text-xs font-medium text-sky-200 ring-1 ring-inset ring-sky-400/25 transition hover:bg-sky-500/20"
      onclick={onaction}
    >{action}</button>
  {/if}
  {#if hint}
    <p class="mt-3 font-mono text-[10px] uppercase tracking-wide text-neutral-600">{hint}</p>
  {/if}
</div>
