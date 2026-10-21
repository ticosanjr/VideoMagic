<script lang="ts">
  import { onMount } from "svelte";
  import BrandTemplateManager from "$lib/BrandTemplateManager.svelte";
  import CapabilitiesPanel from "$lib/CapabilitiesPanel.svelte";
  import CaptionPreview from "$lib/CaptionPreview.svelte";
  import FontManager from "$lib/FontManager.svelte";
  import ImageManager from "$lib/ImageManager.svelte";
  import MusicManager from "$lib/MusicManager.svelte";
  import LogDrawer from "$lib/LogDrawer.svelte";
  import PathPicker from "$lib/PathPicker.svelte";
  import ShortEditor from "$lib/ShortEditor.svelte";
  import StatusIcon from "$lib/StatusIcon.svelte";
  import {
    cancelJob,
    createJob,
    errorMessage,
    getJob,
    getJobState,
    getSystem,
    listJobs,
    probeMedia,
    type Job,
    type JobState,
    type JobStage,
    type ProbedMedia,
    type ShortClip,
    type SystemInfo
  } from "$lib/api";
  import {
    elapsedMs,
    formatBytes,
    formatDateTime,
    formatDuration,
    formatSeconds,
    statusText
  } from "$lib/format";
  import { baseName, parentPath, suggestOutputPath } from "$lib/paths";
  import {
    defaultConfig,
    modules,
    moduleTabs,
    statusLabel,
    statusStyles,
    type ConfigKey,
    type ModuleTab,
    type RackModule,
    type Status
  } from "$lib/modules";
  import "../app.css";

  let system = $state<SystemInfo | null>(null);
  let source = $state("");
  let output = $state("");
  let transcript = $state("");
  let config = $state<any>({ ...defaultConfig });
  let job = $state<Job | null>(null);
  let jobState = $state<JobState | null>(null);
  let history = $state<Job[]>([]);
  let error = $state("");
  let busy = $state(false);
  let logOpen = $state(false);
  let logModule = $state<string | null>(null);
  let overrides = $state<Record<number, "keep" | "discard">>({});
  let now = $state(Date.now());
  let timer: ReturnType<typeof setTimeout> | undefined;
  let clock: ReturnType<typeof setInterval> | undefined;
  let pickerKind = $state<PickerKind | null>(null);
  let outputTouched = $state(false);
  let sourceMedia = $state<ProbedMedia | null>(null);
  let mediaLoading = $state(false);
  let mediaError = $state("");
  let toast = $state<{ kind: "success" | "error"; message: string } | null>(null);
  let toastTimer: ReturnType<typeof setTimeout> | undefined;
  let preset = $state<"youtube" | "lecture" | "shorts" | "custom">("custom");
  let activeTab = $state<ModuleTab>("speech");
  let shortEditor = $state<{ index: number; short: ShortClip } | null>(null);
  let probeToken = 0;

  const visibleModules = $derived(modules.filter((module) => module.tab === activeTab));

  type PickerKind = "source" | "output" | "transcript" | "faster_model" | "whisper_model";

  const VIDEO_EXTENSIONS = ["mp4", "mov", "mkv", "webm", "m4v", "avi", "mts", "m2ts"];

  onMount(() => {
    getSystem()
      .then((payload) => (system = payload))
      .catch((reason) => (error = errorMessage(reason)));
    void refreshHistory();
    clock = setInterval(() => (now = Date.now()), 1000);
    return () => {
      clearTimeout(timer);
      clearTimeout(toastTimer);
      clearInterval(clock);
    };
  });

  const terminal = (status: string | undefined) =>
    status === "succeeded" || status === "failed" || status === "cancelled";

  const active = $derived(job?.status === "queued" || job?.status === "running");

  const jobDuration = $derived(
    job ? job.duration_ms ?? elapsedMs(job.started_at, job.finished_at, now) : null
  );

  const artifacts = $derived(
    job?.result?.artifacts ? Object.entries(job.result.artifacts) : []
  );

  function applySuggestedOutput(path = source) {
    output = suggestOutputPath(path);
    outputTouched = false;
  }

  function openPicker(kind: PickerKind) {
    pickerKind = kind;
  }

  function notify(kind: "success" | "error", message: string) {
    clearTimeout(toastTimer);
    toast = { kind, message };
    toastTimer = setTimeout(() => (toast = null), 3200);
  }

  async function inspectSource(path: string) {
    const token = ++probeToken;
    sourceMedia = null;
    mediaError = "";
    if (!path.trim()) {
      mediaLoading = false;
      return;
    }
    mediaLoading = true;
    try {
      const probed = await probeMedia(path);
      if (token === probeToken) sourceMedia = probed;
    } catch (reason) {
      if (token === probeToken) mediaError = errorMessage(reason);
    } finally {
      if (token === probeToken) mediaLoading = false;
    }
  }

  function handlePick(path: string) {
    const kind = pickerKind;
    pickerKind = null;
    if (kind === "source") {
      source = path;
      if (!output.trim() || !outputTouched) applySuggestedOutput(path);
      void inspectSource(path);
      notify("success", `${baseName(path)} selected`);
    } else if (kind === "output") {
      output = path;
      outputTouched = true;
      notify("success", "Output folder selected");
    } else if (kind === "transcript") {
      transcript = path;
      notify("success", `${baseName(path)} selected`);
    } else if (kind === "faster_model") {
      config.faster_whisper_model = path;
      preset = "custom";
    } else if (kind === "whisper_model") {
      config.whisper_model = path;
      preset = "custom";
    }
  }

  function clearSource() {
    source = "";
    sourceMedia = null;
    mediaError = "";
  }

  function pickerMode(): "file" | "directory" {
    return pickerKind === "output" || pickerKind === "faster_model" ? "directory" : "file";
  }

  function pickerTitle(): string {
    if (pickerKind === "source") return "Choose source video";
    if (pickerKind === "output") return "Choose output folder";
    if (pickerKind === "transcript") return "Choose an SRT transcript";
    if (pickerKind === "faster_model") return "Choose Faster-Whisper model folder";
    return "Choose whisper.cpp model";
  }

  function pickerExtensions(): string[] {
    if (pickerKind === "source") return VIDEO_EXTENSIONS;
    if (pickerKind === "transcript") return ["srt"];
    if (pickerKind === "whisper_model") return ["bin"];
    return [];
  }

  function pickerInitialPath(): string {
    if (pickerKind === "source" || pickerKind === "transcript") {
      return parentPath(source);
    }
    if (pickerKind === "output") {
      return parentPath(output) || parentPath(source);
    }
    if (pickerKind === "faster_model") return parentPath(config.faster_whisper_model || "");
    return parentPath(config.whisper_model || "");
  }

  function mediaDurationSeconds(): number | null {
    if (!sourceMedia) return null;
    return (sourceMedia.media.duration_frames * sourceMedia.media.fps_den) / sourceMedia.media.fps_num;
  }

  function mediaFps(): string {
    if (!sourceMedia) return "—";
    const value = sourceMedia.media.fps_num / sourceMedia.media.fps_den;
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }

  function setField(key: ConfigKey, value: unknown) {
    config[key] = value;
    preset = "custom";
  }

  function toggleTarget(target: string) {
    const current: string[] = Array.isArray(config.export_targets)
      ? [...config.export_targets]
      : [];
    const next = current.includes(target)
      ? current.filter((item) => item !== target)
      : [...current, target];
    if (next.length > 0) config.export_targets = next;
    preset = "custom";
  }

  function applyPreset(name: "youtube" | "lecture" | "shorts") {
    preset = name;
    if (name === "youtube") {
      config.noise_db = -30;
      config.min_silence_ms = 400;
      config.jcut = true;
      config.lcut = false;
      config.zooms = true;
      config.shorts = false;
    } else if (name === "lecture") {
      config.noise_db = -30;
      config.min_silence_ms = 700;
      config.jcut = false;
      config.lcut = false;
      config.zooms = false;
      config.shorts = false;
    } else {
      config.noise_db = -30;
      config.min_silence_ms = 250;
      config.jcut = true;
      config.lcut = false;
      config.zooms = true;
      config.shorts = true;
    }
  }

  function buildPayload() {
    return {
      source: source.trim(),
      output: output.trim(),
      vad_engine: String(config.vad_engine || "auto"),
      noise_db: Number(config.noise_db),
      min_silence_ms: Number(config.min_silence_ms),
      min_speech_ms: Number(config.min_speech_ms),
      speech_threshold: Number(config.speech_threshold),
      speech_pad_before_ms: Number(config.speech_pad_before_ms),
      speech_pad_after_ms: Number(config.speech_pad_after_ms),
      jcut: Boolean(config.jcut),
      lcut: Boolean(config.lcut),
      offset_ms: Number(config.offset_ms),
      crossfade_ms: Number(config.crossfade_ms),
      fade_in_ms: Number(config.fade_in_ms),
      fade_out_ms: Number(config.fade_out_ms),
      fade_curve: String(config.fade_curve),
      handle_check: Boolean(config.handle_check),
      zooms: Boolean(config.zooms),
      zoom_mode: String(config.zoom_mode),
      zoom_min_scale: Number(config.zoom_min_scale),
      zoom_max_scale: Number(config.zoom_max_scale),
      punch_in_scale: Number(config.punch_in_scale),
      anchor_point: String(config.anchor_point),
      progressive_zoom: Boolean(config.progressive_zoom),
      pan_direction: String(config.pan_direction),
      dialect: String(config.dialect) as "1.9" | "1.10",
      export_targets: config.export_targets as string[],
      transcript: transcript.trim() || null,
      cull_retakes: Boolean(config.cull_retakes),
      strictness: String(config.strictness),
      retake_strategy: String(config.retake_strategy),
      context_window: Number(config.context_window),
      llm_base_url: String(config.llm_base_url || "").trim() || null,
      llm_model: String(config.llm_model || "qwen2.5:7b-instruct"),
      shorts: Boolean(config.shorts),
      shorts_count: Number(config.shorts_count),
      shorts_min_count: Number(config.shorts_min_count),
      shorts_min_sec: Number(config.shorts_min_sec),
      shorts_max_sec: Number(config.shorts_max_sec),
      shorts_subtitles: Boolean(config.shorts_subtitles),
      shorts_selection_mode: String(config.shorts_selection_mode),
      shorts_prompt: String(config.shorts_prompt || ""),
      shorts_reprompt: String(config.shorts_reprompt || ""),
      shorts_prompt_mode: String(config.shorts_prompt_mode || "replace") as "replace" | "refine",
      shorts_hook_mode: String(config.shorts_hook_mode || "off") as
        | "off"
        | "metadata"
        | "repeat"
        | "reorder",
      shorts_reframe_mode: String(config.shorts_reframe_mode || "center_crop_9_16") as
        | "center_crop_9_16"
        | "motion_tracking"
        | "face_tracking"
        | "auto_face_tracking_yolo",
      shorts_remove_fillers: Boolean(config.shorts_remove_fillers),
      shorts_filler_words: String(config.shorts_filler_words || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      shorts_aspect: String(config.shorts_aspect || "9:16"),
      shorts_source_start_sec: Number(config.shorts_source_start_sec || 0),
      shorts_source_end_sec: Number(config.shorts_source_end_sec || 0) || null,
      allow_external_services: Boolean(config.allow_external_services),
      allowed_external_hosts: String(config.allowed_external_hosts || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      audio_enhance: Boolean(config.audio_enhance),
      audio_highpass_hz: Number(config.audio_highpass_hz),
      audio_denoise: Boolean(config.audio_denoise),
      audio_denoise_db: Number(config.audio_denoise_db),
      audio_noise_floor_db: Number(config.audio_noise_floor_db),
      audio_loudnorm: Boolean(config.audio_loudnorm),
      audio_target_lufs: Number(config.audio_target_lufs),
      audio_true_peak_db: Number(config.audio_true_peak_db),
      overlay_enabled: Boolean(config.overlay_enabled),
      overlay_asset: String(config.overlay_asset || ""),
      overlay_position: String(config.overlay_position || "bottom_right"),
      overlay_margin_px: Number(config.overlay_margin_px),
      overlay_width_ratio: Number(config.overlay_width_ratio),
      overlay_opacity: Number(config.overlay_opacity),
      music_enabled: Boolean(config.music_enabled),
      music_asset: String(config.music_asset || ""),
      music_volume: Number(config.music_volume),
      music_ducking: Boolean(config.music_ducking),
      music_fade_in_ms: Number(config.music_fade_in_ms),
      music_fade_out_ms: Number(config.music_fade_out_ms),
      intro_enabled: Boolean(config.intro_enabled),
      intro_asset: String(config.intro_asset || ""),
      intro_duration_sec: Number(config.intro_duration_sec),
      outro_enabled: Boolean(config.outro_enabled),
      outro_asset: String(config.outro_asset || ""),
      outro_duration_sec: Number(config.outro_duration_sec),
      caption_font_family: String(config.caption_font_family),
      caption_font_size: Number(config.caption_font_size),
      caption_font_weight: String(config.caption_font_weight),
      caption_italic: Boolean(config.caption_italic),
      caption_uppercase: Boolean(config.caption_uppercase),
      caption_primary_color: String(config.caption_primary_color),
      caption_highlight_color: String(config.caption_highlight_color),
      caption_outline_color: String(config.caption_outline_color),
      caption_outline_width: Number(config.caption_outline_width),
      caption_shadow_color: String(config.caption_shadow_color),
      caption_shadow_offset: Number(config.caption_shadow_offset),
      caption_shadow_opacity: Number(config.caption_shadow_opacity),
      caption_background_color: String(config.caption_background_color),
      caption_background_opacity: Number(config.caption_background_opacity),
      caption_background_padding: Number(config.caption_background_padding),
      caption_alignment: Number(config.caption_alignment),
      caption_position_x: Number(config.caption_position_x),
      caption_position_y: Number(config.caption_position_y),
      caption_max_width: Number(config.caption_max_width),
      caption_animation: String(config.caption_animation),
      caption_word_timing: String(config.caption_word_timing),
      caption_censor_enabled: Boolean(config.caption_censor_enabled),
      caption_censor_words: String(config.caption_censor_words || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      caption_censor_replacement: String(config.caption_censor_replacement || "***"),
      caption_keyword_highlight_enabled: Boolean(config.caption_keyword_highlight_enabled),
      caption_keyword_color: String(config.caption_keyword_color || "#00E5FF"),
      caption_keyword_words: String(config.caption_keyword_words || "")
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean),
      caption_emoji_enabled: Boolean(config.caption_emoji_enabled),
      caption_emoji_map: parsePairs(config.caption_emoji_map),
      caption_brand_vocabulary: parsePairs(config.caption_brand_vocabulary),
      transcribe: Boolean(config.transcribe),
      asr_base_url: String(config.asr_base_url || "").trim() || null,
      asr_model: String(config.asr_model || "whisper-1"),
      asr_language: String(config.asr_language || "pt"),
      whisper_engine: String(config.whisper_engine || "auto"),
      whisper_model_size: String(config.whisper_model_size || "small"),
      whisper_device: String(config.whisper_device || "cpu"),
      whisper_compute_type: String(config.whisper_compute_type || "int8"),
      whisper_vad_filter: Boolean(config.whisper_vad_filter),
      whisper_model: String(config.whisper_model || "").trim() || null,
      faster_whisper_model: String(config.faster_whisper_model || "").trim() || null,
      overrides: Object.entries(overrides).map(([sentenceId, action]) => ({
        sentence_id: Number(sentenceId),
        action
      }))
    };
  }

  function setOverride(sentenceId: number, action: "keep" | "discard") {
    const next = { ...overrides };
    if (next[sentenceId] === action) delete next[sentenceId];
    else next[sentenceId] = action;
    overrides = next;
  }

  function effectiveAction(sentenceId: number): "keep" | "discard" {
    if (overrides[sentenceId]) return overrides[sentenceId];
    return jobState?.retake_culls.includes(sentenceId) ? "discard" : "keep";
  }

  async function applyOverrides() {
    if (!jobState || Object.keys(overrides).length === 0 || active) return;
    await start();
  }

  async function start() {
    error = "";
    if (!source.trim() || !output.trim()) {
      error = "Source and output are required.";
      return;
    }
    if (config.cull_retakes && !transcript.trim()) {
      error = "Retake culling needs an SRT transcript path.";
      return;
    }
    if (config.shorts && !transcript.trim() && !config.transcribe) {
      error = "Shorts need an SRT transcript or local/ASR transcription enabled.";
      return;
    }
    if (Number(config.shorts_min_count) > Number(config.shorts_count)) {
      error = "Shorts minimum count cannot exceed the target count.";
      return;
    }
    if (
      Number(config.shorts_source_end_sec) > 0 &&
      Number(config.shorts_source_end_sec) <= Number(config.shorts_source_start_sec)
    ) {
      error = "Shorts source end must be greater than the source start.";
      return;
    }
    if (Number(config.zoom_min_scale) > Number(config.zoom_max_scale)) {
      error = "Minimum zoom cannot exceed maximum zoom.";
      return;
    }
    if (
      Number(config.punch_in_scale) < Number(config.zoom_min_scale) ||
      Number(config.punch_in_scale) > Number(config.zoom_max_scale)
    ) {
      error = "Punch-in scale must be inside the zoom min/max range.";
      return;
    }
    busy = true;
    jobState = null;
    clearTimeout(timer);
    try {
      job = await createJob(buildPayload());
      notify("success", "Pipeline started");
      schedule();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  function schedule() {
    clearTimeout(timer);
    if (!job || terminal(job.status)) return;
    timer = setTimeout(refresh, 600);
  }

  async function refresh() {
    if (!job) return;
    try {
      job = await getJob(job.job_id);
      if (!terminal(job.status)) {
        schedule();
      } else {
        if (job.status === "succeeded") await loadState();
        await refreshHistory();
      }
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function refreshHistory() {
    try {
      history = await listJobs();
    } catch {
      // The history panel is optional; the run flow stays usable.
    }
  }

  async function loadState() {
    if (!job) return;
    try {
      jobState = await getJobState(job.job_id);
    } catch {
      jobState = null;
    }
  }

  async function cancel() {
    if (!job) return;
    try {
      job = await cancelJob(job.job_id);
      schedule();
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function selectJob(entry: Job) {
    job = entry;
    jobState = null;
    error = "";
    overrides = {};
    source = entry.source;
    output = entry.output;
    outputTouched = true;
    transcript = entry.options.transcript ?? "";
    void inspectSource(entry.source);
    if (entry.status === "succeeded") await loadState();
  }

  function stageFor(moduleId: string): JobStage | undefined {
    return job?.stages?.find((item) => item.module === moduleId);
  }

  function statusFor(module: RackModule): Status {
    if (!module.portable) return "bypassed";
    if (module.id === "transcribe" && !transcript && !config.transcribe) return "bypassed";
    if (module.id === "shorts" && (!config.shorts || !transcript)) return "bypassed";
    if (module.id === "retakes" && (!config.cull_retakes || !transcript)) return "bypassed";
    if (module.id === "jl_cuts" && !config.jcut && !config.lcut) return "bypassed";
    if (module.id === "zooms" && !config.zooms) return "bypassed";
    const stage = stageFor(module.id);
    if (stage) return stage.status as Status;
    if (job?.status === "succeeded") return "bypassed";
    return "pending";
  }

  function progressFor(module: RackModule): number {
    const status = statusFor(module);
    if (status === "succeeded" || status === "cached") return 100;
    if (status === "bypassed" || status === "pending" || status === "cancelled") return 0;
    return stageFor(module.id)?.progress ?? 0;
  }

  function durationFor(module: RackModule): number | null {
    const stage = stageFor(module.id);
    if (!stage) return null;
    if (stage.duration_ms !== null) return stage.duration_ms;
    if (stage.status === "running") return elapsedMs(stage.started_at, null, now);
    return null;
  }

  function isEnabled(module: RackModule): boolean {
    if (!module.portable) return false;
    if (!module.toggleKey) return true;
    if (module.id === "jl_cuts") return Boolean(config.jcut || config.lcut);
    return Boolean(config[module.toggleKey]);
  }

  function toggleModule(module: RackModule) {
    if (!module.toggleKey) return;
    preset = "custom";
    if (module.id === "jl_cuts") {
      const next = !(config.jcut || config.lcut);
      config.jcut = next;
      if (!next) config.lcut = false;
      return;
    }
    config[module.toggleKey] = !config[module.toggleKey];
  }

  function barClass(status: Status): string {
    if (status === "failed") return "bg-rose-500";
    if (status === "succeeded" || status === "cached") return "bg-emerald-500";
    if (status === "running") return "bg-sky-500";
    if (status === "blocked" || status === "dirty") return "bg-amber-500";
    return "bg-neutral-600";
  }

  function openLog(module?: string) {
    logModule = module ?? null;
    logOpen = true;
  }

  function sentenceText(id: number): string {
    return jobState?.transcript.find((item) => item.id === id)?.text ?? `sentence ${id}`;
  }

  const targetOptions = [
    { id: "resolve", label: "Resolve" },
    { id: "premiere", label: "Premiere" },
    { id: "kdenlive", label: "Kdenlive" }
  ];

  const durationPresets = [
    { label: "0–1 min", min: 1, max: 60 },
    { label: "1–3 min", min: 60, max: 180 },
    { label: "3–5 min", min: 180, max: 300 },
    { label: "5–10 min", min: 300, max: 600 }
  ];

  function openShortEditor(index: number, short: ShortClip) {
    shortEditor = { index, short };
  }

  function savedShort(updated: ShortClip) {
    if (job?.result?.shorts && shortEditor) {
      const index = shortEditor.index;
      job = {
        ...job,
        result: {
          ...job.result,
          shorts: job.result.shorts.map((item, itemIndex) =>
            itemIndex === index ? updated : item
          )
        }
      };
    }
    shortEditor = null;
    notify("success", "Short re-rendered");
  }

  function parsePairs(value: unknown): Record<string, string> {
    const pairs: Record<string, string> = {};
    for (const item of String(value || "").split(",")) {
      const [key, ...rest] = item.split("=");
      const target = rest.join("=").trim();
      if (key.trim() && target) pairs[key.trim()] = target;
    }
    return pairs;
  }

  function setShortDuration(min: number, max: number) {
    config.shorts_min_sec = min;
    config.shorts_max_sec = max;
    preset = "custom";
  }
</script>

<svelte:head>
  <title>VideoFlow — Rack</title>
  <meta name="description" content="Local, non-destructive video pre-edit pipeline." />
</svelte:head>

<div class="min-h-screen bg-neutral-950">
  <div class="mx-auto flex min-h-screen max-w-[1400px] flex-col gap-6 px-4 py-6 sm:px-6 lg:px-8">
    <header class="flex flex-wrap items-center justify-between gap-4">
      <div class="flex items-center gap-3">
        <div class="flex h-11 w-11 items-center justify-center rounded-2xl bg-sky-500/15 text-sky-300 ring-1 ring-inset ring-sky-400/20">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <rect x="3" y="5" width="18" height="14" rx="2" />
            <path d="M7 5v14M17 5v14M3 9h4M3 15h4M17 9h4M17 15h4" />
          </svg>
        </div>
        <div>
          <div class="flex items-center gap-2">
            <h1 class="text-xl font-semibold tracking-tight text-white">VideoFlow</h1>
            <span class="rounded-full border border-white/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-neutral-500">local</span>
          </div>
          <p class="mt-0.5 text-xs text-neutral-500">Rough cut automation for talking-head video</p>
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-2 text-xs">
        <span class="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 font-mono text-[11px] text-neutral-400">{system?.version ?? "offline"}</span>
        <span class="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[11px] text-neutral-500">FFmpeg {system?.ffmpeg ? "ready" : "missing"}</span>
        <button
          type="button"
          onclick={() => openLog()}
          disabled={!job}
          class="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[11px] text-neutral-400 transition hover:border-sky-500/50 hover:text-sky-300 disabled:opacity-40"
        >
          Global log
          {#if job}<span class="ml-1 text-neutral-600">{job.log_count}</span>{/if}
        </button>
      </div>
    </header>

    {#if toast}
      <div
        class={`fixed right-4 top-4 z-[60] flex max-w-sm items-start gap-2 rounded-2xl border px-4 py-3 text-sm shadow-2xl ${
          toast.kind === "error"
            ? "border-rose-500/30 bg-rose-950 text-rose-200"
            : "border-emerald-500/30 bg-emerald-950 text-emerald-200"
        }`}
        role="status"
        aria-live="polite"
      >
        <span class={`mt-0.5 h-2 w-2 shrink-0 rounded-full ${toast.kind === "error" ? "bg-rose-400" : "bg-emerald-400"}`}></span>
        <span>{toast.message}</span>
      </div>
    {/if}

    <section class="overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-br from-neutral-900 via-neutral-900/80 to-neutral-950 shadow-2xl shadow-black/20">
      <div class="flex flex-wrap items-center justify-between gap-3 border-b border-white/10 px-5 py-4">
        <div>
          <h2 class="text-sm font-semibold text-white">New project</h2>
          <p class="mt-1 text-xs text-neutral-500">Pick a source, choose where the project should live, and run.</p>
        </div>
        <span class="rounded-full border border-emerald-400/20 bg-emerald-400/10 px-2.5 py-1 text-[10px] font-medium uppercase tracking-wide text-emerald-300">Nothing is uploaded</span>
      </div>

      <div class="grid gap-4 p-5 lg:grid-cols-2">
        <div class="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
          <div class="flex items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <span class="font-mono text-[10px] text-neutral-600">01</span>
              <h3 class="text-sm font-medium text-neutral-100">Source video</h3>
            </div>
            {#if source}
              <button type="button" data-testid="source-clear" onclick={clearSource} class="text-[10px] text-neutral-500 transition hover:text-neutral-300">Clear</button>
            {/if}
          </div>
          {#if source}
            <div class="mt-3 flex items-start gap-3">
              <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-sky-400/10 text-sky-300">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                  <rect x="3" y="5" width="18" height="14" rx="2" />
                  <path d="m10 9 5 3-5 3V9Z" />
                </svg>
              </div>
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm font-medium text-neutral-100">{baseName(source)}</p>
                <p class="mt-0.5 break-all font-mono text-[10px] text-neutral-500">{source}</p>
              </div>
              <button type="button" data-testid="source-change" onclick={() => openPicker("source")} class="rounded-lg border border-white/10 px-2.5 py-1.5 text-[11px] text-neutral-400 transition hover:border-sky-500/50 hover:text-sky-300">Change</button>
            </div>
            {#if mediaLoading}
              <p class="mt-3 text-[11px] text-neutral-500">Reading media metadata…</p>
            {:else if sourceMedia}
              <div class="mt-3 flex flex-wrap gap-1.5">
                <span class="rounded-full bg-white/[0.05] px-2 py-1 text-[10px] text-neutral-400">{formatSeconds(mediaDurationSeconds())}</span>
                <span class="rounded-full bg-white/[0.05] px-2 py-1 text-[10px] text-neutral-400">{sourceMedia.media.width}×{sourceMedia.media.height}</span>
                <span class="rounded-full bg-white/[0.05] px-2 py-1 text-[10px] text-neutral-400">{mediaFps()} fps</span>
                <span class="rounded-full bg-white/[0.05] px-2 py-1 text-[10px] text-neutral-400">{(sourceMedia.media.audio_sample_rate / 1000).toFixed(1)} kHz</span>
                <span class="rounded-full bg-white/[0.05] px-2 py-1 text-[10px] text-neutral-400">{formatBytes(sourceMedia.size_bytes)}</span>
              </div>
            {:else if mediaError}
              <p class="mt-3 break-words text-[10px] leading-4 text-amber-300">Metadata unavailable: {mediaError}</p>
            {/if}
          {:else}
            <button
              type="button"
              data-testid="source-choose"
              onclick={() => openPicker("source")}
              class="mt-3 flex w-full flex-col items-center justify-center rounded-xl border border-dashed border-white/15 bg-neutral-950/40 px-4 py-7 text-center transition hover:border-sky-500/50 hover:bg-sky-500/[0.03]"
            >
              <svg class="text-sky-300" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <path d="M4 7a2 2 0 0 1 2-2h4l2 2h6a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V7Z" />
                <path d="M12 11v5M9.5 13.5 12 11l2.5 2.5" />
              </svg>
              <span class="mt-2 text-sm font-medium text-neutral-200">Choose source video</span>
              <span class="mt-1 text-[10px] text-neutral-600">MP4, MOV, MKV, WebM, M4V, AVI</span>
            </button>
          {/if}
        </div>

        <div class="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
          <div class="flex items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <span class="font-mono text-[10px] text-neutral-600">02</span>
              <h3 class="text-sm font-medium text-neutral-100">Output project</h3>
            </div>
            {#if source && !output}
              <button type="button" onclick={() => applySuggestedOutput()} class="text-[10px] text-sky-300 transition hover:text-sky-200">Use suggested</button>
            {/if}
          </div>
          {#if output}
            <div class="mt-3 flex items-start gap-3">
              <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-400/10 text-amber-300">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                  <path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" />
                </svg>
              </div>
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-2">
                  <p class="truncate text-sm font-medium text-neutral-100">{baseName(output)}</p>
                  {#if !outputTouched}<span class="rounded-full bg-sky-400/10 px-2 py-0.5 text-[9px] uppercase tracking-wide text-sky-300">suggested</span>{/if}
                </div>
                <p class="mt-0.5 break-all font-mono text-[10px] text-neutral-500">{output}</p>
              </div>
              <button type="button" data-testid="output-change" onclick={() => openPicker("output")} class="rounded-lg border border-white/10 px-2.5 py-1.5 text-[11px] text-neutral-400 transition hover:border-sky-500/50 hover:text-sky-300">Change</button>
            </div>
          {:else}
            <button
              type="button"
              data-testid="output-choose"
              onclick={() => openPicker("output")}
              class="mt-3 flex w-full flex-col items-center justify-center rounded-xl border border-dashed border-white/15 bg-neutral-950/40 px-4 py-7 text-center transition hover:border-sky-500/50 hover:bg-sky-500/[0.03]"
            >
              <svg class="text-amber-300" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                <path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" />
                <path d="M12 11v5M9.5 13.5 12 16l2.5-2.5" />
              </svg>
              <span class="mt-2 text-sm font-medium text-neutral-200">Choose output folder</span>
              <span class="mt-1 text-[10px] text-neutral-600">Create a folder now or select an existing one</span>
            </button>
          {/if}
          <p class="mt-2 text-[10px] leading-4 text-neutral-600">The project keeps its state, exports, and work files in this folder.</p>
        </div>
      </div>

      <div class="grid gap-4 px-5 pb-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)]">
        <div class="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
          <div class="flex items-center justify-between gap-2">
            <div class="flex items-center gap-2">
              <span class="font-mono text-[10px] text-neutral-600">03</span>
              <h3 class="text-sm font-medium text-neutral-100">Transcript</h3>
              <span class="rounded-full bg-white/[0.05] px-2 py-0.5 text-[9px] uppercase tracking-wide text-neutral-500">optional</span>
            </div>
            {#if transcript}
              <button type="button" onclick={() => (transcript = "")} class="text-[10px] text-neutral-500 transition hover:text-neutral-300">Clear</button>
            {/if}
          </div>
          {#if transcript}
            <div class="mt-3 flex items-center gap-2">
              <div class="min-w-0 flex-1">
                <p class="truncate text-sm text-neutral-200">{baseName(transcript)}</p>
                <p class="mt-0.5 break-all font-mono text-[10px] text-neutral-500">{transcript}</p>
              </div>
              <button type="button" data-testid="transcript-change" onclick={() => openPicker("transcript")} class="rounded-lg border border-white/10 px-2.5 py-1.5 text-[11px] text-neutral-400 transition hover:border-sky-500/50 hover:text-sky-300">Change</button>
            </div>
          {:else}
            <button type="button" data-testid="transcript-choose" onclick={() => openPicker("transcript")} class="mt-3 flex w-full items-center justify-between rounded-xl border border-white/10 bg-neutral-950/40 px-3 py-2.5 text-left text-xs text-neutral-400 transition hover:border-sky-500/50 hover:text-sky-300">
              <span>Import an SRT instead of transcribing</span>
              <span class="font-mono text-[10px] text-neutral-600">.srt</span>
            </button>
          {/if}
          <p class="mt-2 text-[10px] leading-4 text-neutral-600">An SRT wins over local transcription. Leave empty to use Faster-Whisper or whisper.cpp.</p>
        </div>

        <div class="rounded-2xl border border-white/10 bg-white/[0.03] p-4">
          <div class="flex items-center justify-between gap-2">
            <h3 class="text-sm font-medium text-neutral-100">Starting point</h3>
            {#if preset === "custom"}<span class="rounded-full bg-white/[0.05] px-2 py-0.5 text-[9px] uppercase tracking-wide text-neutral-500">custom</span>{/if}
          </div>
          <div class="mt-3 grid gap-2 sm:grid-cols-3">
            {#each [
              { id: "youtube", label: "YouTube", copy: "Clean cuts, J-cuts, punch-ins" },
              { id: "lecture", label: "Lecture", copy: "Longer pauses, stable frame" },
              { id: "shorts", label: "Main + Shorts", copy: "Keep the edit; add vertical clips" }
            ] as option}
              <button
                type="button"
                onclick={() => applyPreset(option.id as "youtube" | "lecture" | "shorts")}
                aria-pressed={preset === option.id}
                class={`rounded-xl border px-3 py-2.5 text-left transition ${
                  preset === option.id
                    ? "border-sky-500/50 bg-sky-500/10 text-sky-200"
                    : "border-white/10 bg-neutral-950/40 text-neutral-400 hover:border-white/20 hover:text-neutral-200"
                }`}
              >
                <span class="block text-xs font-medium">{option.label}</span>
                <span class="mt-1 block text-[10px] leading-4 opacity-70">{option.copy}</span>
              </button>
            {/each}
          </div>
          <div class="mt-3 rounded-xl border border-white/10 bg-neutral-950/40 p-3">
            <label class="flex items-center justify-between gap-3 text-xs text-neutral-300">
              <span>
                <span class="block font-medium text-neutral-200">Also render vertical shorts</span>
                <span class="mt-0.5 block text-[10px] text-neutral-600">The main project stays intact; MP4 Shorts are added under <span class="font-mono">shorts/</span>.</span>
              </span>
              <input
                type="checkbox"
                checked={Boolean(config.shorts)}
                onchange={() => { config.shorts = !config.shorts; preset = "custom"; }}
                class="h-4 w-4 rounded border-neutral-700 bg-neutral-800"
              />
            </label>
            {#if config.shorts}
              <div class="mt-3 grid grid-cols-2 gap-2">
                <label class="text-[10px] uppercase tracking-wide text-neutral-500">
                  Target
                  <input type="number" min="1" max="20" value={config.shorts_count} oninput={(event) => setField("shorts_count", Number(event.currentTarget.value))} class="mt-1 w-full rounded-lg border border-white/10 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100" />
                </label>
                <label class="text-[10px] uppercase tracking-wide text-neutral-500">
                  Minimum
                  <input type="number" min="1" max="20" value={config.shorts_min_count} oninput={(event) => setField("shorts_min_count", Number(event.currentTarget.value))} class="mt-1 w-full rounded-lg border border-white/10 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100" />
                </label>
              </div>
            {/if}
          </div>
          <p class="mt-2 text-[10px] leading-4 text-neutral-600">Tune individual modules below. Any change switches the preset to custom.</p>
        </div>
      </div>

      <details class="border-t border-white/10 px-5 py-3">
        <summary class="cursor-pointer text-xs font-medium text-neutral-400 transition hover:text-neutral-200">Advanced paths and local models</summary>
        <div class="mt-3 grid gap-3 md:grid-cols-2">
          <label class="text-[11px] text-neutral-500">
            Source path
            <input
              bind:value={source}
              onchange={() => {
                if (!outputTouched) applySuggestedOutput(source);
                void inspectSource(source);
              }}
              placeholder="/media/interview.mp4"
              class="mt-1 w-full rounded-xl border border-white/10 bg-neutral-950 px-3 py-2 font-mono text-xs text-neutral-200 placeholder:text-neutral-700 focus:border-sky-500 focus:outline-none"
            />
          </label>
          <label class="text-[11px] text-neutral-500">
            Output path
            <input
              bind:value={output}
              oninput={() => (outputTouched = true)}
              placeholder="/projects/interview-edit"
              class="mt-1 w-full rounded-xl border border-white/10 bg-neutral-950 px-3 py-2 font-mono text-xs text-neutral-200 placeholder:text-neutral-700 focus:border-sky-500 focus:outline-none"
            />
          </label>
          <label class="text-[11px] text-neutral-500">
            SRT transcript
            <input
              bind:value={transcript}
              placeholder="/media/interview.srt"
              class="mt-1 w-full rounded-xl border border-white/10 bg-neutral-950 px-3 py-2 font-mono text-xs text-neutral-200 placeholder:text-neutral-700 focus:border-sky-500 focus:outline-none"
            />
          </label>
          <label class="text-[11px] text-neutral-500">
            Faster-Whisper model directory
            <span class="mt-1 flex gap-1">
              <input
                bind:value={config.faster_whisper_model}
                placeholder="Bundled model"
                class="w-full rounded-xl border border-white/10 bg-neutral-950 px-3 py-2 font-mono text-xs text-neutral-200 placeholder:text-neutral-700 focus:border-sky-500 focus:outline-none"
              />
              <button type="button" onclick={() => openPicker("faster_model")} class="shrink-0 rounded-xl border border-white/10 px-2.5 py-1 text-[10px] text-neutral-400 transition hover:border-sky-500/50 hover:text-sky-300">Browse</button>
            </span>
          </label>
          <label class="text-[11px] text-neutral-500">
            whisper.cpp GGML file
            <span class="mt-1 flex gap-1">
              <input
                bind:value={config.whisper_model}
                placeholder="Bundled tiny model"
                class="w-full rounded-xl border border-white/10 bg-neutral-950 px-3 py-2 font-mono text-xs text-neutral-200 placeholder:text-neutral-700 focus:border-sky-500 focus:outline-none"
              />
              <button type="button" onclick={() => openPicker("whisper_model")} class="shrink-0 rounded-xl border border-white/10 px-2.5 py-1 text-[10px] text-neutral-400 transition hover:border-sky-500/50 hover:text-sky-300">Browse</button>
            </span>
          </label>
          <p class="self-end text-[10px] leading-4 text-neutral-600 md:col-span-2">
            Paths must stay inside the allowed roots shown in the system panel. Leaving a model empty uses the bundled model.
          </p>
        </div>
      </details>

      <div class="flex flex-col gap-3 border-t border-white/10 bg-white/[0.02] px-5 py-4 sm:flex-row sm:items-center">
        <button
          type="button"
          data-testid="run-pipeline"
          onclick={start}
          disabled={busy || active || !source.trim() || !output.trim()}
          class="inline-flex items-center justify-center gap-2 rounded-xl bg-sky-500 px-5 py-2.5 text-sm font-semibold text-neutral-950 shadow-lg shadow-sky-500/10 transition hover:bg-sky-400 disabled:bg-neutral-800 disabled:text-neutral-500 disabled:shadow-none"
        >
          {#if active}
            <svg class="animate-spin" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" aria-hidden="true">
              <path d="M21 12a9 9 0 1 1-9-9" />
            </svg>
            Running…
          {:else}
            <svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
              <path d="m8 5 11 7-11 7V5Z" />
            </svg>
            Run pipeline
          {/if}
        </button>
        <button
          type="button"
          onclick={cancel}
          disabled={!active}
          class="rounded-xl border border-white/10 px-4 py-2.5 text-sm text-neutral-400 transition hover:border-white/20 hover:text-neutral-200 disabled:opacity-40"
        >
          Cancel
        </button>
        <div class="text-[11px] text-neutral-500 sm:ml-auto">
          {#if busy}
            Starting the job…
          {:else if !source.trim()}
            Choose a source video to begin.
          {:else if !output.trim()}
            Choose an output folder to begin.
          {:else if active}
            Job {job?.job_id.slice(0, 8)} is running.
          {:else}
            Ready when you are.
          {/if}
        </div>
      </div>

      {#if job}
        <div class="border-t border-white/10 px-5 py-4">
          <div class="flex flex-wrap items-center gap-3">
            <div class="flex items-center gap-2 text-sm text-neutral-200">
              <StatusIcon status={job.status === "queued" ? "pending" : job.status} size={18} />
              <span class="capitalize">{statusText(job.status)}</span>
            </div>
            <span class="font-mono text-[10px] text-neutral-600">job {job.job_id.slice(0, 8)}</span>
            <span class="ml-auto text-[11px] text-neutral-500">{formatDateTime(job.started_at ?? job.created_at)} · {formatDuration(jobDuration)}</span>
          </div>
          <div class="mt-3 h-2 overflow-hidden rounded-full bg-neutral-800" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow={job.progress}>
            <div class="h-full rounded-full bg-sky-400 transition-all" style={`width: ${job.progress}%`}></div>
          </div>
          <div class="mt-2 flex flex-wrap justify-between gap-2 text-[10px] text-neutral-500">
            <span>Stage: {job.stage}</span>
            <span>{job.progress}%</span>
          </div>
          {#if job.error}
            <div class="mt-3 rounded-xl border border-rose-500/20 bg-rose-950/30 p-3 text-xs text-rose-300">
              <p class="font-medium">{job.error.message}</p>
              <p class="mt-1 font-mono text-[10px] opacity-70">{job.error.code}</p>
            </div>
          {/if}
        </div>
      {/if}

      {#if error}
        <div class="border-t border-rose-500/20 bg-rose-950/20 px-5 py-3 text-xs text-rose-300" role="alert">
          <span class="font-medium">Could not start the run.</span> {error}
        </div>
      {/if}
    </section>

    <div class="grid gap-6 xl:grid-cols-[minmax(0,1fr)_360px]">
    <section aria-label="Pipeline modules" class="space-y-3">
      <div class="flex flex-wrap gap-1 rounded-2xl border border-neutral-800 bg-neutral-900/60 p-1" role="tablist" aria-label="Pipeline areas">
        {#each moduleTabs as tab}
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            title={tab.hint}
            onclick={() => (activeTab = tab.id)}
            class={`flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-medium transition ${
              activeTab === tab.id
                ? "bg-sky-500/15 text-sky-200 ring-1 ring-inset ring-sky-400/20"
                : "text-neutral-400 hover:bg-white/[0.04] hover:text-neutral-200"
            }`}
          >
            {tab.label}
            {#if tab.id !== "providers"}
              <span class="rounded-full bg-black/20 px-1.5 py-0.5 text-[9px] text-neutral-500">
                {modules.filter((module) => module.tab === tab.id).length}
              </span>
            {/if}
          </button>
        {/each}
      </div>

      {#if activeTab === "providers"}
        <CapabilitiesPanel
          allowExternal={Boolean(config.allow_external_services)}
          allowedHosts={String(config.allowed_external_hosts || "")}
          onToggle={(value) => (config.allow_external_services = value)}
          onHosts={(value) => (config.allowed_external_hosts = value)}
        />
      {:else}
        {#each visibleModules as module}
        {@const status = statusFor(module)}
        {@const progress = progressFor(module)}
        {@const duration = durationFor(module)}
        {@const stage = stageFor(module.id)}
        <article class="rounded-2xl border border-neutral-800 bg-neutral-900/50" data-module={module.id}>
          <div class="p-4">
            <div class="flex flex-wrap items-center gap-3">
              <span class="w-8 font-mono text-xs text-neutral-500">{module.index}</span>
              <StatusIcon status={status} size={18} />
              <div class="min-w-0 flex-1">
                <div class="flex flex-wrap items-center gap-2">
                  <h2 class="text-sm font-semibold">{module.name}</h2>
                  <span
                    class="rounded-full px-2 py-0.5 text-[11px] font-medium uppercase tracking-wide ring-1 {statusStyles[
                      status
                    ]}"
                  >
                    {statusLabel[status]}
                  </span>
                  {#if module.tag}
                    <span class="rounded-full bg-neutral-800 px-2 py-0.5 text-[10px] uppercase text-neutral-500">
                      {module.tag}
                    </span>
                  {/if}
                </div>
                <p class="mt-1 text-xs text-neutral-400">{module.summary}</p>
              </div>
              {#if module.toggleKey}
                <label class="flex items-center gap-2 text-xs text-neutral-400">
                  <input
                    type="checkbox"
                    checked={isEnabled(module)}
                    disabled={!module.portable}
                    onchange={() => toggleModule(module)}
                    class="h-4 w-4 rounded border-neutral-700 bg-neutral-800"
                  />
                  {module.toggleLabel ?? "Enabled"}
                </label>
              {/if}
              <button
                type="button"
                onclick={() => openLog(module.id)}
                disabled={!job}
                class="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300 hover:border-sky-500 disabled:opacity-40"
              >
                Log
              </button>
            </div>

            <div class="mt-3 flex items-center gap-3">
              <div class="h-1.5 flex-1 overflow-hidden rounded-full bg-neutral-800">
                <div
                  class="h-full rounded-full transition-all {barClass(status)}"
                  style={`width: ${progress}%`}
                ></div>
              </div>
              <span class="w-10 text-right text-[11px] text-neutral-500">{progress}%</span>
            </div>
            <div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-neutral-500">
              <span>Started: {formatDateTime(stage?.started_at)}</span>
              <span>Duration: {formatDuration(duration)}</span>
              {#if stage?.message}<span class="truncate">{stage.message}</span>{/if}
            </div>
          </div>

          <details class="border-t border-neutral-800">
            <summary class="cursor-pointer px-4 py-2 text-xs font-medium text-neutral-400 hover:text-neutral-200">
              Parameters
            </summary>
            <div class="grid gap-3 px-4 pb-4 sm:grid-cols-2 lg:grid-cols-3">
              {#each module.fields as field}
                <div class="rounded-xl bg-neutral-950/60 p-3">
                  <div class="flex items-center justify-between gap-2">
                    <label class="text-[11px] uppercase tracking-wide text-neutral-500" for={`${module.id}-${field.key}`}>
                      {field.label}
                    </label>
                    {#if !field.implemented}
                      <span class="rounded bg-neutral-800 px-1.5 py-0.5 text-[9px] uppercase text-neutral-500">
                        later
                      </span>
                    {/if}
                  </div>
                  <div class="mt-2">
                    {#if field.type === "bool"}
                      <input
                        id={`${module.id}-${field.key}`}
                        type="checkbox"
                        checked={Boolean(config[field.key])}
                        disabled={!field.implemented}
                        onchange={(event) => setField(field.key, event.currentTarget.checked)}
                        class="h-4 w-4 rounded border-neutral-700 bg-neutral-800"
                      />
                    {:else if field.type === "number"}
                      <input
                        id={`${module.id}-${field.key}`}
                        type="number"
                        value={config[field.key]}
                        min={field.min}
                        max={field.max}
                        step={field.step}
                        disabled={!field.implemented}
                        oninput={(event) => setField(field.key, Number(event.currentTarget.value))}
                        class="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-sm text-neutral-100 disabled:opacity-50"
                      />
                    {:else if field.type === "color"}
                      <span class="flex gap-1">
                        <input
                          id={`${module.id}-${field.key}`}
                          type="color"
                          value={config[field.key]}
                          disabled={!field.implemented}
                          oninput={(event) => setField(field.key, event.currentTarget.value)}
                          class="h-9 w-12 rounded-lg border border-neutral-700 bg-neutral-950 p-1 disabled:opacity-50"
                        />
                        <input
                          type="text"
                          value={config[field.key]}
                          disabled={!field.implemented}
                          oninput={(event) => setField(field.key, event.currentTarget.value)}
                          class="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-xs text-neutral-100 disabled:opacity-50"
                        />
                      </span>
                    {:else if field.type === "select"}
                      <select
                        id={`${module.id}-${field.key}`}
                        value={config[field.key]}
                        disabled={!field.implemented}
                        onchange={(event) => setField(field.key, event.currentTarget.value)}
                        class="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-sm text-neutral-100 disabled:opacity-50"
                      >
                        {#each field.options ?? [] as option}
                          <option value={option.value}>{option.label}</option>
                        {/each}
                      </select>
                    {:else if field.type === "text"}
                      <input
                        id={`${module.id}-${field.key}`}
                        type="text"
                        value={config[field.key]}
                        disabled={!field.implemented}
                        oninput={(event) => setField(field.key, event.currentTarget.value)}
                        class="w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-sm text-neutral-100 disabled:opacity-50"
                      />
                    {:else if field.type === "textarea"}
                      <textarea
                        id={`${module.id}-${field.key}`}
                        rows="3"
                        value={config[field.key]}
                        disabled={!field.implemented}
                        oninput={(event) => setField(field.key, event.currentTarget.value)}
                        class="w-full resize-y rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-sm text-neutral-100 disabled:opacity-50"
                      ></textarea>
                    {:else if field.type === "targets"}
                      <div class="flex flex-wrap gap-3">
                        {#each targetOptions as target}
                          <label class="flex items-center gap-1.5 text-xs text-neutral-300">
                            <input
                              type="checkbox"
                              checked={(config.export_targets as string[]).includes(target.id)}
                              onchange={() => toggleTarget(target.id)}
                              class="h-4 w-4 rounded border-neutral-700 bg-neutral-800"
                            />
                            {target.label}
                          </label>
                        {/each}
                      </div>
                    {:else}
                      <p class="text-sm text-neutral-400">{String(config[field.key])}</p>
                    {/if}
                  </div>
                  {#if field.help}
                    <p class="mt-2 text-[10px] leading-4 text-neutral-500">{field.help}</p>
                  {/if}
                </div>
              {/each}
            </div>
            {#if module.id === "shorts"}
              <div class="px-4 pb-4">
                <div class="mb-3">
                  <FontManager onSelect={(family) => (config.caption_font_family = family)} />
                </div>
                <div class="mb-3">
                  <ImageManager
                    selected={String(config.overlay_asset || "")}
                    onSelect={(name) => (config.overlay_asset = name)}
                  />
                </div>
                <div class="mb-3">
                  <MusicManager
                    selected={String(config.music_asset || "")}
                    onSelect={(name) => (config.music_asset = name)}
                  />
                </div>
                <div class="mb-3">
                  <BrandTemplateManager {config} />
                </div>
                <div class="mb-3 grid gap-3 sm:grid-cols-2">
                  <ImageManager
                    label="Intro card"
                    selected={String(config.intro_asset || "")}
                    onSelect={(name) => (config.intro_asset = name)}
                  />
                  <ImageManager
                    label="Outro card"
                    selected={String(config.outro_asset || "")}
                    onSelect={(name) => (config.outro_asset = name)}
                  />
                </div>
                <div class="mb-3 rounded-xl border border-neutral-800 bg-neutral-950/60 p-3">
                  <div class="flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p class="text-[11px] uppercase tracking-wide text-neutral-500">Clip length presets</p>
                      <p class="mt-1 text-[10px] text-neutral-500">Sets the minimum and maximum Short duration.</p>
                    </div>
                    <div class="flex flex-wrap gap-1.5">
                      {#each durationPresets as duration}
                        <button
                          type="button"
                          onclick={() => setShortDuration(duration.min, duration.max)}
                          class="rounded-lg border border-neutral-700 px-2 py-1 text-[10px] text-neutral-300 transition hover:border-sky-500/60 hover:text-sky-200"
                        >
                          {duration.label}
                        </button>
                      {/each}
                    </div>
                  </div>
                </div>
                <CaptionPreview {config} />
              </div>
            {/if}
            {#if module.note}
              <p class="px-4 pb-4 text-[11px] leading-5 text-neutral-500">{module.note}</p>
            {/if}
          </details>
        </article>
        {/each}
      {/if}
    </section>

    <aside class="space-y-4">
      <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
        <h2 class="text-sm font-semibold">Run summary</h2>
        {#if job}
          <div class="mt-3 flex items-center gap-2 text-sm">
            <StatusIcon status={job.status === "queued" ? "pending" : job.status} size={18} />
            <span class="capitalize">{statusText(job.status)}</span>
          </div>
          <dl class="mt-3 space-y-2 text-xs text-neutral-400">
            <div><dt class="text-[10px] uppercase text-neutral-500">Started</dt><dd>{formatDateTime(job.started_at ?? job.created_at)}</dd></div>
            <div><dt class="text-[10px] uppercase text-neutral-500">Finished</dt><dd>{formatDateTime(job.finished_at)}</dd></div>
            <div><dt class="text-[10px] uppercase text-neutral-500">Duration</dt><dd>{formatDuration(jobDuration)}</dd></div>
            <div><dt class="text-[10px] uppercase text-neutral-500">Stages</dt><dd>{job.stages.filter((item) => item.status === "succeeded").length} ok · {job.stages.filter((item) => item.status === "failed").length} failed</dd></div>
          </dl>
          {#if artifacts.length > 0}
            <div class="mt-3 space-y-2">
              {#each artifacts as [target, path]}
                <a
                  class="block rounded-lg border border-neutral-800 bg-neutral-950/60 p-2 text-[11px] text-emerald-300 hover:border-emerald-500/50"
                  href={`/api/v1/jobs/${job.job_id}/artifacts/${target}`}
                  download
                >
                  <span class="block uppercase text-neutral-500">{target}</span>
                  <span class="break-all font-mono">{path}</span>
                </a>
              {/each}
            </div>
          {/if}
          {#if job.result?.shorts?.length}
            <div class="mt-3">
              <p class="text-[10px] uppercase tracking-wide text-neutral-500">Shorts</p>
              <div class="mt-2 space-y-2">
                {#each job.result.shorts as clip, index}
                  <div class="rounded-lg border border-neutral-800 bg-neutral-950/60 p-2 text-[11px]">
                    <a
                      class="block text-sky-300 hover:text-sky-200"
                      href={`/api/v1/jobs/${job.job_id}/shorts/${index}`}
                      download
                    >
                      <span class="block truncate">{clip.title}</span>
                      <span class="text-[10px] text-neutral-500">
                        {clip.duration_sec.toFixed(1)} s · {clip.aspect_ratio ?? "9:16"} · MP4
                        {#if clip.virality_score !== undefined}· score {clip.virality_score.toFixed(0)}{/if}
                        {#if clip.edit_count}· edit {clip.edit_count}{/if}
                      </span>
                    </a>
                    {#if clip.hook}
                      <p class="mt-1 line-clamp-2 text-[10px] text-amber-300/80">Hook: {clip.hook}</p>
                    {/if}
                    <div class="mt-2 flex gap-2">
                      <button
                        type="button"
                        onclick={() => openShortEditor(index, clip)}
                        class="rounded-md border border-neutral-700 px-2 py-1 text-[10px] text-neutral-300 hover:border-sky-500/60 hover:text-sky-200"
                      >
                        Edit
                      </button>
                      <a
                        class="rounded-md border border-neutral-700 px-2 py-1 text-[10px] text-neutral-300 hover:border-emerald-500/60 hover:text-emerald-200"
                        href={`/api/v1/jobs/${job.job_id}/shorts/${index}`}
                        download
                      >
                        Download
                      </a>
                    </div>
                  </div>
                {/each}
              </div>
            </div>
          {/if}
        {:else}
          <p class="mt-3 text-xs text-neutral-500">Run the pipeline to see timing, logs, and artifacts.</p>
        {/if}
      </section>

      <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
        <h2 class="text-sm font-semibold">Recent jobs</h2>
        {#if history.length === 0}
          <p class="mt-2 text-xs text-neutral-500">No jobs yet.</p>
        {:else}
          <div class="mt-3 space-y-2">
            {#each history.slice(0, 6) as entry}
              <button
                type="button"
                onclick={() => selectJob(entry)}
                class="flex w-full items-center gap-2 rounded-lg border border-transparent px-2 py-2 text-left text-xs hover:border-neutral-700 hover:bg-neutral-950/60"
              >
                <StatusIcon status={entry.status === "queued" ? "pending" : entry.status} />
                <span class="min-w-0 flex-1">
                  <span class="block truncate text-neutral-300">{entry.source.split(/[\\/]/).pop()}</span>
                  <span class="block text-[10px] text-neutral-500">{formatDateTime(entry.created_at)} · {formatDuration(entry.duration_ms)}</span>
                </span>
              </button>
            {/each}
          </div>
        {/if}
      </section>

      <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4 text-xs text-neutral-400">
        <h2 class="text-sm font-semibold text-neutral-200">System</h2>
        <p class="mt-3">Version: <span class="font-mono text-neutral-300">{system?.version ?? "—"}</span></p>
        <p class="mt-1">FFmpeg: <span class="break-all font-mono text-neutral-300">{system?.ffmpeg ?? "missing"}</span></p>
        <p class="mt-1">Home: <span class="break-all font-mono text-neutral-300">{system?.home ?? "—"}</span></p>
        <p class="mt-1">Roots: <span class="break-all font-mono text-neutral-300">{system?.allowed_roots.join(", ") || "—"}</span></p>
      </section>
    </aside>
  </div>

  <section class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-5">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 class="text-sm font-semibold">Inspector</h2>
        <p class="mt-1 text-xs text-neutral-400">
          Transcript and retake decisions from the current job.
        </p>
      </div>
      <span class="rounded-full bg-neutral-800 px-3 py-1 text-[11px] text-neutral-400">
        {job?.result ? `${job.result.video_segment_count ?? 0} segments` : "No run"}
      </span>
    </div>
    {#if jobState}
      <div class="mt-4 grid gap-2 text-xs text-neutral-300 sm:grid-cols-4">
        <p>Sentences: {jobState.transcript.length}</p>
        <p>Culled: {jobState.retake_culls.length}</p>
        <p>Restored: {jobState.retake_guard_restores.length}</p>
        <p>Overrides: {Object.keys(overrides).length}</p>
      </div>

      <div class="mt-4 flex flex-wrap items-center justify-between gap-2">
        <p class="text-[11px] uppercase tracking-wide text-neutral-500">Manual overrides</p>
        <button
          type="button"
          onclick={applyOverrides}
          disabled={Object.keys(overrides).length === 0 || active}
          class="rounded-lg bg-sky-600 px-3 py-1.5 text-xs font-medium text-white disabled:opacity-40"
        >
          Apply overrides
        </button>
      </div>
      <div class="mt-2 max-h-80 space-y-1 overflow-auto rounded-xl border border-neutral-800 bg-neutral-950/50 p-2">
        {#each jobState.transcript.slice(0, 200) as sentence}
          {@const action = effectiveAction(sentence.id)}
          <div class="flex flex-wrap items-center gap-2 rounded-lg px-2 py-1.5 text-xs hover:bg-neutral-900/60">
            <span class="w-8 shrink-0 font-mono text-[10px] text-neutral-600">#{sentence.id}</span>
            <span class="min-w-0 flex-1 {action === 'discard' ? 'text-rose-300 line-through' : 'text-neutral-300'}">
              {sentence.text}
            </span>
            <button
              type="button"
              onclick={() => setOverride(sentence.id, "keep")}
              class="rounded px-2 py-0.5 text-[10px] {action === 'keep' ? 'bg-emerald-500/15 text-emerald-300' : 'text-neutral-500 hover:text-emerald-300'}"
            >
              Keep
            </button>
            <button
              type="button"
              onclick={() => setOverride(sentence.id, "discard")}
              class="rounded px-2 py-0.5 text-[10px] {action === 'discard' ? 'bg-rose-500/15 text-rose-300' : 'text-neutral-500 hover:text-rose-300'}"
            >
              Discard
            </button>
          </div>
        {/each}
      </div>
      {#if jobState.transcript.length > 200}
        <p class="mt-2 text-[10px] text-neutral-500">Showing the first 200 sentences.</p>
      {/if}
      {#if jobState.retake_guard_restores.length > 0}
        <div class="mt-4">
          <p class="text-[11px] uppercase tracking-wide text-neutral-500">Guard restorations</p>
          <ul class="mt-2 space-y-1 text-xs text-emerald-300">
            {#each jobState.retake_guard_restores as id}
              <li>{sentenceText(id)}</li>
            {/each}
          </ul>
        </div>
      {/if}
      {#if job?.result?.warnings?.length}
        <ul class="mt-3 list-disc pl-5 text-xs text-amber-300">
          {#each job.result.warnings as warning}
            <li>{warning}</li>
          {/each}
        </ul>
      {/if}
    {:else if job?.result}
      <div class="mt-4 grid gap-2 text-xs text-neutral-300 sm:grid-cols-3">
        <p>Speech intervals: {job.result.speech_interval_count ?? "—"}</p>
        <p>Segments: {job.result.video_segment_count ?? "—"}</p>
        <p>Elapsed: {job.result.elapsed_seconds?.toFixed(2) ?? "—"} s</p>
      </div>
    {:else}
      <p class="mt-4 text-xs text-neutral-500">
        Start a run to populate transcript decisions and warnings.
      </p>
    {/if}
  </section>

  <footer class="pb-4 text-xs text-neutral-500">
    <p>
      Local only. The server binds to 127.0.0.1. Every control shown is wired; future modules are
      marked later.
    </p>
  </footer>
  </div>
</div>

<PathPicker
  open={pickerKind !== null}
  mode={pickerMode()}
  title={pickerTitle()}
  extensions={pickerExtensions()}
  initialPath={pickerInitialPath()}
  suggestedName={pickerKind === "output" && !outputTouched ? baseName(output) : ""}
  onclose={() => (pickerKind = null)}
  onselect={handlePick}
/>

{#if shortEditor && job}
  <ShortEditor
    jobId={job.job_id}
    index={shortEditor.index}
    short={shortEditor.short}
    open={shortEditor !== null}
    allowExternal={Boolean(config.allow_external_services)}
    allowedHosts={String(config.allowed_external_hosts || "")}
    onClose={() => (shortEditor = null)}
    onSaved={savedShort}
  />
{/if}

<LogDrawer jobId={job?.job_id ?? null} module={logModule} open={logOpen} onclose={() => (logOpen = false)} />
