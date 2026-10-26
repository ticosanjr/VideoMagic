export type RecipeFieldKind = "boolean" | "number" | "enum" | "text" | "color" | "path" | "json";
export type RecipeControl =
  | "switch"
  | "slider"
  | "number"
  | "select"
  | "segmented"
  | "chips"
  | "path"
  | "color"
  | "json"
  | "text";

export interface RecipeField {
  path: string[];
  id: string;
  label: string;
  kind: RecipeFieldKind;
  control: RecipeControl;
  group: string;
  unit: string;
  options: string[];
  optionsSource: string;
  itemOptions: string[];
  minimum?: number;
  maximum?: number;
  step?: number;
  integer: boolean;
  required: boolean;
  format: string;
  pattern: string;
  placeholder: string;
  help: string;
  value: unknown;
  defaultValue: unknown;
}

export interface RecipeFieldGroup {
  path: string[];
  label: string;
  fields: RecipeField[];
}

type Schema = Record<string, unknown>;
type FieldMeta = {
  group?: string;
  unit?: string;
  label?: string;
  control?: RecipeControl;
  step?: number;
  optionsSource?: string;
  placeholder?: string;
  options?: string[];
};

const FIELD_META: Record<string, Record<string, FieldMeta>> = {
  "audio.vad": {
    engine: { group: "Detection", label: "Engine" },
    noise_db: { group: "Detection", unit: "dB", label: "Noise threshold" },
    speech_threshold: { group: "Detection", label: "Speech threshold" },
    min_silence_ms: { group: "Detection", unit: "ms", label: "Minimum silence" },
    min_speech_ms: { group: "Detection", unit: "ms", label: "Minimum speech" },
    spike_suppression_ms: { group: "Cleanup", unit: "ms", label: "Short spike suppression" },
    merge_gap_ms: { group: "Cleanup", unit: "ms", label: "Merge tiny gaps" },
    pad_before_ms: { group: "Handles", unit: "ms", label: "Pad before" },
    pad_after_ms: { group: "Handles", unit: "ms", label: "Pad after" },
    apply_pads: { group: "Advanced", label: "Apply pads in the VAD (debug)" }
  },
  "edit.timeline": {
    cut_mode: { group: "Cut", label: "Cut mode" },
    enable_j_cuts: { group: "Cut", label: "Enable J-cuts (custom)" },
    enable_l_cuts: { group: "Cut", label: "Enable L-cuts (custom)" },
    offset_ms: { group: "Cut", unit: "ms", label: "J/L audio offset" },
    audio_crossfade_ms: { group: "Cut", unit: "ms", label: "Audio crossfade" },
    fade_in_ms: { group: "Cut", unit: "ms", label: "Fade in" },
    fade_out_ms: { group: "Cut", unit: "ms", label: "Fade out" },
    fade_curve: { group: "Cut", label: "Fade curve" },
    handle_check: { group: "Cut", label: "Check source handles" },
    zoom_mode: { group: "Zoom", label: "Zoom mode" },
    zoom_min_scale: { group: "Zoom", label: "Minimum zoom", step: 0.05 },
    zoom_max_scale: { group: "Zoom", label: "Maximum zoom", step: 0.05 },
    punch_in_scale: { group: "Zoom", label: "Punch-in zoom", step: 0.05 },
    anchor_point: { group: "Zoom", label: "Zoom anchor" },
    progressive_zoom: { group: "Zoom", label: "Progressive zoom" },
    pan_direction: { group: "Zoom", label: "Pan direction" },
    pad_before_ms: { group: "Handles", unit: "ms", label: "Pad before override" },
    pad_after_ms: { group: "Handles", unit: "ms", label: "Pad after override" },
    transition_frames: {
      group: "Transitions",
      unit: "frames",
      label: "Transition length",
      control: "number"
    },
    transition_type: {
      group: "Transitions",
      label: "Transition type",
      control: "select",
      options: ["crossfade", "fade_to_black"]
    }
  },
  "localization.dub": {
    provider_id: { group: "Provider", label: "TTS provider", optionsSource: "providers:tts" },
  },
  "shorts.render": {
    second_source_path: {
      group: "Layout",
      label: "Second source",
      placeholder: "/path/to/second-angle.mp4"
    }
  },
  "broll.plan": {
    asset_dir: {
      group: "B-roll",
      label: "Asset directory",
      placeholder: "/path/to/broll"
    }
  },
  "retakes.cull": {
    enabled: { group: "Retakes", label: "Remove retakes" },
    strategy: { group: "Retakes", label: "Strategy" },
    strictness: { group: "Retakes", label: "Strictness" },
    context_window: { group: "Retakes", label: "Context window" },
    manual_overrides: { group: "Advanced", label: "Manual overrides" }
  },
  "export.nle": {
    targets: { group: "Export", label: "Outputs" },
    dialect: { group: "Export", label: "FCPXML dialect" },
    subdir: { group: "Export", label: "Subdirectory" }
  },
  transcribe: {
    mode: { group: "Transcription", label: "Mode" },
    language: { group: "Transcription", label: "Language" },
    model_size: { group: "Transcription", label: "Model" },
    provider_id: { group: "Provider", label: "Configured provider", optionsSource: "providers:asr" },
    engine: { group: "Transcription", label: "Engine" },
    device: { group: "Transcription", label: "Device" },
    compute_type: { group: "Transcription", label: "Compute" },
    vad_filter: { group: "Transcription", label: "VAD filter" }
  }
};

