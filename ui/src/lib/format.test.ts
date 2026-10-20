import { describe, expect, it } from "vitest";
import { elapsedMs, formatDateTime, formatDuration, statusText } from "./format";

describe("formatDuration", () => {
  it("formats seconds and hours", () => {
    expect(formatDuration(0)).toBe("0:00");
    expect(formatDuration(65_000)).toBe("1:05");
    expect(formatDuration(3_725_000)).toBe("1:02:05");
  });

  it("returns a dash for missing values", () => {
    expect(formatDuration(null)).toBe("—");
    expect(formatDuration(undefined)).toBe("—");
  });
});

describe("elapsedMs", () => {
  it("uses the finish time when present", () => {
    expect(
      elapsedMs("2026-10-20T10:00:00+00:00", "2026-10-20T10:00:02+00:00")
    ).toBe(2000);
  });

  it("uses now while running", () => {
    const now = new Date("2026-10-20T10:00:03+00:00").getTime();
    expect(elapsedMs("2026-10-20T10:00:00+00:00", null, now)).toBe(3000);
  });

  it("returns null without a start", () => {
    expect(elapsedMs(null, null)).toBeNull();
  });
});

describe("formatDateTime", () => {
  it("returns a dash for an empty value", () => {
    expect(formatDateTime(null)).toBe("—");
  });

  it("formats an ISO timestamp", () => {
    expect(formatDateTime("2026-10-20T10:00:00+00:00")).not.toBe("—");
  });
});

describe("statusText", () => {
  it("normalizes underscores", () => {
    expect(statusText("in_review")).toBe("in review");
  });
});
