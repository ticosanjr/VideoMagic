import { describe, expect, it } from "vitest";
import {
  AREAS,
  areaForTab,
  areaTabs,
  defaultTabForArea,
  hashFor,
  resolveRoute,
  TABS
} from "./navigation";

describe("navigation areas", () => {
  it("organizes every tab under exactly one area", () => {
    const tabs = AREAS.flatMap((area) => area.tabs);
    expect(new Set(tabs).size).toBe(tabs.length);
    expect(tabs.sort()).toEqual(TABS.map((tab) => tab.id).sort());
  });

  it("keeps the workflow order", () => {
    expect(AREAS.map((area) => area.id)).toEqual([
      "produce",
      "edit",
      "runs",
      "library",
      "setup"
    ]);
    expect(areaTabs("runs")).toEqual(["jobs", "schedules"]);
    expect(defaultTabForArea("setup")).toBe("models");
  });

  it("maps tabs to areas", () => {
    expect(areaForTab("assistant")).toBe("produce");
    expect(areaForTab("timeline")).toBe("edit");
    expect(areaForTab("media")).toBe("library");
    expect(areaForTab("connect")).toBe("setup");
  });
});

describe("resolveRoute", () => {
  it("reads flat hashes", () => {
    expect(resolveRoute("#timeline")).toEqual({ area: "edit", tab: "timeline" });
  });

  it("reads area/tab hashes", () => {
    expect(resolveRoute("#setup/providers")).toEqual(
      { area: "setup", tab: "providers" }
    );
  });

  it("redirects legacy aliases", () => {
    expect(resolveRoute("#assets").tab).toBe("media");
    expect(resolveRoute("#automation").tab).toBe("schedules");
    expect(resolveRoute("#copilot").tab).toBe("assistant");
    expect(resolveRoute("#library").tab).toBe("brand");
    expect(resolveRoute("#plugins").tab).toBe("extensions");
    expect(resolveRoute("#integrations").tab).toBe("connect");
  });

  it("falls back to produce/overview", () => {
    expect(resolveRoute("")).toEqual({ area: "produce", tab: "overview" });
    expect(resolveRoute("#unknown")).toEqual({ area: "produce", tab: "overview" });
  });

  it("builds flat hashes", () => {
    expect(hashFor("brand")).toBe("#brand");
  });
});
