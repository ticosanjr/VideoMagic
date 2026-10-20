<script lang="ts">
  let { status, size = 16 }: { status: string; size?: number } = $props();

  const colors: Record<string, string> = {
    succeeded: "text-emerald-400",
    cached: "text-emerald-400",
    running: "text-sky-400",
    failed: "text-rose-400",
    blocked: "text-orange-400",
    dirty: "text-amber-400",
    pending: "text-neutral-500",
    bypassed: "text-neutral-500",
    cancelled: "text-neutral-500"
  };
</script>

<svg
  width={size}
  height={size}
  viewBox="0 0 24 24"
  fill="none"
  stroke="currentColor"
  stroke-width="2"
  stroke-linecap="round"
  stroke-linejoin="round"
  class={colors[status] ?? "text-neutral-400"}
  aria-hidden="true"
>
  {#if status === "succeeded" || status === "cached"}
    <circle cx="12" cy="12" r="9" />
    <path d="m8 12 2.5 2.5L16 9" />
  {:else if status === "failed"}
    <circle cx="12" cy="12" r="9" />
    <path d="m9 9 6 6M15 9l-6 6" />
  {:else if status === "running"}
    <path d="M21 12a9 9 0 1 1-9-9" />
  {:else if status === "blocked" || status === "dirty"}
    <path d="M12 3 2.5 20h19L12 3Z" />
    <path d="M12 9v4M12 17h.01" />
  {:else if status === "bypassed" || status === "cancelled"}
    <circle cx="12" cy="12" r="9" />
    <path d="M6 6l12 12" />
  {:else}
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  {/if}
</svg>
