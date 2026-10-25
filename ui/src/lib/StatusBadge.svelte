<script lang="ts">
  let { status }: { status: string } = $props();

  const TONES: Record<string, string> = {
    failed: "border-rose-500/30 bg-rose-950/40 text-rose-200",
    cancelled: "border-neutral-700 bg-white/[0.03] text-neutral-400",
    waiting_approval: "border-amber-400/30 bg-amber-950/30 text-amber-200",
    paused: "border-amber-400/25 bg-amber-950/20 text-amber-200",
    running: "border-sky-400/25 bg-sky-950/30 text-sky-200",
    queued: "border-neutral-700 bg-white/[0.03] text-neutral-300",
    succeeded: "border-emerald-400/25 bg-emerald-950/30 text-emerald-200"
  };

  const ACTIONS: Record<string, string> = {
    failed: "Fix the error, then retry",
    cancelled: "Retry to run it again",
    waiting_approval: "Review and approve",
    paused: "Resume when ready",
    running: "Wait or cancel",
    queued: "Waiting for a free slot",
    succeeded: "Open the artifacts"
  };
</script>

<span
  class={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] uppercase tracking-wide ${TONES[status] ?? TONES.queued}`}
  title={ACTIONS[status] ?? status}
  aria-label={`${status.replaceAll("_", " ")}. ${ACTIONS[status] ?? ""}`}
>
  {status.replaceAll("_", " ")}
</span>
