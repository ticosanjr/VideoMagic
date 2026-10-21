<script lang="ts">
  import type { JobConfig } from "$lib/modules";

  let { config }: { config: JobConfig } = $props();

  const words = ["This", "is", "how", "your", "Shorts", "caption", "will", "look"];
  const activeIndex = 4;
  const scale = 0.25;

  const alignment = $derived(Number(config.caption_alignment) || 2);
  const horizontal = $derived(
    [1, 4, 7].includes(alignment) ? "0%" : [2, 5, 8].includes(alignment) ? "-50%" : "-100%"
  );
  const vertical = $derived(
    alignment <= 3 ? "-100%" : alignment <= 6 ? "-50%" : "0%"
  );
  const textAlign = $derived(
    [1, 4, 7].includes(alignment) ? "left" : [2, 5, 8].includes(alignment) ? "center" : "right"
  );
  const highlight = $derived(String(config.caption_highlight_color || "#FFD400"));
  const fontFamily = $derived(String(config.caption_font_family || "Arial"));
  const fontSize = $derived(Number(config.caption_font_size || 72) * scale);
  const outlineWidth = $derived(Number(config.caption_outline_width || 0) * scale);
  const shadowOffset = $derived(Number(config.caption_shadow_offset || 0) * scale);
  const boxPadding = $derived(Number(config.caption_background_padding || 0) * scale);
  const maxWidth = $derived(Number(config.caption_max_width || 0.9) * 100);
  const positionX = $derived(Number(config.caption_position_x || 0.5) * 100);
  const positionY = $derived(Number(config.caption_position_y || 0.78) * 100);

  const boxStyle = $derived(
    [
      `left: ${positionX}%`,
      `top: ${positionY}%`,
      `transform: translate(${horizontal}, ${vertical})`,
      `text-align: ${textAlign}`,
      `max-width: ${maxWidth}%`,
      `background-color: ${hexToRgba(
        String(config.caption_background_color || "#000000"),
        Number(config.caption_background_opacity || 0)
      )}`,
      `padding: ${boxPadding}px`,
      `border-radius: ${Math.max(2, boxPadding / 2)}px`
    ].join("; ")
  );

  const textStyle = $derived(
    [
      `font-family: ${fontFamily}`,
      `font-size: ${fontSize}px`,
      `font-weight: ${config.caption_font_weight || "bold"}`,
      `font-style: ${config.caption_italic ? "italic" : "normal"}`,
      `color: ${config.caption_primary_color || "#FFFFFF"}`,
      `-webkit-text-stroke: ${outlineWidth}px ${config.caption_outline_color || "#000000"}`,
      "paint-order: stroke fill",
      `text-shadow: ${shadowOffset}px ${shadowOffset}px ${Math.max(1, shadowOffset)}px ${hexToRgba(
        String(config.caption_shadow_color || "#000000"),
        Number(config.caption_shadow_opacity || 0)
      )}`
    ].join("; ")
  );

  function hexToRgba(value: string, opacity: number): string {
    const hex = value.replace("#", "");
    if (!/^[0-9a-f]{6}$/i.test(hex)) return `rgba(0, 0, 0, ${opacity})`;
    return `rgba(${parseInt(hex.slice(0, 2), 16)}, ${parseInt(hex.slice(2, 4), 16)}, ${parseInt(
      hex.slice(4, 6),
      16
    )}, ${Math.max(0, Math.min(1, opacity))})`;
  }

  function display(word: string): string {
    return config.caption_uppercase ? word.toUpperCase() : word;
  }
</script>

<div class="rounded-xl border border-neutral-800 bg-neutral-950/70 p-3">
  <div class="flex items-center justify-between gap-3">
    <span class="text-[11px] uppercase tracking-wide text-neutral-500">Caption preview</span>
    <span class="rounded bg-neutral-800 px-1.5 py-0.5 font-mono text-[10px] text-neutral-400">
      9:16
    </span>
  </div>

  <div
    class="relative mx-auto mt-3 w-[240px] overflow-hidden rounded-lg border border-neutral-800 bg-[radial-gradient(circle_at_30%_20%,#334155,#0a0a0a_70%)]"
    style="aspect-ratio: 9 / 16"
    aria-label="Vertical caption style preview"
    role="img"
  >
    <div class="absolute inset-x-0 top-3 text-center text-[9px] uppercase tracking-[0.2em] text-white/25">
      Short
    </div>
    <div class="absolute bottom-0 left-0 right-0 h-1/3 bg-gradient-to-t from-black/50 to-transparent"></div>
    <div class="absolute whitespace-normal break-words leading-tight" style={boxStyle}>
      <span style={textStyle}>
        {#each words as word, index}
          <span
            class:caption-active={index === activeIndex}
            class:caption-pop={index === activeIndex && config.caption_animation === "pop"}
            class:caption-sweep={index === activeIndex && config.caption_animation === "sweep"}
            style={`--caption-highlight: ${highlight}`}
          >{display(word)}</span>{index < words.length - 1 ? " " : ""}
        {/each}
      </span>
    </div>
  </div>

  <p class="mt-2 text-[10px] leading-4 text-neutral-500">
    Approximate on-screen result. Burned captions are rendered from ASS with the same
    font, colors, outline, shadow, box, alignment, and position.
  </p>
</div>

<style>
  .caption-active {
    color: var(--caption-highlight);
  }

  .caption-pop {
    display: inline-block;
    transform: scale(1.08);
    transform-origin: center bottom;
  }

  .caption-sweep {
    text-decoration-line: underline;
    text-decoration-color: var(--caption-highlight);
    text-decoration-thickness: 2px;
    text-underline-offset: 2px;
  }
</style>
