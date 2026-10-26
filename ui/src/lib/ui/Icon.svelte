<script lang="ts">
  import { ICONS, type IconName } from "$lib/ui/icons";

  let {
    name,
    size = 16,
    strokeWidth = 1.8,
    class: className = "",
    label = ""
  }: {
    name: IconName;
    size?: number;
    strokeWidth?: number;
    class?: string;
    label?: string;
  } = $props();
</script>

<svg
  xmlns="http://www.w3.org/2000/svg"
  viewBox="0 0 24 24"
  width={size}
  height={size}
  fill="none"
  stroke="currentColor"
  stroke-width={strokeWidth}
  stroke-linecap="round"
  stroke-linejoin="round"
  class={`inline-block shrink-0 ${className}`}
  role={label ? "img" : undefined}
  aria-label={label || undefined}
  aria-hidden={label ? undefined : "true"}
>
  {@html ICONS[name] ?? ICONS.circle}
</svg>
