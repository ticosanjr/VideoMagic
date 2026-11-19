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

  it("keeps the MCP control order", () => {
    expect(AREAS.map((area) => area.id)).toEqual(["runs", "setup"]);
    expect(areaTabs("runs")).toEqual(["overview", "jobs"]);
    expect(defaultTabForArea("setup")).toBe("models");
  });

  it("maps tabs to areas", () => {
    expect(areaForTab("jobs")).toBe("runs");
    expect(areaForTab("connect")).toBe("setup");
    expect(areaForTab("gpu")).toBe("setup");
  });
});

describe("resolveRoute", () => {
  it("reads flat hashes", () => {
    expect(resolveRoute("#jobs")).toEqual({ area: "runs", tab: "jobs" });
  });

  it("reads area/tab hashes", () => {
    expect(resolveRoute("#setup/providers")).toEqual(
      { area: "setup", tab: "providers" }
    );
  });

  it("redirects legacy aliases", () => {
    expect(resolveRoute("#plugins").tab).toBe("extensions");
    expect(resolveRoute("#integrations").tab).toBe("connect");
    expect(resolveRoute("#home").tab).toBe("overview");
  });

  it("falls back to runs/overview", () => {
    expect(resolveRoute("")).toEqual({ area: "runs", tab: "overview" });
    expect(resolveRoute("#unknown")).toEqual({ area: "runs", tab: "overview" });
  });

  it("builds flat hashes", () => {
    expect(hashFor("gpu")).toBe("#gpu");
  });
});
