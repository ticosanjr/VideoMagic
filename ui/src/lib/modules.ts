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

export type FieldType =
  | "number"
  | "bool"
  | "select"
  | "text"
  | "textarea"
  | "color"
  | "targets"
  | "readonly";

export type ModuleTab =
  | "speech"
  | "edit"
  | "shorts"
  | "studio"
  | "export"
  | "models"
  | "services"
  | "providers";

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
  | "fade_in_ms"
  | "fade_out_ms"
  | "fade_curve"
  | "handle_check"
  | "zooms"
  | "zoom_mode"
  | "zoom_min_scale"
  | "zoom_max_scale"
  | "punch_in_scale"
  | "anchor_point"
  | "progressive_zoom"
  | "pan_direction"
  | "shorts_count"
  | "shorts_min_count"
  | "shorts_min_sec"
  | "shorts_max_sec"
  | "shorts_subtitles"
  | "shorts_selection_mode"
  | "shorts_prompt"
  | "shorts_reprompt"
  | "shorts_prompt_mode"
  | "shorts_hook_mode"
  | "shorts_reframe_mode"
  | "shorts_audio_energy_boost"
  | "shorts_scene_change_boost"
  | "shorts_remove_fillers"
  | "shorts_filler_words"
  | "audio_enhance"
  | "audio_highpass_hz"
  | "audio_denoise"
  | "audio_denoise_db"
  | "audio_noise_floor_db"
  | "audio_loudnorm"
  | "audio_target_lufs"
  | "audio_true_peak_db"
  | "overlay_enabled"
  | "overlay_asset"
  | "overlay_position"
  | "overlay_margin_px"
  | "overlay_width_ratio"
  | "overlay_opacity"
  | "music_enabled"
  | "music_asset"
  | "music_volume"
  | "music_ducking"
  | "music_fade_in_ms"
  | "music_fade_out_ms"
  | "intro_enabled"
  | "intro_asset"
  | "intro_duration_sec"
  | "outro_enabled"
  | "outro_asset"
  | "outro_duration_sec"
  | "shorts_aspect"
  | "shorts_resolution"
  | "shorts_source_start_sec"
  | "shorts_source_end_sec"
  | "allow_external_services"
  | "allowed_external_hosts"
  | "caption_font_family"
  | "caption_font_size"
  | "caption_font_weight"
  | "caption_italic"
  | "caption_uppercase"
  | "caption_primary_color"
  | "caption_highlight_color"
  | "caption_outline_color"
  | "caption_outline_width"
  | "caption_shadow_color"
  | "caption_shadow_offset"
  | "caption_shadow_opacity"
  | "caption_background_color"
  | "caption_background_opacity"
  | "caption_background_padding"
  | "caption_alignment"
  | "caption_position_x"
  | "caption_position_y"
  | "caption_max_width"
  | "caption_animation"
  | "caption_word_timing"
  | "caption_censor_enabled"
  | "caption_censor_words"
  | "caption_censor_replacement"
  | "caption_keyword_highlight_enabled"
  | "caption_keyword_color"
  | "caption_keyword_words"
  | "caption_emoji_enabled"
  | "caption_emoji_map"
  | "caption_brand_vocabulary"
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
  tab: ModuleTab;
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
  fade_in_ms: 20,
  fade_out_ms: 20,
  fade_curve: "logarithmic",
  handle_check: true,
  zooms: true,
  zoom_mode: "alternate_cuts",
  zoom_min_scale: 1.0,
  zoom_max_scale: 1.5,
  punch_in_scale: 1.15,
  anchor_point: "upper_third",
  progressive_zoom: false,
  pan_direction: "none",
  shorts_count: 3,
  shorts_min_count: 3,
  shorts_min_sec: 30,
  shorts_max_sec: 60,
  shorts_subtitles: true,
  shorts_selection_mode: "auto",
  shorts_prompt: "",
  shorts_reprompt: "",
  shorts_prompt_mode: "replace",
  shorts_hook_mode: "off",
  shorts_reframe_mode: "center_crop_9_16",
  shorts_audio_energy_boost: false,
  shorts_scene_change_boost: false,
  shorts_remove_fillers: false,
  shorts_filler_words: "hum, hmm, uh, um, ah, eh, erm, er",
  audio_enhance: false,
  audio_highpass_hz: 80,
  audio_denoise: true,
  audio_denoise_db: 12,
  audio_noise_floor_db: -30,
  audio_loudnorm: true,
  audio_target_lufs: -16,
  audio_true_peak_db: -1.5,
  overlay_enabled: false,
  overlay_asset: "",
  overlay_position: "bottom_right",
  overlay_margin_px: 32,
  overlay_width_ratio: 0.18,
  overlay_opacity: 0.9,
  music_enabled: false,
  music_asset: "",
  music_volume: 0.18,
  music_ducking: true,
  music_fade_in_ms: 250,
  music_fade_out_ms: 500,
  intro_enabled: false,
  intro_asset: "",
  intro_duration_sec: 2,
  outro_enabled: false,
  outro_asset: "",
  outro_duration_sec: 2,
  shorts_aspect: "9:16",
  shorts_resolution: 1080,
  shorts_source_start_sec: 0,
  shorts_source_end_sec: 0,
  allow_external_services: false,
  allowed_external_hosts: "",
  caption_font_family: "Arial",
  caption_font_size: 72,
  caption_font_weight: "bold",
  caption_italic: false,
  caption_uppercase: false,
  caption_primary_color: "#FFFFFF",
  caption_highlight_color: "#FFD400",
  caption_outline_color: "#000000",
  caption_outline_width: 4,
  caption_shadow_color: "#000000",
  caption_shadow_offset: 2,
  caption_shadow_opacity: 0.6,
  caption_background_color: "#000000",
  caption_background_opacity: 0,
  caption_background_padding: 0,
  caption_alignment: 2,
  caption_position_x: 0.5,
  caption_position_y: 0.78,
  caption_max_width: 0.9,
  caption_animation: "none",
  caption_word_timing: "engine",
  caption_censor_enabled: false,
  caption_censor_words: "porra, merda, caralho, foda, fuck, shit, bitch, asshole",
  caption_censor_replacement: "***",
  caption_keyword_highlight_enabled: false,
  caption_keyword_color: "#00E5FF",
  caption_keyword_words: "",
  caption_emoji_enabled: false,
  caption_emoji_map: "money=💰, idea=💡, warning=⚠️, fire=🔥, growth=📈",
  caption_brand_vocabulary: "",
  dialect: "1.9",
  export_targets: ["resolve", "premiere", "kdenlive"]
};

