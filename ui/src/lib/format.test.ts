import { describe, expect, it } from "vitest";
import {
  elapsedMs,
  formatBytes,
  formatDateTime,
  formatDuration,
  formatSeconds,
  statusText
} from "./format";

describe("formatDuration", () => {
  it("formats milliseconds, seconds, and hours", () => {
    expect(formatDuration(0)).toBe("0 ms");
    expect(formatDuration(428)).toBe("428 ms");
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

describe("formatSeconds", () => {
  it("renders media durations", () => {
    expect(formatSeconds(65.2)).toBe("1:05");
    expect(formatSeconds(null)).toBe("—");
  });
});

describe("formatBytes", () => {
  it("renders file sizes", () => {
    expect(formatBytes(0)).toBe("0 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(10 * 1024 * 1024)).toBe("10 MB");
    expect(formatBytes(null)).toBe("—");
  });
});
