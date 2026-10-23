<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import type { TimelineData } from "$lib/api";

  let {
    timeline,
    playhead = 0,
    zoom = 70,
    selectedClipId = "",
    snap = true,
    brollApproved = {},
    onSeek,
    onSelectClip,
    onMoveClip,
    onTrimClip,
    onZoom
  }: {
    timeline: TimelineData;
    playhead?: number;
    zoom?: number;
    selectedClipId?: string;
    snap?: boolean;
    brollApproved?: Record<string, number[]>;
    onSeek: (time: number) => void;
    onSelectClip: (clip: TimelineData["video"][number] | null) => void;
    onMoveClip: (clipId: string, deltaSec: number) => void;
    onTrimClip: (clipId: string, startSec: number, endSec: number) => void;
    onZoom?: (zoom: number) => void;
  } = $props();

  const HEADER = 96;
  const HEIGHT = 340;
  const RULER = 30;
  const TRACKS = [
    { id: "video", label: "V1 · VIDEO", y: 32, h: 96, color: "#0ea5e9", fill: "#082f49" },
    { id: "audio", label: "A1 · DIALOGUE", y: 132, h: 58, color: "#10b981", fill: "#022c22" },
    { id: "captions", label: "S1 · CAPTIONS", y: 194, h: 48, color: "#8b5cf6", fill: "#2e1065" },
    { id: "broll", label: "B1 · B-ROLL", y: 246, h: 62, color: "#f59e0b", fill: "#451a03" }
  ];

  let container = $state<HTMLDivElement | null>(null);
  let stage: any = null;
  let scene: any = null;
  let overlay: any = null;
  let konva: any = null;
  let playheadLine: any = null;
  let playheadKnob: any = null;
  let guideLine: any = null;
  let guideRect: any = null;
  let scrubbing = false;
  let trim: { id: string; edge: "left" | "right"; originX: number; start: number; end: number } | null = null;
  let trimGhost: { id: string; start: number; end: number } | null = null;

  const width = $derived(Math.max(1000, timeline.duration_sec * zoom + HEADER + 48));

  function x(time: number): number {
    return HEADER + time * zoom;
  }

  function timeAt(pointerX: number): number {
    return Math.max(0, Math.min(timeline.duration_sec, (pointerX - HEADER) / zoom));
  }

  function snapTargets(ignoreId: string): number[] {
    const values = [0, playhead];
    for (const clip of timeline.video) {
      if (clip.id === ignoreId) continue;
      values.push(clip.start_sec, clip.end_sec);
    }
    for (const caption of timeline.captions.slice(0, 400)) {
      values.push(caption.start_sec);
    }
    return values;
  }

  function nearestSnap(time: number, ignoreId: string): number | null {
    if (!snap) return null;
    const threshold = 9 / zoom;
    let best: number | null = null;
    let distance = threshold;
    for (const candidate of snapTargets(ignoreId)) {
      const delta = Math.abs(candidate - time);
      if (delta < distance) {
        distance = delta;
        best = candidate;
      }
    }
    return best;
  }

  function showSnap(time: number) {
    if (!konva || !overlay) return;
    if (!guideLine) {
      guideLine = new konva.Line({
        points: [0, RULER, 0, HEIGHT],
        stroke: "#fbbf24",
        strokeWidth: 1,
        dash: [4, 3],
        listening: false
      });
      overlay.add(guideLine);
    }
    guideLine.points([x(time), RULER, x(time), HEIGHT]);
    overlay.draw();
  }

  function hideSnap() {
    guideLine?.destroy();
    guideLine = null;
    overlay?.draw();
  }

  function showTrim(start: number, end: number, track: { y: number; h: number }) {
    if (!konva || !overlay) return;
    if (!guideRect) {
      guideRect = new konva.Rect({
        stroke: "#fbbf24",
        strokeWidth: 2,
        dash: [5, 3],
        listening: false
      });
      overlay.add(guideRect);
    }
    guideRect.setAttrs({
      x: x(start),
      y: track.y - 2,
      width: Math.max(2, x(end) - x(start)),
      height: track.h + 4
    });
    overlay.draw();
  }

  function hideTrim() {
    guideRect?.destroy();
    guideRect = null;
    overlay?.draw();
  }

  function buildStage() {
    if (!konva || !container || stage) return;
    stage = new konva.Stage({ container, width, height: HEIGHT });
    scene = new konva.Layer({ listening: true });
    overlay = new konva.Layer({ listening: true });
    stage.add(scene);
    stage.add(overlay);

    stage.on("mousedown touchstart", (event: any) => {
      const pointer = stage.getPointerPosition();
      if (!pointer) return;
      if (pointer.y <= RULER) {
        scrubbing = true;
        onSeek(timeAt(pointer.x));
      } else if (event.target === stage) {
        onSeek(timeAt(pointer.x));
        onSelectClip(null);
      }
    });
    stage.on("mousemove touchmove", () => {
      const pointer = stage.getPointerPosition();
      if (!pointer) return;
      if (scrubbing) onSeek(timeAt(pointer.x));
    });
    stage.on("mouseup touchend mouseleave", () => {
      scrubbing = false;
    });
    stage.on("wheel", (event: any) => {
      if (!event.evt.ctrlKey && !event.evt.metaKey) return;
      event.evt.preventDefault();
      const direction = event.evt.deltaY > 0 ? -1 : 1;
      onZoom?.(Math.max(16, Math.min(400, zoom * (direction > 0 ? 1.18 : 0.85))));
    });
  }

  function drawRuler(layer: any) {
    const majorStep = zoom >= 110 ? 1 : zoom >= 50 ? 2 : zoom >= 24 ? 5 : 10;
    for (let second = 0; second <= Math.ceil(timeline.duration_sec) + 1; second += 1) {
      const major = second % majorStep === 0;
      layer.add(
        new konva.Line({
          points: [x(second), RULER, x(second), HEIGHT],
          stroke: major ? "#27272a" : "#17171a",
          strokeWidth: 1,
          listening: false
        })
      );
      if (major) {
        layer.add(
          new konva.Text({
            x: x(second) + 3,
            y: 8,
            text: `${second}s`,
            fontSize: 9,
            fill: "#71717a",
            listening: false
          })
        );
      }
    }
    layer.add(new konva.Rect({ x: 0, y: RULER, width, height: 1, fill: "#3f3f46", listening: false }));
  }

  function drawTracks(layer: any) {
    for (const track of TRACKS) {
      layer.add(
        new konva.Text({
          x: 10,
          y: track.y + track.h / 2 - 5,
          text: track.label,
          fontSize: 8,
          fill: "#a1a1aa",
          fontStyle: "bold",
          listening: false
        })
      );
      layer.add(
        new konva.Rect({
          x: HEADER,
          y: track.y,
          width: width - HEADER,
          height: track.h,
          fill: "#111114",
          stroke: "#27272a",
          strokeWidth: 1
        })
      );
    }
  }

  function drawVideoClips(layer: any) {
    for (const clip of timeline.video) {
      const selected = clip.id === selectedClipId;
      const clipWidth = Math.max(6, (clip.end_sec - clip.start_sec) * zoom);
      const group = new konva.Group({
        x: x(clip.start_sec),
        y: TRACKS[0].y + 4,
        draggable: true,
        name: "clip"
      });
      group.add(
        new konva.Rect({
          width: clipWidth,
          height: TRACKS[0].h - 8,
          fill: selected ? "#0c4a6e" : TRACKS[0].fill,
          stroke: selected ? "#38bdf8" : "#0369a1",
          strokeWidth: selected ? 2 : 1,
          cornerRadius: 4
        })
      );
      const tickCount = Math.max(1, Math.floor(clipWidth / 14));
      for (let index = 1; index < tickCount; index += 1) {
        group.add(
          new konva.Line({
            points: [index * 14, 20, index * 14, TRACKS[0].h - 12],
            stroke: selected ? "#0ea5e9" : "#0c4a6e",
            strokeWidth: 1,
            opacity: 0.8,
            listening: false
          })
        );
      }
      group.add(
        new konva.Text({
          x: 5,
          y: 5,
          width: Math.max(0, clipWidth - 10),
          text: clip.id,
          fontSize: 9,
          fill: "#e0f2fe",
          ellipsis: true,
          listening: false
        })
      );
      group.add(
        new konva.Text({
          x: 5,
          y: 19,
          text: `${(clip.end_sec - clip.start_sec).toFixed(2)}s`,
          fontSize: 8,
          fill: "#7dd3fc",
          listening: false
        })
      );
      if (clip.keyframes) {
        group.add(
          new konva.Text({
            x: 5,
            y: 33,
            text: `${clip.keyframes} keyframes`,
            fontSize: 8,
            fill: "#bae6fd",
            listening: false
          })
        );
      }
      if (clip.transition) {
        group.add(
          new konva.Text({
            x: 5,
            y: 45,
            text: clip.transition,
            fontSize: 8,
            fill: "#fcd34d",
            listening: false
          })
        );
      }
      group.on("click tap", (event: any) => {
        event.cancelBubble = true;
        onSelectClip(clip);
      });
      group.on("mouseenter", () => {
        if (stage) stage.container().style.cursor = "grab";
      });
      group.on("mouseleave", () => {
        if (stage) stage.container().style.cursor = "default";
      });
      group.on("dragstart", () => {
        if (stage) stage.container().style.cursor = "grabbing";
      });
      group.on("dragmove", () => {
        const proposed = (group.x() - HEADER) / zoom;
        const snapped = nearestSnap(proposed, clip.id);
        if (snapped !== null) {
          group.x(x(snapped));
          showSnap(snapped);
        } else {
          hideSnap();
        }
        group.y(TRACKS[0].y + 4);
      });
      group.on("dragend", () => {
        hideSnap();
        if (stage) stage.container().style.cursor = "grab";
        const snapped = (group.x() - HEADER) / zoom;
        group.x(x(clip.start_sec));
        const delta = snapped - clip.start_sec;
        if (Math.abs(delta) > 0.001) onMoveClip(clip.id, delta);
      });
      layer.add(group);
    }
  }

  function drawAudioClips(layer: any) {
    for (const clip of timeline.audio) {
      const clipWidth = Math.max(4, (clip.end_sec - clip.start_sec) * zoom);
      layer.add(
        new konva.Rect({
          x: x(clip.start_sec),
          y: TRACKS[1].y + 5,
          width: clipWidth,
          height: TRACKS[1].h - 10,
          fill: "#064e3b",
          stroke: "#059669",
          cornerRadius: 3,
          listening: false
        })
      );
      const bars = Math.max(1, Math.floor(clipWidth / 5));
      for (let index = 0; index < bars; index += 1) {
        const amplitude = 0.25 + 0.7 * Math.abs(Math.sin((index + 1) * 1.7 + clip.start_sec));
        const barHeight = (TRACKS[1].h - 20) * amplitude;
        layer.add(
          new konva.Line({
            points: [
              x(clip.start_sec) + index * 5 + 2,
              TRACKS[1].y + TRACKS[1].h / 2 - barHeight / 2,
              x(clip.start_sec) + index * 5 + 2,
              TRACKS[1].y + TRACKS[1].h / 2 + barHeight / 2
            ],
            stroke: "#34d399",
            strokeWidth: 1.5,
            opacity: 0.7,
            listening: false
          })
        );
      }
      layer.add(
        new konva.Text({
          x: x(clip.start_sec) + 4,
          y: TRACKS[1].y + 5,
          text: clip.id,
          fontSize: 8,
          fill: "#a7f3d0",
          listening: false
        })
      );
    }
  }

  function drawCaptions(layer: any) {
    for (const caption of timeline.captions.slice(0, 500)) {
      const clipWidth = Math.max(3, (caption.end_sec - caption.start_sec) * zoom);
      const current = caption.start_sec <= playhead && playhead <= caption.end_sec;
      layer.add(
        new konva.Rect({
          x: x(caption.start_sec),
          y: TRACKS[2].y + 5,
          width: clipWidth,
          height: TRACKS[2].h - 10,
          fill: current ? "#6d28d9" : TRACKS[2].fill,
          stroke: "#8b5cf6",
          cornerRadius: 3,
          listening: false
        })
      );
      if (clipWidth > 40) {
        layer.add(
          new konva.Text({
            x: x(caption.start_sec) + 4,
            y: TRACKS[2].y + 10,
            width: clipWidth - 8,
            text: caption.text,
            fontSize: 8,
            fill: "#ede9fe",
            ellipsis: true,
            wrap: "none",
            listening: false
          })
        );
      }
    }
  }

  function drawBroll(layer: any) {
    let chipX = x(0);
    for (const [title, entries] of Object.entries(timeline.broll ?? {})) {
      const approved =
        brollApproved[title]?.length ?? timeline.broll_approval?.[title]?.approved?.length ?? 0;
      const chipWidth = Math.max(90, Math.min(220, timeline.duration_sec * zoom * 0.18));
      layer.add(
        new konva.Rect({
          x: chipX,
          y: TRACKS[3].y + 5,
          width: chipWidth,
          height: TRACKS[3].h - 10,
          fill: approved > 0 ? "#78350f" : "#27272a",
          stroke: approved > 0 ? "#f59e0b" : "#52525b",
          cornerRadius: 4,
          listening: false
        })
      );
      layer.add(
        new konva.Text({
          x: chipX + 5,
          y: TRACKS[3].y + 9,
          width: chipWidth - 10,
          text: title,
          fontSize: 8,
          fill: "#fde68a",
          ellipsis: true,
          wrap: "none",
          listening: false
        })
      );
      layer.add(
        new konva.Text({
          x: chipX + 5,
          y: TRACKS[3].y + 23,
          text: `${approved}/${entries.length} approved`,
          fontSize: 8,
          fill: approved > 0 ? "#fbbf24" : "#a1a1aa",
          listening: false
        })
      );
      chipX += chipWidth + 8;
      if (chipX > width - 40) break;
    }
  }

  function drawBackground() {
    if (!konva || !container) return;
    buildStage();
    if (!stage || !scene) return;
    stage.width(width);
    scene.destroyChildren();
    scene.add(new konva.Rect({ x: 0, y: 0, width, height: HEIGHT, fill: "#09090b" }));
    scene.add(
      new konva.Rect({
        x: 0,
        y: 0,
        width: HEADER,
        height: HEIGHT,
        fill: "#0c0c0f",
        stroke: "#27272a",
        strokeWidth: 1
      })
    );
    scene.add(
      new konva.Text({ x: 10, y: 8, text: "TIMELINE", fontSize: 10, fill: "#71717a", fontStyle: "bold" })
    );
    scene.add(
      new konva.Text({
        x: 10,
        y: 310,
        text: `${timeline.video.length} clips · ${timeline.captions.length} captions · ${Math.round(timeline.duration_sec)}s`,
        fontSize: 8,
        fill: "#52525b"
      })
    );
    drawRuler(scene);
    drawTracks(scene);
    drawVideoClips(scene);
    drawAudioClips(scene);
    drawCaptions(scene);
    drawBroll(scene);
    scene.draw();
  }

  function drawOverlay() {
    if (!konva || !overlay) return;
    overlay.destroyChildren();
    playheadLine = null;
    playheadKnob = null;
    guideLine = null;
    guideRect = null;

    const clip = timeline.video.find((item) => item.id === selectedClipId);
    if (clip) {
      for (const edge of ["left", "right"] as const) {
        const handleX = edge === "left" ? x(clip.start_sec) - 4 : x(clip.end_sec) - 4;
        const handle = new konva.Rect({
          x: handleX,
          y: TRACKS[0].y + 2,
          width: 8,
          height: TRACKS[0].h - 4,
          fill: "#f43f5e",
          cornerRadius: 2,
          draggable: true
        });
        handle.on("mouseenter", () => {
          if (stage) stage.container().style.cursor = "ew-resize";
        });
        handle.on("mouseleave", () => {
          if (stage) stage.container().style.cursor = "default";
        });
        handle.on("dragstart", (event: any) => {
          event.cancelBubble = true;
          trim = {
            id: clip.id,
            edge,
            originX: handle.x(),
            start: clip.start_sec,
            end: clip.end_sec
          };
        });
        handle.on("dragmove", (event: any) => {
          event.cancelBubble = true;
          handle.y(TRACKS[0].y + 2);
          if (!trim) return;
          const delta = (handle.x() - trim.originX) / zoom;
          if (edge === "left") {
            trimGhost = {
              id: clip.id,
              start: Math.max(0, Math.min(trim.end - 0.05, trim.start + delta)),
              end: trim.end
            };
          } else {
            trimGhost = {
              id: clip.id,
              start: trim.start,
              end: Math.max(trim.start + 0.05, Math.min(timeline.duration_sec, trim.end + delta))
            };
          }
          showTrim(trimGhost.start, trimGhost.end, TRACKS[0]);
        });
        handle.on("dragend", (event: any) => {
          event.cancelBubble = true;
          const ghost = trimGhost;
          trim = null;
          trimGhost = null;
          hideTrim();
          if (!ghost) return;
          const start = Math.round(ghost.start * 1000) / 1000;
          const end = Math.round(ghost.end * 1000) / 1000;
          if (Math.abs(start - clip.start_sec) > 0.001 || Math.abs(end - clip.end_sec) > 0.001) {
            onTrimClip(clip.id, start, end);
          }
        });
        overlay.add(handle);
      }
    }

    playheadLine = new konva.Line({
      points: [x(playhead), RULER, x(playhead), HEIGHT],
      stroke: "#fb7185",
      strokeWidth: 2,
      listening: false
    });
    overlay.add(playheadLine);
    playheadKnob = new konva.Circle({
      x: x(playhead),
      y: 16,
      radius: 6,
      fill: "#fb7185",
      stroke: "#4c0519",
      strokeWidth: 1,
      draggable: true,
      dragBoundFunc: (position: { x: number; y: number }) => ({
        x: Math.max(HEADER, Math.min(width - 8, position.x)),
        y: 16
      })
    });
    playheadKnob.on("dragmove", () => {
      const pointer = stage?.getPointerPosition();
      if (pointer) onSeek(timeAt(pointer.x));
    });
    overlay.add(playheadKnob);
    overlay.draw();
  }

  function updatePlayhead() {
    if (!playheadLine || !playheadKnob || !overlay) return;
    playheadLine.points([x(playhead), RULER, x(playhead), HEIGHT]);
    playheadKnob.x(x(playhead));
    overlay.batchDraw();
  }

  onMount(async () => {
    konva = (await import("konva")).default;
    drawBackground();
    drawOverlay();
  });

  onDestroy(() => {
    stage?.destroy();
    stage = null;
    scene = null;
    overlay = null;
  });

  $effect(() => {
    timeline;
    zoom;
    selectedClipId;
    brollApproved;
    if (stage) {
      drawBackground();
      drawOverlay();
    }
  });

  $effect(() => {
    playhead;
    updatePlayhead();
  });
</script>

<div class="relative overflow-hidden rounded-xl border border-neutral-800 bg-neutral-950" data-testid="timeline-canvas">
  <div class="overflow-x-auto">
    <div bind:this={container} style={`width:${width}px;height:${HEIGHT}px`}></div>
  </div>
</div>
