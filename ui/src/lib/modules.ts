export type Status =
  | "pending"
  | "cached"
  | "dirty"
  | "running"
  | "bypassed"
  | "failed"
  | "blocked"
  | "cancelled"
  | "succeeded";

export type FieldType = "number" | "bool" | "select" | "text" | "targets" | "readonly";

export type ConfigKey =
  | "force_cfr"
  | "extract_pcm"
  | "proxy"
  | "noise_db"
  | "min_silence_ms"
  | "min_speech_ms"
  | "model"
  | "language"
  | "device"
  | "cull_retakes"
  | "strictness"
  | "retake_strategy"
  | "context_window"
  | "llm_base_url"
  | "llm_model"
  | "shorts"
  | "jcut"
  | "lcut"
  | "offset_ms"
  | "crossfade_ms"
  | "handle_check"
  | "zooms"
  | "zoom_mode"
  | "punch_in_scale"
  | "anchor_point"
  | "progressive_zoom"
  | "pan_direction"
  | "shorts_count"
  | "shorts_min_sec"
  | "shorts_max_sec"
  | "shorts_subtitles"
  | "dialect"
  | "export_targets";

export type ConfigValue = string | number | boolean | string[];
export type JobConfig = Record<ConfigKey, ConfigValue>;

export interface ModuleField {
  key: ConfigKey;
  label: string;
  type: FieldType;
  implemented: boolean;
  min?: number;
  max?: number;
  step?: number;
  options?: { value: string; label: string }[];
  help?: string;
}

export interface RackModule {
  index: string;
  id: string;
  name: string;
  summary: string;
  portable: boolean;
  tag?: string;
  note?: string;
  toggleKey?: ConfigKey;
  toggleLabel?: string;
  fields: ModuleField[];
}

export const defaultConfig: JobConfig = {
  force_cfr: true,
  extract_pcm: true,
  proxy: false,
  noise_db: -30,
  min_silence_ms: 400,
  min_speech_ms: 100,
  model: "small",
  language: "pt",
  device: "cpu",
  cull_retakes: false,
  strictness: "balanced",
  retake_strategy: "keep_last",
  context_window: 15,
  llm_base_url: "",
  llm_model: "qwen2.5:7b-instruct",
  shorts: false,
  jcut: true,
  lcut: false,
  offset_ms: 200,
  crossfade_ms: 20,
  handle_check: true,
  zooms: true,
  zoom_mode: "alternate_cuts",
  punch_in_scale: 1.15,
  anchor_point: "upper_third",
  progressive_zoom: false,
  pan_direction: "none",
  shorts_count: 3,
  shorts_min_sec: 30,
  shorts_max_sec: 60,
  shorts_subtitles: true,
  dialect: "1.9",
  export_targets: ["resolve", "premiere", "kdenlive"]
};

