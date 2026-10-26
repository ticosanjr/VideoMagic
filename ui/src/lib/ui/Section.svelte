<script lang="ts">
  import type { Snippet } from "svelte";
  import Icon from "$lib/ui/Icon.svelte";
  import type { IconName } from "$lib/ui/icons";

  let {
    title,
    icon = undefined,
    tone = "neutral",
    collapsible = true,
    testid = "",
    actions,
    children
  }: {
    title: string;
    icon?: IconName;
    tone?: "neutral" | "input" | "output" | "config";
    collapsible?: boolean;
    testid?: string;
    actions?: Snippet;
    children?: Snippet;
  } = $props();

  let expanded = $state(true);
  const tones: Record<string, string> = {
    neutral: "border-neutral-800 bg-neutral-900/60",
    input: "border-sky-500/20 bg-sky-950/10",
    output: "border-emerald-500/15 bg-emerald-950/10",
    config: "border-neutral-800 bg-neutral-900/60"
  };
  const titleTones: Record<string, string> = {
    neutral: "text-neutral-500",
    input: "text-sky-300/80",
    output: "text-emerald-300/80",
    config: "text-neutral-500"
  };
</script>

<section class={`rounded-lg border p-2 ${tones[tone]}`} data-testid={testid || undefined}>
  <div class="flex items-center justify-between gap-2">
    <button
      type="button"
      class={`flex items-center gap-1.5 text-[10px] uppercase tracking-wide ${titleTones[tone]}`}
      aria-expanded={collapsible ? expanded : undefined}
      onclick={() => { if (collapsible) expanded = !expanded; }}
    >
      {#if icon}<Icon name={icon} size={12} />{/if}
      <span>{title}</span>
      {#if collapsible}
        <Icon name="chevron" size={11} class={`transition ${expanded ? "rotate-180" : ""}`} />
      {/if}
    </button>
    {#if actions}{@render actions()}{/if}
  </div>
  {#if expanded}
    <div class="mt-2">
      {@render children?.()}
    </div>
  {/if}
</section>