const PRESETS: Record<string, Array<{ label: string; patch: Record<string, unknown> }>> = {
  "audio.vad": [
    {
      label: "Gentle",
      patch: {
        noise_db: -38,
        speech_threshold: 0.4,
        min_silence_ms: 550,
        min_speech_ms: 150,
        spike_suppression_ms: 260,
        merge_gap_ms: 180,
        pad_before_ms: 140,
        pad_after_ms: 200
      }
    },
    {
      label: "Balanced",
      patch: {
        noise_db: -30,
        speech_threshold: 0.5,
        min_silence_ms: 350,
        min_speech_ms: 120,
        spike_suppression_ms: 180,
        merge_gap_ms: 120,
        pad_before_ms: 80,
        pad_after_ms: 120
      }
    },
    {
      label: "Aggressive",
      patch: {
        noise_db: -24,
        speech_threshold: 0.62,
        min_silence_ms: 240,
        min_speech_ms: 90,
        spike_suppression_ms: 120,
        merge_gap_ms: 70,
        pad_before_ms: 40,
        pad_after_ms: 60
      }
    },
    {
      label: "Tight",
      patch: {
        noise_db: -20,
        speech_threshold: 0.7,
        min_silence_ms: 180,
        min_speech_ms: 70,
        spike_suppression_ms: 90,
        merge_gap_ms: 40,
        pad_before_ms: 20,
        pad_after_ms: 30
      }
    }
  ],
  "edit.timeline": [
    { label: "Hard cut", patch: { cut_mode: "hard", enable_j_cuts: false, enable_l_cuts: false } },
    { label: "J-cut", patch: { cut_mode: "j_cut", enable_j_cuts: true, enable_l_cuts: false } },
    { label: "L-cut", patch: { cut_mode: "l_cut", enable_j_cuts: false, enable_l_cuts: true } },
    {
      label: "Custom",
      patch: { cut_mode: "custom" }
    }
  ],
  "retakes.cull": [
    { label: "Conservative", patch: { strictness: "conservative", strategy: "keep_best" } },
    { label: "Balanced", patch: { strictness: "balanced", strategy: "keep_last" } },
    { label: "Aggressive", patch: { strictness: "aggressive", strategy: "keep_last" } }
  ]
};

function resolve(schema: Schema, root: Schema): Schema {
  const ref = schema.$ref;
  if (typeof ref === "string" && ref.startsWith("#/")) {
    let current: unknown = root;
    for (const part of ref.slice(2).split("/")) {
      current = (current as Record<string, unknown> | undefined)?.[part];
    }
    if (current && typeof current === "object") return current as Schema;
  }
  const variants = schema.anyOf ?? schema.oneOf;
  if (Array.isArray(variants)) {
    const nonNull = variants.find((item) => {
      if (!item || typeof item !== "object") return false;
      return (item as Schema).type !== "null";
    });
    if (nonNull && typeof nonNull === "object") {
      return resolve({ ...schema, ...(nonNull as Schema), anyOf: undefined, oneOf: undefined }, root);
    }
  }
  return schema;
}

