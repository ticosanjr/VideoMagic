<script lang="ts">
  import { onDestroy, onMount } from "svelte";

  let {
    url = "",
    playhead = 0,
    duration = 1,
    onSeek
  }: {
    url?: string;
    playhead?: number;
    duration?: number;
    onSeek: (time: number) => void;
  } = $props();

  let container = $state<HTMLDivElement | null>(null);
  let player: any = null;
  let loading = $state(false);
  let error = $state("");

  const percent = $derived(Math.max(0, Math.min(100, (playhead / Math.max(0.001, duration)) * 100)));

  async function load(target: string) {
    if (!target || !container) return;
    error = "";
    loading = true;
    try {
      const WaveSurfer = (await import("wavesurfer.js")).default;
      player?.destroy();
      player = WaveSurfer.create({
        container,
        url: target,
        height: 54,
        waveColor: "#1f6f5c",
        progressColor: "#34d399",
        cursorColor: "transparent",
        cursorWidth: 0,
        barWidth: 2,
        barGap: 1,
        barRadius: 2,
        normalize: true,
        interact: true,
        backend: "WebAudio"
      });
      player.on("interaction", (time: number) => onSeek(Math.max(0, time)));
      player.on("error", (reason: unknown) => {
        error = `Waveform unavailable: ${String(reason)}`;
      });
    } catch (reason) {
      error = `Waveform unavailable: ${String(reason)}`;
    } finally {
      loading = false;
    }
  }

  onMount(() => {
    if (url) void load(url);
  });

  onDestroy(() => {
    player?.destroy();
    player = null;
  });

  $effect(() => {
    if (url && player === null) void load(url);
  });
</script>

<div class="relative overflow-hidden rounded-xl border border-neutral-800 bg-neutral-950">
  <div class="flex items-center justify-between border-b border-neutral-800 px-3 py-1.5">
    <span class="text-[10px] uppercase tracking-wide text-neutral-500">Waveform</span>
    <span class="font-mono text-[10px] text-neutral-500">{playhead.toFixed(2)}s / {duration.toFixed(1)}s</span>
  </div>
  <div class="relative">
    <div bind:this={container} class="px-2 py-1" data-testid="timeline-waveform"></div>
    {#if loading}<p class="px-3 py-2 text-[10px] text-neutral-500">Reading waveform…</p>{/if}
    {#if error}<p class="px-3 py-2 text-[10px] text-amber-300">{error}</p>{/if}
    {#if !loading && !error}
      <div class="pointer-events-none absolute inset-y-1 w-px bg-rose-400" style={`left:${percent}%`}></div>
    {/if}
  </div>
</div>