export const modules: RackModule[] = [
  {
    index: "01",
    id: "ingest",
    name: "Ingest",
    summary: "Validate the container, extract analysis audio, and fingerprint the PCM.",
    portable: true,
    note: "CFR normalisation and proxies are planned; the portable build probes and extracts PCM.",
    fields: [
      { key: "force_cfr", label: "Force CFR", type: "bool", implemented: false },
      { key: "extract_pcm", label: "Extract PCM", type: "bool", implemented: false },
      { key: "proxy", label: "Generate proxy", type: "bool", implemented: false }
    ]
  },
  {
    index: "02",
    id: "vad",
    name: "Voice detect",
    summary: "Find speech and remove silence with a protected minimum speech length.",
    portable: true,
    fields: [
      {
        key: "noise_db",
        label: "Noise floor (dB)",
        type: "number",
        implemented: true,
        min: -80,
        max: -5,
        step: 1
      },
      {
        key: "min_silence_ms",
        label: "Minimum silence (ms)",
        type: "number",
        implemented: true,
        min: 100,
        max: 5000,
        step: 50
      },
      {
        key: "min_speech_ms",
        label: "Minimum speech (ms)",
        type: "number",
        implemented: true,
        min: 0,
        max: 2000,
        step: 50,
        help: "Drops codec blips shorter than this."
      }
    ]
  },
  {
    index: "03",
    id: "transcribe",
    name: "Transcribe",
    summary: "Word-level timestamps from Faster-Whisper, or an imported SRT.",
    portable: true,
    tag: "SRT",
    note: "Built-in transcription is not in this build. Provide an SRT in the run panel; it is imported as a transcript.",
    fields: [
      {
        key: "model",
        label: "Model",
        type: "select",
        implemented: false,
        options: ["tiny", "base", "small", "medium", "large-v3"].map((value) => ({
          value,
          label: value
        }))
      },
      {
        key: "language",
        label: "Language",
        type: "select",
        implemented: false,
        options: ["pt", "it", "en", "es", "auto"].map((value) => ({ value, label: value }))
      },
      {
        key: "device",
        label: "Device",
        type: "select",
        implemented: false,
        options: [
          { value: "cpu", label: "CPU / int8" },
          { value: "cuda", label: "CUDA / float16" }
        ]
      }
    ]
  },
  {
    index: "04",
    id: "retakes",
    name: "Retakes",
    summary: "Cull failed takes while guarding the final attempt.",
    portable: true,
    tag: "SRT",
    toggleKey: "cull_retakes",
    toggleLabel: "Cull",
    note: "Needs an SRT or an API transcript. The LLM key stays in VIDEOWFLOW_LLM_API_KEY.",
    fields: [
      {
        key: "strictness",
        label: "Strictness",
        type: "select",
        implemented: true,
        options: ["conservative", "balanced", "aggressive"].map((value) => ({
          value,
          label: value
        }))
      },
      {
        key: "retake_strategy",
        label: "Strategy",
        type: "select",
        implemented: true,
        options: [
          { value: "keep_last", label: "Keep last (safe)" },
          { value: "keep_best", label: "Keep best" }
        ]
      },
      {
        key: "context_window",
        label: "Context window",
        type: "number",
        implemented: true,
        min: 1,
        max: 100,
        step: 1,
        help: "Sentences per LLM request."
      },
      {
        key: "llm_base_url",
        label: "LLM base URL",
        type: "text",
        implemented: true,
        help: "Empty uses exact-repeat culling only."
      },
      { key: "llm_model", label: "LLM model", type: "text", implemented: true }
    ]
  },
  {
    index: "05",
    id: "jl_cuts",
    name: "J/L cuts",
    summary: "Offset audio at joins and add logarithmic micro-fades.",
    portable: true,
    toggleKey: "jcut",
    toggleLabel: "J-cuts",
    fields: [
      { key: "jcut", label: "J-cuts", type: "bool", implemented: true },
      { key: "lcut", label: "L-cuts", type: "bool", implemented: true },
      {
        key: "offset_ms",
        label: "Offset (ms)",
        type: "number",
        implemented: true,
        min: 100,
        max: 500,
        step: 10
      },
      {
        key: "crossfade_ms",
        label: "Crossfade (ms)",
        type: "number",
        implemented: true,
        min: 10,
        max: 50,
        step: 5
      },
      { key: "handle_check", label: "Handle check", type: "bool", implemented: true }
    ]
  },
  {
    index: "06",
    id: "zooms",
    name: "Zooms",
    summary: "Alternate punch-ins and optional pan to hide jump cuts.",
    portable: true,
    toggleKey: "zooms",
    toggleLabel: "Enabled",
    fields: [
      {
        key: "zoom_mode",
        label: "Mode",
        type: "select",
        implemented: true,
        options: [
          { value: "alternate_cuts", label: "Alternate cuts" },
          { value: "manual_rules", label: "Manual / neutral" }
        ]
      },
      {
        key: "punch_in_scale",
        label: "Punch-in scale",
        type: "number",
        implemented: true,
        min: 1.05,
        max: 1.3,
        step: 0.01
      },
      {
        key: "anchor_point",
        label: "Anchor",
        type: "select",
        implemented: true,
        options: [
          { value: "center", label: "Center" },
          { value: "upper_third", label: "Upper third" },
          { value: "face_detect", label: "Face detect (fallback)" }
        ]
      },
      { key: "progressive_zoom", label: "Progressive zoom", type: "bool", implemented: true },
      {
        key: "pan_direction",
        label: "Pan",
        type: "select",
        implemented: true,
        options: [
          { value: "none", label: "None" },
          { value: "left_to_right", label: "Left to right" },
          { value: "right_to_left", label: "Right to left" }
        ]
      }
    ]
  },
  {
    index: "07",
    id: "shorts",
    name: "Shorts",
    summary: "Select and render vertical 1080x1920 clips with captions.",
    portable: true,
    tag: "SRT",
    toggleKey: "shorts",
    toggleLabel: "Render",
    note: "Requires an SRT transcript. Each clip is rendered to output/shorts as H.264/MP4.",
    fields: [
      {
        key: "shorts_count",
        label: "Count",
        type: "number",
        implemented: true,
        min: 1,
        max: 20,
        step: 1
      },
      {
        key: "shorts_min_sec",
        label: "Minimum seconds",
        type: "number",
        implemented: true,
        min: 1,
        max: 300,
        step: 1
      },
      {
        key: "shorts_max_sec",
        label: "Maximum seconds",
        type: "number",
        implemented: true,
        min: 1,
        max: 600,
        step: 1
      },
      { key: "shorts_subtitles", label: "Burn captions", type: "bool", implemented: true }
    ]
  },
  {
    index: "08",
    id: "export",
    name: "Export",
    summary: "Write FCPXML, xmeml, and OTIO from one validated timeline.",
    portable: true,
    fields: [
      {
        key: "dialect",
        label: "FCPXML dialect",
        type: "select",
        implemented: true,
        options: [
          { value: "1.9", label: "1.9 (Resolve default)" },
          { value: "1.10", label: "1.10" }
        ]
      },
      { key: "export_targets", label: "Targets", type: "targets", implemented: true }
    ]
  }
];

export const statusStyles: Record<Status, string> = {
  pending: "bg-neutral-600/20 text-neutral-400 ring-neutral-600/40",
  cached: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  dirty: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
  running: "bg-sky-500/15 text-sky-300 ring-sky-500/30",
  bypassed: "bg-neutral-600/20 text-neutral-400 ring-neutral-600/40",
  failed: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
  blocked: "bg-orange-500/15 text-orange-300 ring-orange-500/30",
  cancelled: "bg-neutral-600/20 text-neutral-400 ring-neutral-600/40",
  succeeded: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30"
};

export const statusLabel: Record<Status, string> = {
  pending: "pending",
  cached: "cached",
  dirty: "dirty",
  running: "running",
  bypassed: "bypassed",
  failed: "failed",
  blocked: "blocked",
  cancelled: "cancelled",
  succeeded: "succeeded"
};
