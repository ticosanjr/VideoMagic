import { describe, expect, it } from "vitest";
import { moduleTabs } from "./modules";

describe("module tabs", () => {
  it("keeps every primary workspace discoverable", () => {
    const ids = moduleTabs.map((tab) => tab.id);
    expect(ids).toEqual([
      "speech",
      "edit",
      "shorts",
      "studio",
      "export",
      "models",
      "services",
      "providers"
    ]);
  });
});
