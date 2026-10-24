import { describe, expect, it } from "vitest";
import { nextFocusIndex } from "./a11y";

describe("nextFocusIndex", () => {
  it("wraps forward and backward", () => {
    expect(nextFocusIndex(2, 3, false)).toBe(0);
    expect(nextFocusIndex(0, 3, true)).toBe(2);
    expect(nextFocusIndex(1, 3, false)).toBe(2);
    expect(nextFocusIndex(2, 3, true)).toBe(1);
  });

  it("enters the list from outside", () => {
    expect(nextFocusIndex(-1, 3, false)).toBe(0);
    expect(nextFocusIndex(-1, 3, true)).toBe(2);
  });

  it("handles an empty list", () => {
    expect(nextFocusIndex(0, 0, false)).toBe(0);
  });
});
