<script lang="ts">
  let {
    message = "",
    title = "Something went wrong",
    detail = "",
    onDismiss,
    testId = "error-banner"
  }: {
    message?: string;
    title?: string;
    detail?: string;
    onDismiss?: () => void;
    testId?: string;
  } = $props();

  const visible = $derived(Boolean(message || detail));

  async function copyDiagnostics() {
    const text = [title, message, detail].filter(Boolean).join("\n");
    try {
      await navigator.clipboard.writeText(text);
    } catch {
      // Clipboard access is optional; the banner stays readable either way.
    }
  }
</script>

{#if visible}
  <div
    role="alert"
    aria-live="assertive"
    data-testid={testId}
    class="sticky top-2 z-40 flex items-start gap-3 rounded-2xl border border-rose-500/40 bg-rose-950/95 px-4 py-3 text-xs text-rose-100 shadow-2xl shadow-black/40 backdrop-blur"
  >
    <span class="mt-1 h-2 w-2 shrink-0 rounded-full bg-rose-400" aria-hidden="true"></span>
    <div class="min-w-0 flex-1">
      <p class="font-semibold text-rose-50">{title}</p>
      {#if message}<p class="mt-0.5 break-words leading-5">{message}</p>{/if}
      {#if detail}<p class="mt-0.5 break-words font-mono text-[10px] leading-4 text-rose-200/70">{detail}</p>{/if}
    </div>
    <div class="flex shrink-0 items-center gap-1">
      <button
        type="button"
        onclick={() => void copyDiagnostics()}
        class="rounded-md border border-rose-400/30 px-2 py-1 text-[10px] text-rose-200 hover:border-rose-300/60 hover:text-white"
      >
        Copy
      </button>
      {#if onDismiss}
        <button
          type="button"
          onclick={onDismiss}
          class="rounded-md px-2 py-1 text-sm leading-none text-rose-300 hover:text-white"
          aria-label="Dismiss error"
        >
          ×
        </button>
      {/if}
    </div>
  </div>
{/if}
