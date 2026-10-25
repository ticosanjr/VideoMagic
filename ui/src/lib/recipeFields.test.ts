import { describe, expect, it } from "vitest";
import { fieldGroups, nodePresets } from "./recipeFields";

const schema = {
  type: "object",
  properties: {
    noise_db: { type: "number", minimum: -80, maximum: -5, default: -30 },
    engine: { type: "string", enum: ["auto", "silero", "ffmpeg"], default: "auto" },
    apply_pads: { type: "boolean", default: false },
    targets: {
      type: "array",
      items: { type: "string", enum: ["mp4", "resolve", "premiere"] },
      default: ["mp4"]
    },
    huge: { type: "number", minimum: 0, maximum: 60000, default: 10 }
  }
};

describe("recipeFields controls", () => {
  it("maps bounded numbers to sliders and enums to segmented controls", () => {
    const groups = fieldGroups(schema, {}, "audio.vad");
    const fields = Object.fromEntries(groups.flatMap((group) => group.fields).map((field) => [field.id, field]));
    expect(fields.noise_db.control).toBe("slider");
    expect(fields.engine.control).toBe("segmented");
    expect(fields.apply_pads.control).toBe("switch");
    expect(fields.targets.control).toBe("chips");
    expect(fields.targets.itemOptions).toEqual(["mp4", "resolve", "premiere"]);
    expect(fields.huge.control).toBe("number");
  });

  it("groups VAD fields and exposes node presets", () => {
    const groups = fieldGroups(schema, {}, "audio.vad");
    expect(groups[0].label).toBe("Detection");
    expect(groups.map((group) => group.label)).toContain("Detection");
    expect(groups.map((group) => group.label)).toContain("Advanced");
    expect(nodePresets("audio.vad").map((preset) => preset.label)).toContain("Aggressive");
    expect(nodePresets("edit.timeline").map((preset) => preset.label)).toContain("J-cut");
  });
});
