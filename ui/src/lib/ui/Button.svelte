<script lang="ts">
  import type { Snippet } from "svelte";
  import Icon from "$lib/ui/Icon.svelte";
  import type { IconName } from "$lib/ui/icons";

  let {
    variant = "secondary",
    size = "sm",
    icon = undefined,
    disabled = false,
    type = "button",
    title = "",
    testid = "",
    class: className = "",
    onclick,
    children
  }: {
    variant?: "primary" | "secondary" | "ghost" | "danger" | "success";
    size?: "xs" | "sm" | "md";
    icon?: IconName;
    disabled?: boolean;
    type?: "button" | "submit";
    title?: string;
    testid?: string;
    class?: string;
    onclick?: (event: MouseEvent) => void;
    children?: Snippet;
  } = $props();

  const variants: Record<string, string> = {
    primary: "border-sky-400/60 bg-sky-500 text-neutral-950 hover:bg-sky-400",
    secondary: "border-neutral-700 bg-neutral-950/40 text-neutral-300 hover:border-sky-500 hover:text-sky-200",
    ghost: "border-transparent text-neutral-400 hover:bg-white/5 hover:text-neutral-100",
    danger: "border-rose-500/30 bg-rose-500/10 text-rose-200 hover:bg-rose-500/20",
    success: "border-emerald-500/40 bg-emerald-500/10 text-emerald-200 hover:bg-emerald-500/20"
  };
  const sizes: Record<string, string> = {
    xs: "min-h-7 px-2 py-1 text-[length:var(--vf-text-2xs)] gap-1",
    sm: "min-h-8 px-2.5 py-1.5 text-[length:var(--vf-text-xs)] gap-1.5",
    md: "min-h-9 px-3 py-1.5 text-[length:var(--vf-text-sm)] gap-1.5"
  };
</script>

<button
  {type}
  {disabled}
  {title}
  data-testid={testid || undefined}
  onclick={onclick}
  class={`inline-flex items-center justify-center rounded-lg border font-medium transition-colors duration-150 active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40 ${variants[variant]} ${sizes[size]} ${className}`}
>
  {#if icon}<Icon name={icon} size={size === "xs" ? 11 : size === "sm" ? 12 : 14} />{/if}
  {#if children}{@render children()}{/if}
</button>
