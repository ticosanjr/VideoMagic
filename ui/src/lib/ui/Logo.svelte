<script lang="ts">
  let {
    size = 40,
    wordmark = false,
    subtitle = ""
  }: {
    size?: number;
    wordmark?: boolean;
    subtitle?: string;
  } = $props();

  const uid = $props.id();
</script>

<span class="inline-flex items-center gap-3">
  <svg
    width={size}
    height={size}
    viewBox="0 0 48 48"
    role="img"
    aria-label="VideoFlow"
    class="shrink-0 drop-shadow-[0_6px_18px_rgba(56,189,248,0.22)]"
  >
    <defs>
      <linearGradient id={`${uid}-bg`} x1="0" y1="0" x2="1" y2="1">
        <stop offset="0%" stop-color="#38bdf8" />
        <stop offset="55%" stop-color="#6366f1" />
        <stop offset="100%" stop-color="#8b5cf6" />
      </linearGradient>
    </defs>
    <rect width="48" height="48" rx="13" fill={`url(#${uid}-bg)`} />
    <rect
      x="1"
      y="1"
      width="46"
      height="46"
      rx="12"
      fill="none"
      stroke="#ffffff"
      stroke-opacity="0.28"
    />
    <path d="M12.5 13.5h5.5v21h-5.5zM30 13.5h5.5v21H30z" fill="#0b1020" fill-opacity="0.22" />
    <path d="M19.5 16.5 31 24l-11.5 7.5z" fill="#ffffff" />
  </svg>
  {#if wordmark}
    <span class="flex min-w-0 flex-col leading-none">
      <span class="text-xl font-semibold tracking-tight text-white">VideoFlow</span>
      {#if subtitle}
        <span class="mt-1 truncate text-xs text-neutral-400">{subtitle}</span>
      {/if}
    </span>
  {/if}
</span>
