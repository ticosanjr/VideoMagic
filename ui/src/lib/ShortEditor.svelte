<script lang="ts">
  import {
    editShort,
    errorMessage,
    generateShortMetadata,
    generateShortThumbnail,
    generateShortVoiceover,
    type ShortClip,
    type ShortMetadata,
    type ShortThumbnail
  } from "$lib/api";

  let {
    jobId,
    index,
    short,
    open,
    allowExternal = false,
    allowedHosts = "",
    onClose,
    onSaved
  }: {
    jobId: string;
    index: number;
    short: ShortClip;
    open: boolean;
    allowExternal?: boolean;
    allowedHosts?: string;
    onClose: () => void;
    onSaved: (value: ShortClip) => void;
  } = $props();

  let tab = $state<"clip" | "captions" | "metadata">("clip");
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
  let platform = $state("youtube");
  let tone = $state("engaging");
  let metadata = $state<ShortMetadata | null>(null);
  let metadataBusy = $state(false);
  let metadataError = $state("");
  let thumbnail = $state<ShortThumbnail | null>(null);
  let thumbnailTime = $state(0.5);
  let thumbnailBusy = $state(false);
  let thumbnailError = $state("");
  let voiceoverText = $state("");
  let voiceoverBaseUrl = $state("");
  let voiceoverModel = $state("tts-1");
  let voiceoverVoice = $state("alloy");
  let voiceoverBusy = $state(false);
  let voiceoverError = $state("");

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
    platform = "youtube";
    tone = "engaging";
    metadata = short.metadata?.youtube ?? null;
    metadataError = "";
    thumbnail = short.thumbnails?.at(-1) ?? null;
    thumbnailTime = 0.5;
    thumbnailError = "";
    voiceoverText = short.voiceover?.text ?? "";
    voiceoverBaseUrl = "";
    voiceoverModel = short.voiceover?.model ?? "tts-1";
    voiceoverVoice = short.voiceover?.voice ?? "alloy";
    voiceoverError = "";
  });

  function setPlatform(value: string) {
    platform = value;
    metadata = short.metadata?.[value] ?? null;
    metadataError = "";
  }

  async function generateMetadata() {
    if (metadataBusy) return;
    metadataBusy = true;
    metadataError = "";
    try {
      const response = await generateShortMetadata(jobId, index, {
        platform,
        tone
      });
      metadata = response.metadata;
    } catch (reason) {
      metadataError = errorMessage(reason);
    } finally {
      metadataBusy = false;
    }
  }

  async function makeVoiceover() {
    if (voiceoverBusy) return;
    voiceoverBusy = true;
    voiceoverError = "";
    try {
      const hosts = allowedHosts
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      const response = await generateShortVoiceover(jobId, index, {
        text: voiceoverText,
        base_url: voiceoverBaseUrl.trim() || undefined,
        model: voiceoverModel,
        voice: voiceoverVoice,
        allow_external_services: allowExternal,
        allowed_external_hosts: hosts
      });
      onSaved(response.short);
    } catch (reason) {
      voiceoverError = errorMessage(reason);
    } finally {
      voiceoverBusy = false;
    }
  }

  async function makeThumbnail() {
    if (thumbnailBusy) return;
    thumbnailBusy = true;
    thumbnailError = "";
    try {
      const response = await generateShortThumbnail(jobId, index, {
        time_sec: Number(thumbnailTime),
        title
      });
      thumbnail = response.thumbnail;
    } catch (reason) {
      thumbnailError = errorMessage(reason);
    } finally {
      thumbnailBusy = false;
    }
  }

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
        <button
          type="button"
          role="tab"
          aria-selected={tab === "metadata"}
          onclick={() => (tab = "metadata")}
          class={`rounded-t-lg px-3 py-2 text-xs font-medium ${tab === "metadata" ? "bg-neutral-800 text-sky-200" : "text-neutral-400 hover:text-neutral-200"}`}
        >
          Metadata
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
        {:else if tab === "captions"}
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
        {:else}
          <div class="grid gap-3 sm:grid-cols-2">
            <label class="block text-xs text-neutral-300">
              <span class="text-[10px] uppercase tracking-wide text-neutral-500">Platform</span>
              <select
                value={platform}
                onchange={(event) => setPlatform(event.currentTarget.value)}
                class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100"
              >
                <option value="youtube">YouTube</option>
                <option value="tiktok">TikTok</option>
                <option value="instagram">Instagram</option>
                <option value="linkedin">LinkedIn</option>
              </select>
            </label>
            <label class="block text-xs text-neutral-300">
              <span class="text-[10px] uppercase tracking-wide text-neutral-500">Tone</span>
              <select
                value={tone}
                onchange={(event) => (tone = event.currentTarget.value)}
                class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100"
              >
                <option value="engaging">Engaging</option>
                <option value="professional">Professional</option>
                <option value="educational">Educational</option>
                <option value="bold">Bold</option>
              </select>
            </label>
          </div>

          <button
            type="button"
            onclick={generateMetadata}
            disabled={metadataBusy}
            class="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-xs font-medium text-sky-200 disabled:opacity-40"
          >
            {metadataBusy ? "Generating…" : "Generate metadata"}
          </button>

          {#if metadataError}
            <p class="rounded-lg border border-rose-500/20 bg-rose-950/30 p-2 text-[11px] text-rose-300">{metadataError}</p>
          {/if}

          {#if metadata}
            <div class="space-y-3 rounded-xl border border-neutral-800 bg-neutral-950/60 p-3">
              <div>
                <div class="flex items-center justify-between gap-2">
                  <span class="text-[10px] uppercase tracking-wide text-neutral-500">Title</span>
                  <button type="button" onclick={() => (title = metadata?.title ?? title)} class="text-[10px] text-sky-300 hover:text-sky-200">
                    Use as title
                  </button>
                </div>
                <p class="mt-1 text-xs text-neutral-200">{metadata.title}</p>
              </div>
              <div>
                <span class="text-[10px] uppercase tracking-wide text-neutral-500">Description</span>
                <p class="mt-1 whitespace-pre-wrap text-[11px] leading-5 text-neutral-400">{metadata.description}</p>
              </div>
              <div>
                <span class="text-[10px] uppercase tracking-wide text-neutral-500">Hashtags</span>
                <p class="mt-1 text-[11px] text-sky-300">{metadata.hashtags.join(" ")}</p>
              </div>
            </div>
          {/if}

          <div class="rounded-xl border border-neutral-800 bg-neutral-950/60 p-3">
            <div class="flex flex-wrap items-end gap-2">
              <label class="block flex-1 text-xs text-neutral-300">
                <span class="text-[10px] uppercase tracking-wide text-neutral-500">Frame time (s)</span>
                <input
                  type="number"
                  min="0"
                  max={short.duration_sec}
                  step="0.05"
                  value={thumbnailTime}
                  oninput={(event) => (thumbnailTime = Number(event.currentTarget.value))}
                  class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100"
                />
              </label>
              <button
                type="button"
                onclick={makeThumbnail}
                disabled={thumbnailBusy}
                class="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs font-medium text-amber-200 disabled:opacity-40"
              >
                {thumbnailBusy ? "Rendering…" : "Generate thumbnail"}
              </button>
            </div>
            {#if thumbnailError}
              <p class="mt-2 text-[10px] text-rose-300">{thumbnailError}</p>
            {/if}
            {#if thumbnail}
              <img
                src={`/api/v1/jobs/${jobId}/shorts/${index}/thumbnail?v=${encodeURIComponent(thumbnail.path)}`}
                alt="Short thumbnail"
                class="mt-3 w-full rounded-lg border border-neutral-800"
              />
              <a
                class="mt-2 block truncate text-[10px] text-sky-300 hover:text-sky-200"
                href={`/api/v1/jobs/${jobId}/shorts/${index}/thumbnail`}
                download
              >
                Download thumbnail
              </a>
            {/if}
          </div>

          <div class="rounded-xl border border-neutral-800 bg-neutral-950/60 p-3">
            <p class="text-[10px] uppercase tracking-wide text-neutral-500">Voice-over</p>
            <textarea
              rows="3"
              value={voiceoverText}
              oninput={(event) => (voiceoverText = event.currentTarget.value)}
              placeholder="Narration text"
              class="mt-2 w-full resize-y rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-sm text-neutral-100"
            ></textarea>
            <div class="mt-2 grid gap-2 sm:grid-cols-3">
              <input
                type="text"
                value={voiceoverBaseUrl}
                oninput={(event) => (voiceoverBaseUrl = event.currentTarget.value)}
                placeholder="TTS base URL"
                class="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100"
              />
              <input
                type="text"
                value={voiceoverModel}
                oninput={(event) => (voiceoverModel = event.currentTarget.value)}
                placeholder="model"
                class="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100"
              />
              <input
                type="text"
                value={voiceoverVoice}
                oninput={(event) => (voiceoverVoice = event.currentTarget.value)}
                placeholder="voice"
                class="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100"
              />
            </div>
            <button
              type="button"
              onclick={makeVoiceover}
              disabled={voiceoverBusy || !allowExternal}
              class="mt-2 rounded-lg border border-violet-500/40 bg-violet-500/10 px-3 py-1.5 text-xs font-medium text-violet-200 disabled:opacity-40"
            >
              {voiceoverBusy ? "Generating…" : "Generate voice-over"}
            </button>
            {#if !allowExternal}
              <p class="mt-1 text-[10px] text-amber-300">Enable external services in Providers first.</p>
            {/if}
            {#if voiceoverError}
              <p class="mt-2 text-[10px] text-rose-300">{voiceoverError}</p>
            {/if}
            {#if short.voiceover}
              <p class="mt-2 text-[10px] text-emerald-300">
                Voice-over mixed · {short.voiceover.model} · {short.voiceover.voice}
              </p>
            {/if}
          </div>
        {/if}

        {#if error}
          <p class="rounded-lg border border-rose-500/20 bg-rose-950/30 p-2 text-[11px] text-rose-300">{error}</p>
        {/if}
      </div>

      <div class="flex flex-wrap items-center justify-between gap-2 border-t border-neutral-800 p-4">
        {#if tab === "metadata"}
          <span class="text-[10px] text-neutral-500">Metadata is saved when generated.</span>
          <button type="button" onclick={onClose} class="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300">
            Close
          </button>
        {:else}
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
        {/if}
      </div>
    </div>
  </div>
{/if}
