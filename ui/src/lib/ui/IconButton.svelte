<script lang="ts">
  import Icon from "$lib/ui/Icon.svelte";
  import type { IconName } from "$lib/ui/icons";

  let {
    icon,
    label,
    title = "",
    variant = "ghost",
    disabled = false,
    testid = "",
    class: className = "",
    onclick
  }: {
    icon: IconName;
    label: string;
    title?: string;
    variant?: "ghost" | "secondary" | "danger";
    disabled?: boolean;
    testid?: string;
    class?: string;
    onclick?: (event: MouseEvent) => void;
  } = $props();

  const variants: Record<string, string> = {
    ghost: "border-transparent text-neutral-400 hover:bg-white/5 hover:text-neutral-100",
    secondary: "border-neutral-700 bg-neutral-950/40 text-neutral-300 hover:border-sky-500 hover:text-sky-200",
    danger: "border-rose-500/30 bg-rose-500/10 text-rose-200 hover:bg-rose-500/20"
  };
</script>

<button
  type="button"
  {disabled}
  title={title || label}
  aria-label={label}
  data-testid={testid || undefined}
  onclick={onclick}
  class={`inline-flex h-7 w-7 items-center justify-center rounded-lg border transition disabled:cursor-not-allowed disabled:opacity-40 ${variants[variant]} ${className}`}
>
  <Icon name={icon} size={14} />
</button>
