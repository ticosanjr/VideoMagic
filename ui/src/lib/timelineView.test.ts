import { describe, expect, it } from "vitest";
import {
  clipVisible,
  fitScrollLeft,
  fitZoom,
  groupTrimEdits,
  liveOutputDuration,
  liveSegments,
  outputForSource,
  sourceForOutput,
  visibleRange
} from "./timelineView";

describe("visibleRange", () => {
  it("maps scroll and zoom to a padded time window", () => {
    expect(visibleRange(700, 1400, 70)).toEqual({ start: 7, end: 33 });
  });

  it("never goes below zero", () => {
    expect(visibleRange(0, 1000, 50).start).toBe(0);
  });

  it("survives a zero zoom", () => {
    const range = visibleRange(0, 1000, 0);
    expect(Number.isFinite(range.end)).toBe(true);
  });
});

describe("clipVisible", () => {
  const range = visibleRange(700, 1400, 70);

  it("keeps overlapping clips", () => {
    expect(clipVisible(5, 10, range)).toBe(true);
    expect(clipVisible(30, 40, range)).toBe(true);
  });

  it("drops clips outside the window", () => {
    expect(clipVisible(0, 3, range)).toBe(false);
    expect(clipVisible(60, 70, range)).toBe(false);
  });
});

describe("groupTrimEdits", () => {
  const clips = [
    { id: "a", start_sec: 0, end_sec: 5 },
    { id: "b", start_sec: 5, end_sec: 10 }
  ];

  it("moves the right edge of every selected clip", () => {
    expect(groupTrimEdits(clips, "right", 1, 20)).toEqual([
      { clip_id: "a", action: "trim", start_sec: 0, end_sec: 6 },
      { clip_id: "b", action: "trim", start_sec: 5, end_sec: 11 }
    ]);
  });

  it("clamps the left edge at zero and skips the unchanged clip", () => {
    expect(groupTrimEdits(clips, "left", -4, 20)).toEqual([
      { clip_id: "b", action: "trim", start_sec: 1, end_sec: 10 }
    ]);
  });

  it("clamps the right edge at the timeline duration", () => {
    const edits = groupTrimEdits(clips, "right", 20, 12);
    expect(edits.map((edit) => edit.end_sec)).toEqual([12, 12]);
  });

  it("skips edits that would not change the clip", () => {
    expect(groupTrimEdits(clips, "right", 0, 20)).toEqual([]);
  });
});


describe("liveSegments", () => {
  it("orders active ranges and skips the inactive gap in output time", () => {
    const segments = liveSegments(
      [
        { id: "b", start_sec: 5, end_sec: 7, source_in_frame: 75, source_out_frame: 105 },
        { id: "a", start_sec: 0, end_sec: 2, source_in_frame: 0, source_out_frame: 30 }
      ],
      15
    );

    expect(segments).toEqual([
      { id: "a", start: 0, end: 2, outputStart: 0, outputEnd: 2 },
      { id: "b", start: 5, end: 7, outputStart: 2, outputEnd: 4 }
    ]);
  });

  it("overlaps crossfade segments and shortens the output duration", () => {
    const segments = liveSegments(
      [
        {
          id: "a",
          start_sec: 0,
          end_sec: 2,
          source_in_frame: 0,
          source_out_frame: 30,
          transition: "crossfade",
          transition_frames: 5,
          transition_audio: true
        },
        {
          id: "b",
          start_sec: 5,
          end_sec: 7,
          source_in_frame: 75,
          source_out_frame: 105
        }
      ],
      15
    );

    expect(segments[0]).toMatchObject({
      transitionOut: { type: "crossfade", duration: 1 / 3, audio: true }
    });
    expect(segments[1].outputStart).toBeCloseTo(2 - 1 / 3);
    expect(liveOutputDuration(segments)).toBeCloseTo(2 + 2 - 1 / 3);
  });

  it("does not overlap fade-to-black segments", () => {
    const segments = liveSegments(
      [
        {
          id: "a",
          start_sec: 0,
          end_sec: 2,
          source_in_frame: 0,
          source_out_frame: 30,
          transition: "fade_to_black",
          transition_frames: 5
        },
        { id: "b", start_sec: 2, end_sec: 4, source_in_frame: 30, source_out_frame: 60 }
      ],
      15
    );
    expect(segments[1].outputStart).toBe(2);
    expect(liveOutputDuration(segments)).toBe(4);
  });

  it("uses explicit source seconds when provided", () => {
    const segments = liveSegments(
      [{ id: "a", start_sec: 3, end_sec: 4, source_start_sec: 10, source_end_sec: 11 }],
      30
    );
    expect(segments[0]).toMatchObject({ start: 10, end: 11, outputStart: 0 });
  });
});

describe("source and output mapping", () => {
  const segments = liveSegments(
    [
      { id: "a", start_sec: 0, end_sec: 2, source_in_frame: 0, source_out_frame: 30 },
      { id: "b", start_sec: 5, end_sec: 7, source_in_frame: 75, source_out_frame: 105 }
    ],
    15
  );

  it("maps the official playhead to the source used by the player", () => {
    expect(sourceForOutput(segments, 0)).toBe(0);
    expect(sourceForOutput(segments, 1.5)).toBe(1.5);
    expect(sourceForOutput(segments, 2)).toBe(5);
    expect(sourceForOutput(segments, 2.5)).toBe(5.5);
    expect(sourceForOutput(segments, 3.5)).toBe(6.5);
  });

  it("maps a Recut source cursor back to the official output playhead", () => {
    expect(outputForSource(segments, 0)).toBe(0);
    expect(outputForSource(segments, 1.5)).toBe(1.5);
    expect(outputForSource(segments, 3)).toBe(2);
    expect(outputForSource(segments, 6)).toBe(3);
  });
});

describe("fit helpers", () => {
  it("fits a span into the real viewport minus the fixed header", () => {
    expect(fitZoom(10, 1096, 96, 0)).toBe(100);
    expect(fitZoom(10, 1096, 96, 96)).toBeCloseTo(90.4);
  });

  it("clamps the zoom to the supported range", () => {
    expect(fitZoom(0.01, 500, 0, 0)).toBe(400);
    expect(fitZoom(10_000, 500, 0, 0)).toBe(2);
  });

  it("keeps a margin before the fitted range", () => {
    expect(fitScrollLeft(5, 100)).toBe(476);
    expect(fitScrollLeft(0, 100)).toBe(0);
  });
});
