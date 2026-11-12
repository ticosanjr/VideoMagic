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
  class="rounded-xl border border-dashed border-neutral-800 bg-neutral-950/40 px-4 py-10 text-center"
  data-testid={testId || undefined}
>
  <div class="mx-auto mb-3 flex h-11 w-11 items-center justify-center rounded-xl border border-sky-400/20 bg-sky-400/10 text-sky-300/90">
    <Icon name={icon} size={20} />
  </div>
  <p class="text-[length:var(--vf-text-base)] font-medium text-neutral-100">{title}</p>
  {#if description}
    <p class="mx-auto mt-1 max-w-md text-[length:var(--vf-text-sm)] leading-relaxed text-neutral-400">{description}</p>
  {/if}
  {#if action && onaction}
    <button
      type="button"
      class="mt-4 min-h-9 rounded-lg bg-sky-500 px-3.5 py-1.5 text-[length:var(--vf-text-sm)] font-medium text-neutral-950 transition-colors hover:bg-sky-400"
      onclick={onaction}
    >{action}</button>
  {/if}
  {#if hint}
    <p class="mt-3 font-mono text-[length:var(--vf-text-2xs)] uppercase tracking-wide text-neutral-500">{hint}</p>
  {/if}
</div>