export function getPath(source: unknown, path: string[]): unknown {
  let current: unknown = source;
  for (const key of path) {
    if (!current || typeof current !== "object") return undefined;
    current = (current as Record<string, unknown>)[key];
  }
  return current;
}

export function setPath(source: Record<string, unknown>, path: string[], value: unknown): Record<string, unknown> {
  if (path.length === 0) return source;
  const [head, ...rest] = path;
  const current = source[head];
  if (rest.length === 0) return { ...source, [head]: value };
  const child = current && typeof current === "object" && !Array.isArray(current)
    ? { ...(current as Record<string, unknown>) }
    : {};
  return { ...source, [head]: setPath(child, rest, value) };
}

export function humanize(key: string): string {
  return key
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function kindFor(key: string, schema: Schema, resolved: Schema): RecipeFieldKind {
  const type = resolved.type;
  const enumValues = resolved.enum;
  if (type === "boolean") return "boolean";
  if (type === "number" || type === "integer") return "number";
  if (Array.isArray(enumValues) && enumValues.length) return "enum";
  if (/(^|_)color$/i.test(key)) return "color";
  if (/(_path|_dir|^path|^file)$/i.test(key)) return "path";
  return "text";
}

function controlFor(
  kind: RecipeFieldKind,
  resolved: Schema,
  minimum: number | undefined,
  maximum: number | undefined,
  itemOptions: string[],
  meta: FieldMeta
): RecipeControl {
  if (meta.optionsSource) return "select";
  if (meta.control) return meta.control;
  const schemaControl = resolved["x-control"];
  if (typeof schemaControl === "string") return schemaControl as RecipeControl;
  if (kind === "boolean") return "switch";
  if (kind === "enum") {
    const count = Array.isArray(resolved.enum) ? resolved.enum.length : 0;
    return count > 0 && count <= 4 ? "segmented" : "select";
  }
  if (kind === "number" && minimum !== undefined && maximum !== undefined) {
    return maximum - minimum <= 10_000 ? "slider" : "number";
  }
  if (kind === "number") return "number";
  if (kind === "json" && itemOptions.length) return "chips";
  if (resolved.type === "array") {
    const items = resolved.items as Schema | undefined;
    if (items && (items.type === "string" || Array.isArray(items.enum))) return "chips";
  }
  if (kind === "path") return "path";
  if (kind === "color") return "color";
  return kind === "json" ? "json" : "text";
}

function buildField(
  key: string,
  schema: Schema,
  root: Schema,
  params: unknown,
  path: string[],
  required: boolean,
  stepType: string
): RecipeField | null {
  const resolved = resolve(schema, root);
  const type = resolved.type;
  if (type === "object") return null;
  const meta = FIELD_META[stepType]?.[key] ?? {};
  const enumValues = Array.isArray(resolved.enum)
    ? resolved.enum.map((value) => String(value))
    : (meta.options ?? []);
  const itemSchema = resolved.items as Schema | undefined;
  const itemOptions = Array.isArray(itemSchema?.enum)
    ? itemSchema.enum.map((value) => String(value))
    : [];
  const kind = kindFor(key, schema, resolved);
  const minimum = typeof resolved.minimum === "number" ? resolved.minimum : undefined;
  const maximum = typeof resolved.maximum === "number" ? resolved.maximum : undefined;
  const description = typeof resolved.description === "string" ? resolved.description : "";
  const defaultValue = resolved.default;
  return {
    path,
    id: path.join("."),
    label: meta.label ?? (typeof resolved.title === "string" ? resolved.title : humanize(key)),
    kind,
    control: controlFor(kind, resolved, minimum, maximum, itemOptions, meta),
    group: meta.group ?? String(resolved["x-group"] ?? "Parameters"),
    unit: meta.unit ?? String(resolved["x-unit"] ?? ""),
    options: enumValues,
    optionsSource: meta.optionsSource ?? "",
    itemOptions,
    minimum,
    maximum,
    step: meta.step ?? (type === "integer" ? 1 : undefined),
    integer: type === "integer",
    required,
    format: typeof resolved.format === "string" ? resolved.format : "",
    pattern: typeof resolved.pattern === "string" ? resolved.pattern : "",
    placeholder:
      meta.placeholder ??
      (typeof resolved["x-placeholder"] === "string"
        ? resolved["x-placeholder"]
        : description || (kind === "path" ? "/path/to/file" : "")),
    help: description,
    value: getPath(params, path) ?? defaultValue,
    defaultValue
  };
}

export function fieldGroups(
  schema: unknown,
  params: unknown,
  stepType = ""
): RecipeFieldGroup[] {
  const root = (schema ?? {}) as Schema;
  const properties = (root.properties ?? {}) as Record<string, Schema>;
  const required = new Set(Array.isArray(root.required) ? root.required.map(String) : []);
  const groups: RecipeFieldGroup[] = [];
  const rootGroups = new Map<string, RecipeFieldGroup>();
  for (const [key, raw] of Object.entries(properties)) {
    if (stepType === "ingest" && key === "source") continue;
    const resolved = resolve(raw, root);
    if (resolved.type === "object") {
      const nestedProperties = (resolved.properties ?? {}) as Record<string, Schema>;
      if (!Object.keys(nestedProperties).length) continue;
      const nestedRequired = new Set(
        Array.isArray(resolved.required) ? resolved.required.map(String) : []
      );
      const nested: RecipeFieldGroup = {
        path: [key],
        label: typeof resolved.title === "string" ? resolved.title : humanize(key),
        fields: []
      };
      for (const [childKey, childSchema] of Object.entries(nestedProperties)) {
        const field = buildField(
          childKey,
          childSchema,
          root,
          params,
          [key, childKey],
          nestedRequired.has(childKey),
          stepType
        );
        if (field) nested.fields.push(field);
      }
      if (nested.fields.length) groups.push(nested);
      continue;
    }
    const field = buildField(key, raw, root, params, [key], required.has(key), stepType);
    if (!field) continue;
    const group = rootGroups.get(field.group) ?? {
      path: [],
      label: field.group,
      fields: []
    };
    group.fields.push(field);
    rootGroups.set(field.group, group);
  }
  groups.unshift(...rootGroups.values());
  return groups;
}

export function nodePresets(
  stepType: string
): Array<{ label: string; patch: Record<string, unknown> }> {
  return PRESETS[stepType] ?? [];
}

export function validateField(field: RecipeField): string | null {
  const value = field.value;
  if (field.required && (value === undefined || value === null || value === "")) {
    return "Required";
  }
  if (value === undefined || value === null || value === "") return null;
  if (field.control === "chips") {
    if (!Array.isArray(value)) return "Choose one or more values";
    return null;
  }
  if (field.kind === "enum" && !field.options.includes(String(value))) {
    return `Choose one of: ${field.options.join(", ")}`;
  }
  if (field.kind === "number") {
    const number = Number(value);
    if (!Number.isFinite(number)) return "Enter a number";
    if (field.integer && !Number.isInteger(number)) return "Enter an integer";
    if (field.minimum !== undefined && number < field.minimum) {
      return `Minimum ${field.minimum}`;
    }
    if (field.maximum !== undefined && number > field.maximum) {
      return `Maximum ${field.maximum}`;
    }
  }
  if (field.kind === "color" && !/^#[0-9a-f]{6}$/i.test(String(value))) {
    return "Use #RRGGBB";
  }
  if (field.format === "uri" || /(^|_)url$/i.test(field.id)) {
    try {
      const parsed = new URL(String(value));
      if (!["http:", "https:"].includes(parsed.protocol)) return "Use http:// or https://";
    } catch {
      return "Invalid URL";
    }
  }
  if (field.pattern) {
    try {
      if (!new RegExp(field.pattern).test(String(value))) return "Invalid format";
    } catch {
      // Ignore an invalid server-provided pattern.
    }
  }
  return null;
}

export function validateParams(
  schema: unknown,
  params: unknown,
  stepType = ""
): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const group of fieldGroups(schema, params, stepType)) {
    for (const field of group.fields) {
      const error = validateField(field);
      if (error) errors[field.id] = error;
    }
  }
  return errors;
}
