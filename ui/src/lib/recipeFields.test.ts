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

  it("resolves nullable and referenced object fields", () => {
    const rich = {
      type: "object",
      $defs: {
        CaptionStyle: {
          type: "object",
          properties: {
            font_size: { type: "integer", minimum: 8, maximum: 300, default: 72 }
          }
        }
      },
      properties: {
        srt_path: {
          anyOf: [{ type: "string" }, { type: "null" }],
          default: null
        },
        caption_style: { $ref: "#/$defs/CaptionStyle" }
      }
    };
    const fields = fieldGroups(rich, {}, "shorts.render").flatMap((group) => group.fields);
    const byId = Object.fromEntries(fields.map((field) => [field.id, field]));

    expect(byId.srt_path).toBeDefined();
    expect(byId.srt_path.control).toBe("path");
    expect(byId["caption_style.font_size"]).toBeDefined();
    expect(byId["caption_style.font_size"].control).toBe("slider");
  });

  it("uses schema metadata for select options and path placeholders", () => {
    const fields = fieldGroups(
      {
        type: "object",
        properties: {
          transition_type: { type: "string", default: "crossfade" },
          second_source_path: { type: "string", default: "" }
        }
      },
      {},
      "edit.timeline"
    ).flatMap((group) => group.fields);
    const transition = fields.find((field) => field.id === "transition_type");
    expect(transition?.control).toBe("select");
    expect(transition?.options).toEqual(["crossfade", "fade_to_black"]);

    const second = fieldGroups(
      {
        type: "object",
        properties: { second_source_path: { type: "string", default: "" } }
      },
      {},
      "shorts.render"
    )
      .flatMap((group) => group.fields)
      .find((field) => field.id === "second_source_path");
    expect(second?.placeholder).toBe("/path/to/second-angle.mp4");
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
