<script lang="ts">
  import { focusTrap } from "$lib/a11y";
  import { noticeCounts, sortNotices, type Notice } from "$lib/notifications";
  import { notifications } from "$lib/notifications.svelte";
  import { formatDateTime } from "$lib/format";
  import { i18n } from "$lib/i18n.svelte";

  let {
    open = false,
    onclose,
    onaction,
    onclear
  }: {
    open?: boolean;
    onclose: () => void;
    onaction?: (actionId: string, notice: Notice) => void;
    onclear?: () => void;
  } = $props();

  const ordered = $derived(sortNotices(notifications.items));
  const counts = $derived(noticeCounts(notifications.items));

  const tones: Record<string, string> = {
    info: "border-sky-400/20 bg-sky-950/30 text-sky-100",
    success: "border-emerald-400/20 bg-emerald-950/30 text-emerald-100",
    warning: "border-amber-400/20 bg-amber-950/30 text-amber-100",
    error: "border-rose-500/30 bg-rose-950/40 text-rose-100"
  };
</script>

{#if open}
  <div class="fixed inset-0 z-[70]" role="presentation">
    <button
      type="button"
      class="absolute inset-0 bg-black/40"
      aria-label="Close notifications"
      onclick={onclose}
    ></button>
    <aside
      class="absolute right-3 top-16 flex max-h-[75vh] w-[min(26rem,calc(100vw-1.5rem))] flex-col overflow-hidden rounded-2xl border border-neutral-700 bg-neutral-950 shadow-2xl shadow-black/50"
      use:focusTrap
      aria-label="Notification center"
      data-testid="notification-center"
    >
      <header class="flex items-center justify-between gap-2 border-b border-neutral-800 px-4 py-3">
        <div>
          <p class="text-sm font-medium text-white">Notifications</p>
          <p class="mt-0.5 text-[11px] text-neutral-500">
            {counts.total} total · {counts.errors} errors · {counts.warnings} warnings
          </p>
        </div>
        <div class="flex items-center gap-2">
          <button
            type="button"
            class="rounded-lg border border-white/10 px-2 py-1 text-[11px] text-neutral-400 hover:text-neutral-100 disabled:opacity-40"
            disabled={counts.total === 0}
            onclick={() => {
              notifications.clear();
              onclear?.();
            }}
          >{i18n.t("clear_all")}</button>
          <button
            type="button"
            class="rounded-lg border border-white/10 px-2 py-1 text-[11px] text-neutral-400 hover:text-neutral-100"
            onclick={onclose}
          >{i18n.t("close")}</button>
        </div>
      </header>
      <div class="flex-1 space-y-2 overflow-auto p-3" aria-live="polite">
        {#if ordered.length === 0}
          <p class="rounded-xl border border-dashed border-neutral-800 px-3 py-6 text-center text-xs text-neutral-500">
            {i18n.t("notification_empty")}
          </p>
        {/if}
        {#each ordered as notice (notice.id)}
          <article class={`rounded-xl border px-3 py-2.5 text-xs ${tones[notice.kind] ?? tones.info}`}>
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0">
                <p class="truncate font-medium">{notice.title}</p>
                {#if notice.message}
                  <p class="mt-1 whitespace-pre-wrap break-words text-[11px] opacity-80">{notice.message}</p>
                {/if}
                {#if notice.detail}
                  <details class="mt-1">
                    <summary class="cursor-pointer text-[10px] uppercase tracking-wide opacity-70">Details</summary>
                    <pre class="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded bg-black/30 p-2 font-mono text-[10px] leading-4 opacity-80">{notice.detail}</pre>
                  </details>
                {/if}
                <p class="mt-1 text-[10px] uppercase tracking-wide opacity-60">
                  {notice.kind}{notice.code ? ` · ${notice.code}` : ""} · {formatDateTime(notice.createdAt)}
                </p>
              </div>
              <button
                type="button"
                class="shrink-0 rounded-md border border-white/10 px-1.5 py-0.5 text-[10px] opacity-70 hover:opacity-100"
                aria-label={`Dismiss ${notice.title}`}
                onclick={() => notifications.dismiss(notice.id)}
              >✕</button>
            </div>
            {#if notice.actionLabel && notice.actionId}
              <button
                type="button"
                class="mt-2 rounded-lg border border-white/20 bg-white/5 px-2.5 py-1 text-[11px] font-medium hover:bg-white/10"
                onclick={() => onaction?.(notice.actionId, notice)}
              >{notice.actionLabel}</button>
            {/if}
          </article>
        {/each}
      </div>
    </aside>
  </div>
{/if}
