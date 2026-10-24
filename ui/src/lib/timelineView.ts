import type { TimelineClip } from "./api";

export interface VisibleRange {
  start: number;
  end: number;
}

export function visibleRange(
  scrollLeft: number,
  viewportWidth: number,
  zoom: number,
  paddingSec = 3
): VisibleRange {
  const safeZoom = Math.max(1, zoom);
  return {
    start: Math.max(0, scrollLeft / safeZoom - paddingSec),
    end: (scrollLeft + Math.max(1, viewportWidth)) / safeZoom + paddingSec
  };
}

export function clipVisible(startSec: number, endSec: number, range: VisibleRange): boolean {
  return endSec >= range.start && startSec <= range.end;
}

export interface GroupTrimEdit {
  clip_id: string;
  action: "trim";
  start_sec: number;
  end_sec: number;
}

/**
 * Trim several selected clips by the same edge delta, clamped to the timeline.
 * A clip shorter than 50 ms is skipped instead of producing an invalid range.
 */
export function groupTrimEdits(
  clips: Pick<TimelineClip, "id" | "start_sec" | "end_sec">[],
  edge: "left" | "right",
  deltaSec: number,
  durationSec: number
): GroupTrimEdit[] {
  const edits: GroupTrimEdit[] = [];
  for (const clip of clips) {
    const start = Math.max(0, Math.min(clip.end_sec - 0.05, clip.start_sec + deltaSec));
    const end = Math.max(clip.start_sec + 0.05, Math.min(durationSec, clip.end_sec + deltaSec));
    const nextStart = edge === "left" ? start : clip.start_sec;
    const nextEnd = edge === "right" ? end : clip.end_sec;
    if (nextEnd - nextStart < 0.05) continue;
    if (Math.abs(nextStart - clip.start_sec) < 0.001 && Math.abs(nextEnd - clip.end_sec) < 0.001) {
      continue;
    }
    edits.push({
      clip_id: clip.id,
      action: "trim",
      start_sec: Math.round(nextStart * 1000) / 1000,
      end_sec: Math.round(nextEnd * 1000) / 1000
    });
  }
  return edits;
}
