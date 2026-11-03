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
  it("maps bounded numbers to sliders and enums/arrays to dropdowns", () => {
    const groups = fieldGroups(schema, {}, "audio.vad");
    const fields = Object.fromEntries(groups.flatMap((group) => group.fields).map((field) => [field.id, field]));
    expect(fields.noise_db.control).toBe("slider");
    expect(fields.engine.control).toBe("select");
    expect(fields.apply_pads.control).toBe("switch");
    expect(fields.targets.control).toBe("multi");
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

describe("transcribe field visibility", () => {
  const transcribeSchema = {
    type: "object",
    properties: {
      provider_id: { type: "string", default: "" },
      mode: {
        type: "string",
        enum: ["auto", "srt", "http", "faster_whisper", "whisper_cpp"],
        default: "auto"
      },
      model_id: { type: "string", default: "" },
      model_size: { type: "string", default: "small" },
      srt_path: { type: "string", default: "" },
      base_url: { type: "string", default: "" },
      whisper_model: { type: "string", default: "" },
      device: { type: "string", default: "cpu" }
    }
  };
  const ids = (params: Record<string, unknown>) =>
    fieldGroups(transcribeSchema, params, "transcribe")
      .flatMap((group) => group.fields)
      .map((field) => field.id);

  it("shows HTTP fields only without a provider", () => {
    expect(ids({ mode: "http", provider_id: "" })).toContain("base_url");
    expect(ids({ mode: "http", provider_id: "asr-demo" })).not.toContain("base_url");
  });

  it("shows local model fields only for the matching mode", () => {
    expect(ids({ mode: "faster_whisper" })).toContain("model_size");
    expect(ids({ mode: "whisper_cpp" })).not.toContain("model_size");
    expect(ids({ mode: "whisper_cpp" })).toContain("whisper_model");
    expect(ids({ mode: "srt" })).toContain("srt_path");
    expect(ids({ mode: "srt" })).not.toContain("whisper_model");
  });

  it("disables model size when an explicit model id is selected", () => {
    const field = fieldGroups(
      transcribeSchema,
      { mode: "faster_whisper", model_id: "faster-whisper-tiny" },
      "transcribe"
    )
      .flatMap((group) => group.fields)
      .find((item) => item.id === "model_size");
    expect(field?.visible).toBe(true);
    expect(field?.disabled).toBe(true);
  });
});
