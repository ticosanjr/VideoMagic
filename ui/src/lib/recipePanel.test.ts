import { describe, expect, it } from "vitest";
import type { Job, Recipe } from "$lib/api";
import {
  cachedCount,
  describeRecipeDiff,
  executedCount,
  outputValueText,
  retakeGroups,
  runDuration
} from "./recipePanel";

function recipe(overrides: Partial<Recipe> = {}): Recipe {
  return {
    schema_version: 1,
    id: "r",
    name: "Recipe",
    steps: [],
    ...overrides
  } as Recipe;
}

describe("recipePanel helpers", () => {
  it("renders output values", () => {
    expect(outputValueText(undefined)).toBe("");
    expect(outputValueText("text")).toBe("text");
    expect(outputValueText({ a: 1 })).toBe('{\n  "a": 1\n}');
  });

  it("filters retake groups", () => {
    expect(retakeGroups(null)).toEqual([]);
    expect(retakeGroups({ groups: "bad" })).toEqual([]);
    const valid = {
      keep: [1],
      discard: [2],
      reason: "repeat",
      keep_text: ["a"],
      discard_text: ["b"],
      start_sec: 0,
      end_sec: 1
    };
    expect(retakeGroups({ groups: [valid, { keep: [] }, 1] })).toEqual([valid]);
  });

  it("describes recipe diffs", () => {
    const older = recipe({
      name: "Old",
      steps: [
        {
          id: "a",
          type: "ingest",
          needs: [],
          inputs: {},
          params: { source: "one" },
          enabled: true
        } as Recipe["steps"][number]
      ]
    });
    const current = recipe({
      name: "New",
      steps: [
        {
          id: "a",
          type: "ingest",
          needs: ["b"],
          inputs: { source: "b" },
          params: { source: "two" },
          enabled: true
        } as Recipe["steps"][number],
        { id: "b", type: "export", needs: [], inputs: {}, params: {}, enabled: true } as Recipe["steps"][number]
      ]
    });
    const lines = describeRecipeDiff(current, older);
    expect(lines).toContain('Name: "Old" → "New"');
    expect(lines).toContain("Added step: b");
    expect(lines).toContain("a: needs [] → [b]");
    expect(lines).toContain("a: wiring changed");
    expect(lines).toContain('a.source: "one" → "two"');
    expect(lines[0]).toBe("Steps: 1 → 2");
    expect(describeRecipeDiff(older, older)).toEqual(["No recipe changes."]);
  });

  it("formats run durations and step counts", () => {
    const job = {
      duration_ms: 1500,
      result: { step_runs: [{ status: "cached" }, { status: "executed" }, { status: "cached" }] }
    } as unknown as Job;
    expect(runDuration(job)).toBe("1.5s");
    expect(cachedCount(job)).toBe(2);
    expect(executedCount(job)).toBe(1);
    expect(runDuration({ result: { elapsed_seconds: 2 } } as unknown as Job)).toBe("2.0s");
    expect(runDuration({ result: {} } as unknown as Job)).toBe("—");
  });
});
