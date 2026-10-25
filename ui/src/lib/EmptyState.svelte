<script lang="ts">
  let {
    title,
    description = "",
    action = "",
    onaction,
    testId = ""
  }: {
    title: string;
    description?: string;
    action?: string;
    onaction?: () => void;
    testId?: string;
  } = $props();
</script>

<div
  class="rounded-2xl border border-dashed border-neutral-800 bg-neutral-950/40 px-4 py-10 text-center"
  data-testid={testId || undefined}
>
  <p class="text-sm font-medium text-neutral-200">{title}</p>
  {#if description}
    <p class="mx-auto mt-1 max-w-md text-xs text-neutral-500">{description}</p>
  {/if}
  {#if action && onaction}
    <button
      type="button"
      class="mt-4 rounded-xl bg-sky-500/15 px-3 py-1.5 text-xs font-medium text-sky-200 ring-1 ring-inset ring-sky-400/25 hover:bg-sky-500/20"
      onclick={onaction}
    >{action}</button>
  {/if}
</div>
