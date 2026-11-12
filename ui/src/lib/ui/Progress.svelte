<script lang="ts">
  let {
    value = 0,
    label = "",
    tone = "accent",
    testid = ""
  }: {
    value?: number;
    label?: string;
    tone?: "accent" | "success" | "warning" | "danger";
    testid?: string;
  } = $props();

  const safe = $derived(Math.max(0, Math.min(100, Math.round(Number(value) || 0))));
  const tones: Record<string, string> = {
    accent: "bg-sky-400",
    success: "bg-emerald-400",
    warning: "bg-amber-400",
    danger: "bg-rose-400"
  };
</script>

<div
  class="h-1.5 w-full overflow-hidden rounded-full bg-white/[0.08]"
  role="progressbar"
  aria-valuemin="0"
  aria-valuemax="100"
  aria-valuenow={safe}
  aria-label={label || undefined}
  data-testid={testid || undefined}
>
  <div class={`h-full rounded-full transition-[width] duration-300 ${tones[tone] ?? tones.accent}`} style={`width:${safe}%`}></div>
</div>
