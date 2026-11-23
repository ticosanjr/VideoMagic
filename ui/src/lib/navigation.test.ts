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

describe("three-screen navigation", () => {
  it("exposes exactly curation, jobs, and setup", () => {
    expect(TABS.map((tab) => tab.id)).toEqual(["curation", "jobs", "setup"]);
    expect(AREAS.map((area) => area.id)).toEqual(["main"]);
    expect(areaTabs("main")).toEqual(["curation", "jobs", "setup"]);
    expect(defaultTabForArea("main")).toBe("curation");
    expect(areaForTab("jobs")).toBe("main");
  });
});

describe("resolveRoute", () => {
  it("reads flat hashes", () => {
    expect(resolveRoute("#jobs")).toEqual({ area: "main", tab: "jobs" });
    expect(resolveRoute("#setup")).toEqual({ area: "main", tab: "setup" });
  });

  it("reads curation project deep links", () => {
    expect(resolveRoute("#curation/abc-123")).toEqual({
      area: "main",
      tab: "curation"
    });
  });

  it("redirects legacy setup aliases", () => {
    expect(resolveRoute("#plugins").tab).toBe("setup");
    expect(resolveRoute("#gpu").tab).toBe("setup");
    expect(resolveRoute("#connect").tab).toBe("setup");
    expect(resolveRoute("#home").tab).toBe("curation");
  });

  it("falls back to curation", () => {
    expect(resolveRoute("")).toEqual({ area: "main", tab: "curation" });
    expect(resolveRoute("#unknown")).toEqual({ area: "main", tab: "curation" });
  });

  it("builds flat hashes", () => {
    expect(hashFor("setup")).toBe("#setup");
    expect(hashFor("curation")).toBe("#curation");
  });
});
