import { describe, expect, it } from "vitest";
import {
  filterCommands,
  moveActiveIndex,
  recordRecentCommand,
  withRecentCommands,
  type Command
} from "./commandPalette";

const COMMANDS: Command[] = [
  { id: "tab:recipes", title: "Open Recipes", group: "Navigate", keywords: "run build" },
  { id: "tab:timeline", title: "Open Timeline", group: "Navigate", keywords: "edit clips" },
  { id: "tab:jobs", title: "Open Jobs", group: "Navigate", keywords: "queue dashboard" },
  { id: "action:backup", title: "Back up the home folder", group: "Maintain" }
];

describe("filterCommands", () => {
  it("returns everything without a query", () => {
    expect(filterCommands(COMMANDS, "")).toHaveLength(4);
  });

  it("matches title and keywords case insensitively", () => {
    expect(filterCommands(COMMANDS, "TIMELINE")[0].id).toBe("tab:timeline");
    expect(filterCommands(COMMANDS, "queue")[0].id).toBe("tab:jobs");
  });

  it("ranks title matches before keyword matches", () => {
    const result = filterCommands(COMMANDS, "open");
    expect(result.map((command) => command.id)).toEqual([
      "tab:recipes",
      "tab:timeline",
      "tab:jobs"
    ]);
  });

  it("returns nothing when the query does not match", () => {
    expect(filterCommands(COMMANDS, "nonexistent")).toEqual([]);
  });
});

describe("moveActiveIndex", () => {
  it("wraps around both ends", () => {
    expect(moveActiveIndex(0, 3, -1)).toBe(2);
    expect(moveActiveIndex(2, 3, 1)).toBe(0);
    expect(moveActiveIndex(1, 3, 1)).toBe(2);
  });

  it("stays at zero for empty lists", () => {
    expect(moveActiveIndex(4, 0, 1)).toBe(0);
  });
});

describe("recordRecentCommand", () => {
  it("moves an existing command to the front", () => {
    expect(recordRecentCommand(["a", "b", "c"], "b")).toEqual(["b", "a", "c"]);
  });

  it("caps the list at the limit", () => {
    expect(recordRecentCommand(["a", "b", "c", "d", "e"], "f")).toEqual([
      "f",
      "a",
      "b",
      "c",
      "d"
    ]);
  });
});

describe("withRecentCommands", () => {
  it("returns the original list without recent ids", () => {
    expect(withRecentCommands(COMMANDS, [])).toBe(COMMANDS);
  });

  it("places recent commands first with a Recent group", () => {
    const result = withRecentCommands(COMMANDS, ["tab:jobs", "action:backup"]);
    expect(result.slice(0, 2).map((command) => command.id)).toEqual([
      "tab:jobs",
      "action:backup"
    ]);
    expect(result[0].group).toBe("Recent");
    expect(result).toHaveLength(COMMANDS.length);
  });

  it("ignores unknown and duplicate recent ids", () => {
    const result = withRecentCommands(COMMANDS, [
      "missing",
      "tab:timeline",
      "tab:timeline"
    ]);
    expect(result[0].id).toBe("tab:timeline");
    expect(result).toHaveLength(COMMANDS.length);
  });
});
