<script lang="ts">
  import { editShort, errorMessage, type ShortClip } from "$lib/api";

  let {
    jobId,
    index,
    short,
    open,
    onClose,
    onSaved
  }: {
    jobId: string;
    index: number;
    short: ShortClip;
    open: boolean;
    onClose: () => void;
    onSaved: (value: ShortClip) => void;
  } = $props();

  let tab = $state<"clip" | "captions">("clip");
  let title = $state("");
  let startSec = $state(0);
  let endSec = $state(0);
  let aspect = $state<"9:16" | "1:1" | "16:9">("9:16");
  let burnSubtitles = $state(true);
  let fontSize = $state(72);
  let primaryColor = $state("#FFFFFF");
  let highlightColor = $state("#FFD400");
  let backgroundOpacity = $state(0);
  let busy = $state(false);
  let error = $state("");

  $effect(() => {
    if (!open) return;
    tab = "clip";
    error = "";
    title = short.title;
    startSec = 0;
    endSec = Number(short.duration_sec || 0);
    aspect = (short.aspect_ratio as "9:16" | "1:1" | "16:9") || "9:16";
    burnSubtitles = Boolean(short.subtitles);
    const style = short.caption_style ?? {};
    fontSize = Number(style.font_size ?? 72);
    primaryColor = String(style.primary_color ?? "#FFFFFF");
    highlightColor = String(style.highlight_color ?? "#FFD400");
    backgroundOpacity = Number(style.background_opacity ?? 0);
  });

  async function save() {
    if (busy) return;
    error = "";
    if (!title.trim()) {
      error = "Title is required.";
      return;
    }
    if (Number(endSec) <= Number(startSec)) {
      error = "End must be greater than start.";
      return;
    }
    busy = true;
    try {
      const response = await editShort(jobId, index, {
        title: title.trim(),
        start_sec: Number(startSec),
        end_sec: Number(endSec),
        aspect_ratio: aspect,
        burn_subtitles: burnSubtitles,
        caption_style: {
          font_size: Number(fontSize),
          primary_color: primaryColor,
          highlight_color: highlightColor,
          background_opacity: Number(backgroundOpacity)
        }
      });
      onSaved(response.short);
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }
</script>

{#if open}
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" role="dialog" aria-modal="true" aria-label="Edit Short">
    <div class="w-full max-w-lg overflow-hidden rounded-2xl border border-neutral-700 bg-neutral-900 shadow-2xl">
      <div class="flex items-start justify-between gap-3 border-b border-neutral-800 p-4">
        <div>
          <h2 class="text-sm font-semibold text-white">Edit Short</h2>
          <p class="mt-1 text-[11px] text-neutral-500">
            Re-renders from the source. The original MP4 stays available.
          </p>
        </div>
        <button type="button" onclick={onClose} class="rounded-lg border border-neutral-700 px-2 py-1 text-xs text-neutral-400 hover:text-white">
          Close
        </button>
      </div>

      <div class="flex gap-1 border-b border-neutral-800 px-3 pt-3" role="tablist" aria-label="Short edit sections">
        <button
          type="button"
          role="tab"
          aria-selected={tab === "clip"}
          onclick={() => (tab = "clip")}
          class={`rounded-t-lg px-3 py-2 text-xs font-medium ${tab === "clip" ? "bg-neutral-800 text-sky-200" : "text-neutral-400 hover:text-neutral-200"}`}
        >
          Clip
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === "captions"}
          onclick={() => (tab = "captions")}
          class={`rounded-t-lg px-3 py-2 text-xs font-medium ${tab === "captions" ? "bg-neutral-800 text-sky-200" : "text-neutral-400 hover:text-neutral-200"}`}
        >
          Captions
        </button>
      </div>

      <div class="space-y-4 p-4">
        {#if tab === "clip"}
          <label class="block text-xs text-neutral-300">
            <span class="text-[10px] uppercase tracking-wide text-neutral-500">Title</span>
            <input
              type="text"
              value={title}
              oninput={(event) => (title = event.currentTarget.value)}
              class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100"
            />
          </label>

          <div class="grid gap-3 sm:grid-cols-2">
            <label class="block text-xs text-neutral-300">
              <span class="text-[10px] uppercase tracking-wide text-neutral-500">Start (s)</span>
              <input
                type="number"
                min="0"
                max={short.duration_sec}
                step="0.05"
                value={startSec}
                oninput={(event) => (startSec = Number(event.currentTarget.value))}
                class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100"
              />
            </label>
            <label class="block text-xs text-neutral-300">
              <span class="text-[10px] uppercase tracking-wide text-neutral-500">End (s)</span>
              <input
                type="number"
                min="0"
                max={short.duration_sec}
                step="0.05"
                value={endSec}
                oninput={(event) => (endSec = Number(event.currentTarget.value))}
                class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100"
              />
            </label>
          </div>

          <label class="block text-xs text-neutral-300">
            <span class="text-[10px] uppercase tracking-wide text-neutral-500">Aspect ratio</span>
            <select
              value={aspect}
              onchange={(event) => (aspect = event.currentTarget.value as "9:16" | "1:1" | "16:9")}
              class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100"
            >
              <option value="9:16">9:16 vertical</option>
              <option value="1:1">1:1 square</option>
              <option value="16:9">16:9 landscape</option>
            </select>
          </label>

          <label class="flex items-center gap-2 text-xs text-neutral-300">
            <input
              type="checkbox"
              checked={burnSubtitles}
              onchange={(event) => (burnSubtitles = event.currentTarget.checked)}
              class="h-4 w-4 rounded border-neutral-700 bg-neutral-800"
            />
            Burn captions on the edited render
          </label>
        {:else}
          <div class="grid gap-3 sm:grid-cols-2">
            <label class="block text-xs text-neutral-300">
              <span class="text-[10px] uppercase tracking-wide text-neutral-500">Font size</span>
              <input
                type="number"
                min="8"
                max="300"
                value={fontSize}
                oninput={(event) => (fontSize = Number(event.currentTarget.value))}
                class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100"
              />
            </label>
            <label class="block text-xs text-neutral-300">
              <span class="text-[10px] uppercase tracking-wide text-neutral-500">Box opacity</span>
              <input
                type="number"
                min="0"
                max="1"
                step="0.05"
                value={backgroundOpacity}
                oninput={(event) => (backgroundOpacity = Number(event.currentTarget.value))}
                class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100"
              />
            </label>
          </div>

          <div class="grid gap-3 sm:grid-cols-2">
            <label class="block text-xs text-neutral-300">
              <span class="text-[10px] uppercase tracking-wide text-neutral-500">Text color</span>
              <input
                type="color"
                value={primaryColor}
                oninput={(event) => (primaryColor = event.currentTarget.value)}
                class="mt-1 h-10 w-full rounded-lg border border-neutral-700 bg-neutral-950 p-1"
              />
            </label>
            <label class="block text-xs text-neutral-300">
              <span class="text-[10px] uppercase tracking-wide text-neutral-500">Highlight color</span>
              <input
                type="color"
                value={highlightColor}
                oninput={(event) => (highlightColor = event.currentTarget.value)}
                class="mt-1 h-10 w-full rounded-lg border border-neutral-700 bg-neutral-950 p-1"
              />
            </label>
          </div>
          <p class="text-[10px] leading-4 text-neutral-500">
            Other caption fields inherit from the project style.
          </p>
        {/if}

        {#if error}
          <p class="rounded-lg border border-rose-500/20 bg-rose-950/30 p-2 text-[11px] text-rose-300">{error}</p>
        {/if}
      </div>

      <div class="flex flex-wrap items-center justify-between gap-2 border-t border-neutral-800 p-4">
        <span class="text-[10px] text-neutral-500">{short.duration_sec.toFixed(2)} s original</span>
        <div class="flex gap-2">
          <button type="button" onclick={onClose} class="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300">
            Cancel
          </button>
          <button
            type="button"
            onclick={save}
            disabled={busy}
            class="rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40"
          >
            {busy ? "Rendering…" : "Save and re-render"}
          </button>
        </div>
      </div>
    </div>
  </div>
{/if}
