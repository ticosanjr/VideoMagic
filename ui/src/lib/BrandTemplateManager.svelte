<script lang="ts">
  import { onMount } from "svelte";
  import {
    applyBrandTemplate,
    deleteBrandTemplate,
    errorMessage,
    getBrandTemplates,
    saveBrandTemplate,
    type BrandTemplate
  } from "$lib/api";

  let { config }: { config: any } = $props();
  let templates = $state<BrandTemplate[]>([]);
  let name = $state("");
  let description = $state("");
  let busy = $state(false);
  let error = $state("");

  const captionKeys = [
    "caption_font_family",
    "caption_font_size",
    "caption_font_weight",
    "caption_italic",
    "caption_uppercase",
    "caption_primary_color",
    "caption_highlight_color",
    "caption_outline_color",
    "caption_outline_width",
    "caption_shadow_color",
    "caption_shadow_offset",
    "caption_shadow_opacity",
    "caption_background_color",
    "caption_background_opacity",
    "caption_background_padding",
    "caption_alignment",
    "caption_position_x",
    "caption_position_y",
    "caption_max_width",
    "caption_animation",
    "caption_word_timing",
    "caption_censor_enabled",
    "caption_censor_words",
    "caption_censor_replacement",
    "caption_keyword_highlight_enabled",
    "caption_keyword_color",
    "caption_keyword_words",
    "caption_emoji_enabled",
    "caption_emoji_map",
    "caption_brand_vocabulary"
  ] as const;

  async function refresh() {
    try {
      templates = await getBrandTemplates();
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function save() {
    if (!name.trim() || busy) return;
    busy = true;
    error = "";
    try {
      const caption_style: Record<string, unknown> = {};
      for (const key of captionKeys) caption_style[key.replace(/^caption_/, "")] = config[key];
      await saveBrandTemplate(name.trim(), {
        description,
        caption_style,
        overlay: {
          enabled: Boolean(config.overlay_enabled),
          asset: String(config.overlay_asset || ""),
          position: String(config.overlay_position),
          margin_px: Number(config.overlay_margin_px),
          width_ratio: Number(config.overlay_width_ratio),
          opacity: Number(config.overlay_opacity)
        },
        music: {
          enabled: Boolean(config.music_enabled),
          asset: String(config.music_asset || ""),
          volume: Number(config.music_volume),
          ducking: Boolean(config.music_ducking),
          fade_in_ms: Number(config.music_fade_in_ms),
          fade_out_ms: Number(config.music_fade_out_ms)
        },
        intro_outro: {
          intro_enabled: Boolean(config.intro_enabled),
          intro_asset: String(config.intro_asset || ""),
          intro_duration_sec: Number(config.intro_duration_sec),
          outro_enabled: Boolean(config.outro_enabled),
          outro_asset: String(config.outro_asset || ""),
          outro_duration_sec: Number(config.outro_duration_sec)
        }
      });
      name = "";
      description = "";
      await refresh();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  async function apply(template: BrandTemplate) {
    busy = true;
    error = "";
    try {
      const options = await applyBrandTemplate(template.name);
      for (const [key, value] of Object.entries(options)) {
        if (key in config) config[key] = value;
      }
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  async function remove(template: BrandTemplate) {
    busy = true;
    error = "";
    try {
      await deleteBrandTemplate(template.name);
      await refresh();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  onMount(() => {
    void refresh();
  });
</script>

<div class="rounded-xl border border-neutral-800 bg-neutral-950/60 p-3">
  <div>
    <p class="text-[11px] uppercase tracking-wide text-neutral-500">Brand templates</p>
    <p class="mt-1 text-[10px] text-neutral-500">
      Save caption, overlay, music, and intro/outro settings as a reusable bundle.
    </p>
  </div>
  <div class="mt-2 grid gap-2 sm:grid-cols-2">
    <input
      type="text"
      value={name}
      oninput={(event) => (name = event.currentTarget.value)}
      placeholder="Template name"
      class="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100"
    />
    <input
      type="text"
      value={description}
      oninput={(event) => (description = event.currentTarget.value)}
      placeholder="Description"
      class="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100"
    />
  </div>
  <button
    type="button"
    onclick={save}
    disabled={busy || !name.trim()}
    class="mt-2 rounded-lg border border-sky-500/40 bg-sky-500/10 px-2.5 py-1.5 text-[10px] text-sky-200 disabled:opacity-40"
  >
    Save current brand
  </button>
  {#if error}<p class="mt-2 text-[10px] text-rose-300">{error}</p>{/if}
  {#if templates.length}
    <div class="mt-2 space-y-1.5">
      {#each templates as template}
        <div class="flex items-center gap-2 rounded-lg border border-neutral-800 bg-neutral-900/60 px-2 py-1.5">
          <div class="min-w-0 flex-1">
            <p class="truncate text-[11px] text-neutral-200">{template.name}</p>
            {#if template.description}
              <p class="truncate text-[9px] text-neutral-500">{template.description}</p>
            {/if}
          </div>
          <button type="button" onclick={() => apply(template)} disabled={busy} class="text-[10px] text-sky-300 hover:text-sky-200">
            Apply
          </button>
          <button type="button" onclick={() => remove(template)} disabled={busy} class="text-[10px] text-rose-300 hover:text-rose-200">
            Delete
          </button>
        </div>
      {/each}
    </div>
  {/if}
</div>
