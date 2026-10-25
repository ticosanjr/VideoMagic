<script lang="ts">
  let { text, tone = "muted" }: { text: string; tone?: "muted" | "warning" } = $props();
</script>

<p class={`mt-1 text-[10px] leading-relaxed ${tone === "warning" ? "text-amber-300/80" : "text-neutral-500"}`}>
  {text}
</p>
