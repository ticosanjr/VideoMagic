<script lang="ts">
  let { status }: { status: string } = $props();

  const TONES: Record<string, string> = {
    failed: "border-rose-500/30 bg-rose-950/40 text-rose-200",
    cancelled: "border-neutral-700 bg-white/[0.03] text-neutral-400",
    waiting_approval: "border-amber-400/30 bg-amber-950/30 text-amber-200",
    waiting_input: "border-amber-400/30 bg-amber-950/30 text-amber-200",
    answered: "border-neutral-700 bg-white/[0.03] text-neutral-400",
    paused: "border-amber-400/25 bg-amber-950/20 text-amber-200",
    running: "border-sky-400/25 bg-sky-950/30 text-sky-200",
    queued: "border-neutral-700 bg-white/[0.03] text-neutral-300",
    succeeded: "border-emerald-400/25 bg-emerald-950/30 text-emerald-200"
  };

  const DOTS: Record<string, string> = {
    failed: "bg-rose-400",
    cancelled: "bg-neutral-500",
    waiting_approval: "bg-amber-400",
    waiting_input: "bg-amber-400",
    answered: "bg-neutral-500",
    paused: "bg-amber-400",
    running: "animate-pulse bg-sky-400",
    queued: "bg-neutral-400",
    succeeded: "bg-emerald-400"
  };

  const ACTIONS: Record<string, string> = {
    failed: "Fix the error, then retry",
    cancelled: "Retry to run it again",
    waiting_approval: "Review and approve",
    waiting_input: "Answer the questions or upload files",
    answered: "Resumed as a new job",
    paused: "Resume when ready",
    running: "Wait or cancel",
    queued: "Waiting for a free slot",
    succeeded: "Open the artifacts"
  };
</script>

<span
  class={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[length:var(--vf-text-2xs)] font-semibold uppercase tracking-wide ${TONES[status] ?? TONES.queued}`}
  title={ACTIONS[status] ?? status}
  aria-label={`${status.replaceAll("_", " ")}. ${ACTIONS[status] ?? ""}`}
>
  <span class={`h-1.5 w-1.5 rounded-full ${DOTS[status] ?? DOTS.queued}`} aria-hidden="true"></span>
  {status.replaceAll("_", " ")}
</span>