export const moduleTabs: { id: ModuleTab; label: string; hint: string }[] = [
  { id: "speech", label: "Speech", hint: "Ingest, voice detection, transcription, and retakes" },
  { id: "edit", label: "Edit", hint: "J/L cuts, fades, and framing" },
  { id: "shorts", label: "Shorts", hint: "Curation, captions, aspect ratio, and render" },
  { id: "studio", label: "Studio", hint: "AI analysis, timeline, keyframes, tracks, and transitions" },
  { id: "export", label: "Export", hint: "NLE targets and FCPXML dialect" },
  { id: "models", label: "Models", hint: "Optional on-demand speech and vision models" },
  { id: "services", label: "Services", hint: "Inspect, stop, and restart local VideoFlow processes" },
  { id: "providers", label: "Providers", hint: "Local models and optional external services" }
];

export const modules: RackModule[] = [
  {
    index: "01",
    id: "ingest",
    tab: "speech",
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
    tab: "speech",
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
    tab: "speech",
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
        options: [
          ["auto", "Auto-detect"],
          ["pt", "Portuguese"],
          ["en", "English"],
          ["es", "Spanish"],
          ["it", "Italian"],
          ["fr", "French"],
          ["de", "German"],
          ["nl", "Dutch"],
          ["sv", "Swedish"],
          ["no", "Norwegian"],
          ["da", "Danish"],
          ["fi", "Finnish"],
          ["pl", "Polish"],
          ["cs", "Czech"],
          ["ro", "Romanian"],
          ["hu", "Hungarian"],
          ["el", "Greek"],
          ["tr", "Turkish"],
          ["ru", "Russian"],
          ["uk", "Ukrainian"],
          ["ar", "Arabic"],
          ["he", "Hebrew"],
          ["hi", "Hindi"],
          ["ja", "Japanese"],
          ["ko", "Korean"],
          ["zh", "Chinese"],
          ["th", "Thai"],
          ["vi", "Vietnamese"],
          ["id", "Indonesian"],
          ["ms", "Malay"]
        ].map(([value, label]) => ({ value, label }))
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
    tab: "speech",
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
    tab: "edit",
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
      {
        key: "fade_in_ms",
        label: "Fade in (ms)",
        type: "number",
        implemented: true,
        min: 0,
        max: 1000,
        step: 10
      },
      {
        key: "fade_out_ms",
        label: "Fade out (ms)",
        type: "number",
        implemented: true,
        min: 0,
        max: 1000,
        step: 10
      },
      {
        key: "fade_curve",
        label: "Fade curve",
        type: "select",
        implemented: true,
        options: [
          { value: "logarithmic", label: "Logarithmic" },
          { value: "linear", label: "Linear" }
        ]
      },
      { key: "handle_check", label: "Handle check", type: "bool", implemented: true }
    ]
  },
  {
    index: "06",
    id: "zooms",
    tab: "edit",
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
        key: "zoom_min_scale",
        label: "Minimum scale",
        type: "number",
        implemented: true,
        min: 1.0,
        max: 4.0,
        step: 0.01
      },
      {
        key: "zoom_max_scale",
        label: "Maximum scale",
        type: "number",
        implemented: true,
        min: 1.0,
        max: 4.0,
        step: 0.01
      },
      {
        key: "punch_in_scale",
        label: "Punch-in scale",
        type: "number",
        implemented: true,
        min: 1.0,
        max: 4.0,
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
    tab: "shorts",
    name: "Shorts",
    summary: "Select and render social clips with captions in 9:16, 1:1, or 16:9.",
    portable: true,
    tag: "SRT",
    toggleKey: "shorts",
    toggleLabel: "Render",
    note: "Needs a transcript (SRT, local, or ASR). Adds vertical MP4s under output/shorts without replacing the main project.",
    fields: [
      {
        key: "shorts_count",
        label: "Target count",
        type: "number",
        implemented: true,
        min: 1,
        max: 20,
        step: 1
      },
      {
        key: "shorts_min_count",
        label: "Minimum clips",
        type: "number",
        implemented: true,
        min: 1,
        max: 20,
        step: 1
      },
      {
        key: "shorts_selection_mode",
        label: "Selection",
        type: "select",
        implemented: true,
        options: [
          { value: "auto", label: "Auto (LLM, then heuristic)" },
          { value: "llm", label: "LLM ranking" },
          { value: "heuristic", label: "Heuristic ranking" }
        ]
      },
      {
        key: "shorts_prompt",
        label: "Prompt / topic",
        type: "textarea",
        implemented: true,
        help: "Optional focus for selection, e.g. 'the part about pricing and margins'."
      },
      {
        key: "shorts_reprompt",
        label: "Reprompt",
        type: "textarea",
        implemented: true,
        help: "Refinement instruction used with prompt_mode=refine."
      },
      {
        key: "shorts_prompt_mode",
        label: "Prompt mode",
        type: "select",
        implemented: true,
        options: [
          { value: "replace", label: "Replace selection" },
          { value: "refine", label: "Refine previous selection" }
        ],
        help: "Refine loads the previous shorts.json from the output folder."
      },
      {
        key: "shorts_reframe_mode",
        label: "Reframe mode",
        type: "select",
        implemented: true,
        options: [
          { value: "center_crop_9_16", label: "Center crop" },
          { value: "motion_tracking", label: "Motion tracking" },
          { value: "face_tracking", label: "Face tracking (optional OpenCV)" }
        ],
        help: "Motion tracking uses low-resolution frame differences. Face tracking requires opencv-python-headless."
      },
      {
        key: "shorts_audio_energy_boost",
        label: "Boost audio-energy peaks",
        type: "bool",
        implemented: true,
        help: "Adds a score bonus to clips overlapping loud audio peaks."
      },
      {
        key: "shorts_scene_change_boost",
        label: "Boost scene changes",
        type: "bool",
        implemented: true,
        help: "Adds a score bonus to clips around visual scene changes."
      },
      {
        key: "shorts_remove_fillers",
        label: "Remove filler words",
        type: "bool",
        implemented: true,
        help: "Cuts filler words when word timings are available."
      },
      {
        key: "shorts_filler_words",
        label: "Filler words",
        type: "text",
        implemented: true,
        help: "Comma-separated. Defaults: hum, hmm, uh, um, ah, eh, erm, er."
      },
      {
        key: "audio_enhance",
        label: "Enhance Short audio",
        type: "bool",
        implemented: true,
        help: "Applies high-pass, FFT denoise, and loudness normalization to rendered Shorts."
      },
      {
        key: "audio_highpass_hz",
        label: "High-pass (Hz)",
        type: "number",
        implemented: true,
        min: 20,
        max: 500,
        step: 5
      },
      {
        key: "audio_denoise",
        label: "FFT denoise",
        type: "bool",
        implemented: true
      },
      {
        key: "audio_denoise_db",
        label: "Denoise amount",
        type: "number",
        implemented: true,
        min: 1,
        max: 30,
        step: 1
      },
      {
        key: "audio_noise_floor_db",
        label: "Noise floor (dB)",
        type: "number",
        implemented: true,
        min: -80,
        max: -5,
        step: 1
      },
      {
        key: "audio_loudnorm",
        label: "Loudness normalize",
        type: "bool",
        implemented: true
      },
      {
        key: "audio_target_lufs",
        label: "Target LUFS",
        type: "number",
        implemented: true,
        min: -30,
        max: -8,
        step: 0.5
      },
      {
        key: "audio_true_peak_db",
        label: "True peak (dB)",
        type: "number",
        implemented: true,
        min: -9,
        max: 0,
        step: 0.1
      },
      {
        key: "overlay_enabled",
        label: "Watermark overlay",
        type: "bool",
        implemented: true
      },
      {
        key: "overlay_asset",
        label: "Overlay asset",
        type: "text",
        implemented: true,
        help: "Filename from the image asset store."
      },
      {
        key: "overlay_position",
        label: "Overlay position",
        type: "select",
        implemented: true,
        options: [
          { value: "top_left", label: "Top left" },
          { value: "top_right", label: "Top right" },
          { value: "bottom_left", label: "Bottom left" },
          { value: "bottom_right", label: "Bottom right" },
          { value: "center", label: "Center" }
        ]
      },
      {
        key: "overlay_margin_px",
        label: "Overlay margin (px)",
        type: "number",
        implemented: true,
        min: 0,
        max: 400,
        step: 1
      },
      {
        key: "overlay_width_ratio",
        label: "Overlay width ratio",
        type: "number",
        implemented: true,
        min: 0.03,
        max: 1,
        step: 0.01
      },
      {
        key: "overlay_opacity",
        label: "Overlay opacity",
        type: "number",
        implemented: true,
        min: 0,
        max: 1,
        step: 0.05
      },
      {
        key: "music_enabled",
        label: "Background music",
        type: "bool",
        implemented: true
      },
      {
        key: "music_asset",
        label: "Music track",
        type: "text",
        implemented: true,
        help: "Filename from the music asset store."
      },
      {
        key: "music_volume",
        label: "Music volume",
        type: "number",
        implemented: true,
        min: 0,
        max: 1,
        step: 0.01
      },
      {
        key: "music_ducking",
        label: "Duck under speech",
        type: "bool",
        implemented: true
      },
      {
        key: "music_fade_in_ms",
        label: "Music fade in (ms)",
        type: "number",
        implemented: true,
        min: 0,
        max: 5000,
        step: 50
      },
      {
        key: "music_fade_out_ms",
        label: "Music fade out (ms)",
        type: "number",
        implemented: true,
        min: 0,
        max: 5000,
        step: 50
      },
      {
        key: "intro_enabled",
        label: "Intro card",
        type: "bool",
        implemented: true
      },
      {
        key: "intro_asset",
        label: "Intro image",
        type: "text",
        implemented: true,
        help: "Filename from the image store."
      },
      {
        key: "intro_duration_sec",
        label: "Intro seconds",
        type: "number",
        implemented: true,
        min: 0.2,
        max: 10,
        step: 0.1
      },
      {
        key: "outro_enabled",
        label: "Outro card",
        type: "bool",
        implemented: true
      },
      {
        key: "outro_asset",
        label: "Outro image",
        type: "text",
        implemented: true,
        help: "Filename from the image store."
      },
      {
        key: "outro_duration_sec",
        label: "Outro seconds",
        type: "number",
        implemented: true,
        min: 0.2,
        max: 10,
        step: 0.1
      },
      {
        key: "shorts_hook_mode",
        label: "Auto hook",
        type: "select",
        implemented: true,
        options: [
          { value: "off", label: "Off" },
          { value: "metadata", label: "Metadata only" },
          { value: "repeat", label: "Repeat hook at start" },
          { value: "reorder", label: "Reorder hook to start" }
        ],
        help: "The hook is the highest-scoring sentence inside the selected clip."
      },
      {
        key: "shorts_aspect",
        label: "Aspect ratio",
        type: "select",
        implemented: true,
        options: [
          { value: "9:16", label: "9:16 vertical (Shorts, Reels, TikTok)" },
          { value: "1:1", label: "1:1 square" },
          { value: "16:9", label: "16:9 landscape" }
        ],
        help: "The caption layer uses the same pixel style at the selected render size."
      },
      {
        key: "shorts_resolution",
        label: "Render resolution",
        type: "select",
        implemented: true,
        options: [
          { value: "1080", label: "1080p short edge (full HD)" },
          { value: "1440", label: "1440p short edge (2K)" },
          { value: "2160", label: "2160p short edge (4K)" }
        ],
        help: "2160 renders 2160x3840 vertical, 2160x2160 square, or 3840x2160 landscape."
      },
      {
        key: "shorts_source_start_sec",
        label: "Source start (s)",
        type: "number",
        implemented: true,
        min: 0,
        max: 86400,
        step: 0.1,
        help: "Only sentences fully inside this source window are considered."
      },
      {
        key: "shorts_source_end_sec",
        label: "Source end (s)",
        type: "number",
        implemented: true,
        min: 0,
        max: 86400,
        step: 0.1,
        help: "0 means the end of the source."
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
      { key: "shorts_subtitles", label: "Burn captions", type: "bool", implemented: true },
      { key: "caption_font_family", label: "Caption font", type: "text", implemented: true },
      {
        key: "caption_font_size",
        label: "Caption size",
        type: "number",
        implemented: true,
        min: 8,
        max: 300,
        step: 1
      },
      {
        key: "caption_font_weight",
        label: "Caption weight",
        type: "select",
        implemented: true,
        options: [
          { value: "normal", label: "Normal" },
          { value: "bold", label: "Bold" }
        ]
      },
      { key: "caption_italic", label: "Italic", type: "bool", implemented: true },
      { key: "caption_uppercase", label: "Uppercase", type: "bool", implemented: true },
      { key: "caption_primary_color", label: "Text color", type: "color", implemented: true },
      { key: "caption_highlight_color", label: "Karaoke color", type: "color", implemented: true },
      { key: "caption_outline_color", label: "Outline color", type: "color", implemented: true },
      {
        key: "caption_outline_width",
        label: "Outline width",
        type: "number",
        implemented: true,
        min: 0,
        max: 20,
        step: 1
      },
      { key: "caption_shadow_color", label: "Shadow color", type: "color", implemented: true },
      {
        key: "caption_shadow_offset",
        label: "Shadow offset",
        type: "number",
        implemented: true,
        min: 0,
        max: 20,
        step: 1
      },
      {
        key: "caption_shadow_opacity",
        label: "Shadow opacity",
        type: "number",
        implemented: true,
        min: 0,
        max: 1,
        step: 0.05
      },
      { key: "caption_background_color", label: "Box color", type: "color", implemented: true },
      {
        key: "caption_background_opacity",
        label: "Box opacity",
        type: "number",
        implemented: true,
        min: 0,
        max: 1,
        step: 0.05
      },
      {
        key: "caption_background_padding",
        label: "Box padding",
        type: "number",
        implemented: true,
        min: 0,
        max: 40,
        step: 1
      },
      {
        key: "caption_alignment",
        label: "Alignment (1-9)",
        type: "number",
        implemented: true,
        min: 1,
        max: 9,
        step: 1
      },
      {
        key: "caption_position_x",
        label: "Position X",
        type: "number",
        implemented: true,
        min: 0,
        max: 1,
        step: 0.01
      },
      {
        key: "caption_position_y",
        label: "Position Y",
        type: "number",
        implemented: true,
        min: 0,
        max: 1,
        step: 0.01
      },
      {
        key: "caption_max_width",
        label: "Max width",
        type: "number",
        implemented: true,
        min: 0.2,
        max: 1,
        step: 0.01
      },
      {
        key: "caption_animation",
        label: "Animation",
        type: "select",
        implemented: true,
        options: [
          { value: "none", label: "None" },
          { value: "pop", label: "Pop" },
          { value: "sweep", label: "Sweep" }
        ]
      },
      {
        key: "caption_word_timing",
        label: "Word timing",
        type: "select",
        implemented: true,
        options: [
          { value: "engine", label: "Engine word timings" },
          { value: "proportional", label: "Proportional fallback" },
          { value: "sentence", label: "Sentence only" }
        ]
      },
      { key: "caption_censor_enabled", label: "Censor profanity", type: "bool", implemented: true },
      {
        key: "caption_censor_words",
        label: "Censor words",
        type: "text",
        implemented: true,
        help: "Comma-separated list; matching is case-insensitive."
      },
      {
        key: "caption_censor_replacement",
        label: "Censor replacement",
        type: "text",
        implemented: true
      },
      {
        key: "caption_keyword_highlight_enabled",
        label: "Highlight keywords",
        type: "bool",
        implemented: true
      },
      {
        key: "caption_keyword_color",
        label: "Keyword color",
        type: "color",
        implemented: true
      },
      {
        key: "caption_keyword_words",
        label: "Keyword words",
        type: "text",
        implemented: true,
        help: "Comma-separated. Empty auto-selects the top words."
      },
      {
        key: "caption_emoji_enabled",
        label: "Context emojis",
        type: "bool",
        implemented: true
      },
      {
        key: "caption_emoji_map",
        label: "Emoji map",
        type: "text",
        implemented: true,
        help: "Comma-separated word=emoji pairs."
      },
      {
        key: "caption_brand_vocabulary",
        label: "Brand vocabulary",
        type: "text",
        implemented: true,
        help: "Comma-separated wrong=Preferred pairs."
      }
    ]
  },
  {
    index: "08",
    id: "export",
    tab: "export",
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
