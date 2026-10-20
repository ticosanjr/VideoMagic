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
  | "vad_engine"
  | "noise_db"
  | "min_silence_ms"
  | "min_speech_ms"
  | "speech_threshold"
  | "speech_pad_before_ms"
  | "speech_pad_after_ms"
  | "transcribe"
  | "asr_base_url"
  | "asr_model"
  | "asr_language"
  | "whisper_engine"
  | "whisper_model_size"
  | "whisper_device"
  | "whisper_compute_type"
  | "whisper_vad_filter"
  | "whisper_model"
  | "faster_whisper_model"
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
  vad_engine: "auto",
  noise_db: -30,
  min_silence_ms: 400,
  min_speech_ms: 100,
  speech_threshold: 0.5,
  speech_pad_before_ms: 120,
  speech_pad_after_ms: 150,
  transcribe: false,
  asr_base_url: "",
  asr_model: "whisper-1",
  asr_language: "pt",
  whisper_engine: "auto",
  whisper_model_size: "small",
  whisper_device: "cpu",
  whisper_compute_type: "int8",
  whisper_vad_filter: false,
  whisper_model: "",
  faster_whisper_model: "",
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
        key: "vad_engine",
        label: "Engine",
        type: "select",
        implemented: true,
        options: [
          { value: "auto", label: "Auto (Silero, then FFmpeg)" },
          { value: "silero", label: "Silero (quality)" },
          { value: "ffmpeg", label: "FFmpeg (portable)" }
        ],
        help: "Auto uses the bundled Silero model when ONNX Runtime is available."
      },
      {
        key: "speech_threshold",
        label: "Speech probability",
        type: "number",
        implemented: true,
        min: 0.1,
        max: 0.9,
        step: 0.05,
        help: "Silero threshold; ignored by the FFmpeg fallback."
      },
      {
        key: "speech_pad_before_ms",
        label: "Pad before (ms)",
        type: "number",
        implemented: true,
        min: 0,
        max: 2000,
        step: 10
      },
      {
        key: "speech_pad_after_ms",
        label: "Pad after (ms)",
        type: "number",
        implemented: true,
        min: 0,
        max: 2000,
        step: 10
      },
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
    summary: "Import an SRT, run local Faster-Whisper or whisper.cpp, or call an ASR endpoint.",
    portable: true,
    tag: "SRT/Local/ASR",
    toggleKey: "transcribe",
    toggleLabel: "Local/ASR",
    note: "An SRT in the run panel wins. Local auto prefers Faster-Whisper when its package and model are available, then falls back to whisper.cpp. An ASR base URL takes precedence; the key stays in VIDEOWFLOW_ASR_API_KEY.",
    fields: [
      {
        key: "whisper_engine",
        label: "Local engine",
        type: "select",
        implemented: true,
        options: [
          { value: "auto", label: "Auto (Faster-Whisper, then whisper.cpp)" },
          { value: "faster-whisper", label: "Faster-Whisper (quality)" },
          { value: "whisper.cpp", label: "whisper.cpp (portable)" }
        ],
        help: "An explicit engine fails with an actionable hint instead of silently downgrading."
      },
      {
        key: "whisper_model_size",
        label: "Model size",
        type: "select",
        implemented: true,
        options: ["tiny", "base", "small", "medium", "large-v3"].map((value) => ({
          value,
          label: value
        })),
        help: "Faster-Whisper CTranslate2 model. The release bundles small."
      },
      {
        key: "faster_whisper_model",
        label: "Faster-Whisper model",
        type: "text",
        implemented: true,
        help: "Optional CTranslate2 model directory. Empty uses the bundled model for the selected size."
      },
      {
        key: "whisper_device",
        label: "Device",
        type: "select",
        implemented: true,
        options: [
          { value: "cpu", label: "CPU (default)" },
          { value: "cuda", label: "CUDA" }
        ]
      },
      {
        key: "whisper_compute_type",
        label: "Compute type",
        type: "select",
        implemented: true,
        options: ["int8", "float16", "float32"].map((value) => ({ value, label: value })),
        help: "CPU defaults to int8. float16 is intended for CUDA."
      },
      {
        key: "whisper_vad_filter",
        label: "Whisper VAD",
        type: "bool",
        implemented: true,
        help: "Keep off when module 02 is enabled; the full WAV is always transcribed."
      },
      {
        key: "asr_base_url",
        label: "ASR base URL",
        type: "text",
        implemented: true,
        help: "Empty runs a local engine; VIDEOWFLOW_ASR_BASE_URL is the fallback."
      },
      { key: "asr_model", label: "ASR model", type: "text", implemented: true },
      {
        key: "asr_language",
        label: "Language",
        type: "select",
        implemented: true,
        options: ["pt", "it", "en", "es", "auto"].map((value) => ({ value, label: value }))
      },
      {
        key: "whisper_model",
        label: "GGML model",
        type: "text",
        implemented: true,
        help: "whisper.cpp model. Empty uses the bundled tiny model."
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
    summary: "Write FCPXML, xmeml, and native Kdenlive MLT from one validated timeline.",
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
