import { describe, expect, it } from "vitest";
import { clipVisible, groupTrimEdits, visibleRange } from "./timelineView";

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
