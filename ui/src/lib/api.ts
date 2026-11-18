import { ApiError, raiseApiError, request } from "./api/client";

export type JobStatus =
  | "queued"
  | "paused"
  | "running"
  | "waiting_approval"
  | "waiting_input"
  | "succeeded"
  | "failed"
  | "cancelled"
  | "answered";
export type StageStatus = "pending" | "running" | "succeeded" | "failed" | "cancelled";

export interface SystemInfo {
  ok: boolean;
  version: string;
  home: string;
  allowed_roots: string[];
  ffmpeg: string | null;
  ffprobe: string | null;
  settings_error?: string;
  database_error?: string;
}

export interface LocalModel {
  id: string;
  label: string;
  size_mb: number;
  kind: string;
  capability: string;
  used_by: string[];
  license: string;
  source: string;
  installed: boolean;
  path: string;
  custom?: boolean;
}

export interface ServiceProcessInfo {
  pid: number;
  cmdline: string[];
  ports: number[];
  port: number | null;
  version: string | null;
  url: string | null;
  kind: string;
  current: boolean;
  protected: boolean;
}

export interface ServicesResponse {
  ok: boolean;
  pid: number;
  port: number | null;
  log_path: string;
  services: ServiceProcessInfo[];
}

export interface FsRoot {
  name: string;
  path: string;
  exists: boolean;
  writable: boolean;
}

export interface FsBreadcrumb {
  name: string;
  path: string;
}

export interface FsEntry {
  name: string;
  path: string;
  kind: "file" | "directory";
  size_bytes: number | null;
  modified_at: string | null;
  extension: string | null;
  selectable: boolean;
  is_symlink: boolean;
}

export interface FsListing {
  ok: boolean;
  path: string;
  name: string;
  parent: FsBreadcrumb | null;
  breadcrumbs: FsBreadcrumb[];
  roots: FsRoot[];
  entries: FsEntry[];
  truncated: boolean;
  can_write: boolean;
  mode: "file" | "directory";
}

export interface ImportedMedia {
  ok: boolean;
  path: string;
  media: ProbedMedia["media"];
}

export interface ProbedMedia {
  ok: boolean;
  path: string;
  name: string;
  size_bytes: number;
  media: {
    source_path: string;
    duration_frames: number;
    fps_num: number;
    fps_den: number;
    width: number;
    height: number;
    audio_sample_rate: number;
    start_timecode_frames: number;
  };
}

export interface JobOptions {
  vad_engine: string;
  noise_db: number;
  min_silence_ms: number;
  min_speech_ms: number;
  speech_threshold: number;
  speech_pad_before_ms: number;
  speech_pad_after_ms: number;
  jcut: boolean;
  lcut: boolean;
  offset_ms: number;
  crossfade_ms: number;
  handle_check: boolean;
  zooms: boolean;
  zoom_mode: string;
  punch_in_scale: number;
  anchor_point: string;
  progressive_zoom: boolean;
  pan_direction: string;
  dialect: "1.9" | "1.10";
  export_targets: string[];
  transcript: string | null;
  cull_retakes: boolean;
  strictness: string;
  retake_strategy: string;
  context_window: number;
  llm_base_url: string | null;
  llm_model: string;
  transcribe?: boolean;
  asr_base_url?: string | null;
  asr_model?: string;
  asr_language?: string;
  whisper_engine?: string;
  whisper_model_size?: string;
  whisper_device?: string;
  whisper_compute_type?: string;
  whisper_vad_filter?: boolean;
  whisper_model?: string | null;
  faster_whisper_model?: string | null;
  brand_template?: string | null;
  project_template?: string | null;
  fade_in_ms?: number;
  fade_out_ms?: number;
  fade_curve?: string;
  zoom_min_scale?: number;
  zoom_max_scale?: number;
  shorts?: boolean;
  shorts_count?: number;
  shorts_min_count?: number;
  shorts_min_sec?: number;
  shorts_max_sec?: number;
  shorts_subtitles?: boolean;
  shorts_selection_mode?: string;
  shorts_prompt?: string;
  shorts_reprompt?: string;
  shorts_prompt_mode?: string;
  shorts_hook_mode?: string;
  shorts_reframe_mode?: string;
  shorts_audio_energy_boost?: boolean;
  shorts_scene_change_boost?: boolean;
  shorts_remove_fillers?: boolean;
  shorts_filler_words?: string[];
  shorts_aspect?: string;
  shorts_resolution?: number;
  shorts_source_start_sec?: number;
  shorts_source_end_sec?: number | null;
  allow_external_services?: boolean;
  allowed_external_hosts?: string[];
  audio_enhance?: boolean;
  audio_highpass_hz?: number;
  audio_denoise?: boolean;
  audio_denoise_db?: number;
  audio_noise_floor_db?: number;
  audio_loudnorm?: boolean;
  audio_target_lufs?: number;
  audio_true_peak_db?: number;
  overlay_enabled?: boolean;
  overlay_asset?: string;
  overlay_position?: string;
  overlay_margin_px?: number;
  overlay_width_ratio?: number;
  overlay_opacity?: number;
  music_enabled?: boolean;
  music_asset?: string;
  music_volume?: number;
  music_ducking?: boolean;
  music_fade_in_ms?: number;
  music_fade_out_ms?: number;
  intro_enabled?: boolean;
  intro_asset?: string;
  intro_duration_sec?: number;
  outro_enabled?: boolean;
  outro_asset?: string;
  outro_duration_sec?: number;
  caption_font_family?: string;
  caption_font_size?: number;
  caption_font_weight?: string;
  caption_italic?: boolean;
  caption_uppercase?: boolean;
  caption_primary_color?: string;
  caption_highlight_color?: string;
  caption_outline_color?: string;
  caption_outline_width?: number;
  caption_shadow_color?: string;
  caption_shadow_offset?: number;
  caption_shadow_opacity?: number;
  caption_background_color?: string;
  caption_background_opacity?: number;
  caption_background_padding?: number;
  caption_alignment?: number;
  caption_position_x?: number;
  caption_position_y?: number;
  caption_max_width?: number;
  caption_animation?: string;
  caption_word_timing?: string;
}

export interface JobStage {
  id: string;
  module: string;
  label: string;
  status: StageStatus;
  progress: number;
  message: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  error: string | null;
}

export interface ShortClip {
  title: string;
  path: string;
  duration_sec: number;
  start_sec: number;
  end_sec: number;
  sentence_ids: number[];
  pieces?: number[][];
  hook?: string | null;
  hook_sentence_id?: number | null;
  hook_start_sample?: number | null;
  hook_end_sample?: number | null;
  crop_focus_x?: number;
  crop_focus_y?: number;
  virality_score?: number;
  score_breakdown?: Record<string, number>;
  arc?: string;
  arc_reason?: string;
  curation_source?: string;
  crop_keyframes?: number[][];
  aspect_ratio?: string;
  width?: number;
  height?: number;
  subtitles?: string;
  caption_style?: Record<string, unknown>;
  metadata?: Record<string, ShortMetadata>;
  thumbnail?: string;
  thumbnails?: ShortThumbnail[];
  voiceover?: ShortVoiceover;
  dubbing?: ShortDubbing;
  analysis?: ShortAnalysis;
  analysis_llm?: ShortVisionAnalysis;
  edited_at?: string;
  edit_count?: number;
  previous_path?: string;
}

export interface ShortVisionAnalysis {
  objects: string[];
  scene: string;
  people: number;
  mood: string;
  energy: number;
  confidence: number;
  evidence: string;
  frame_count: number;
  provider: string;
  model: string;
}

export interface ShortAnalysis {
  audio: { label: string; rms: number; zcr: number; variation: number };
  visual: {
    motion: { x: number; y: number; coverage: number } | null;
    face_count: number | null;
    face_focus_x: number | null;
    provider: string;
  };
  caveats: string[];
}

export interface ShortDubbing {
  source_text: string;
  translated_text: string;
  target_language: string;
  audio_path: string;
  path: string;
  provider: string;
  model: string;
  voice: string;
  original_volume: number;
}

export interface ShortVoiceover {
  text: string;
  audio_path: string;
  path: string;
  provider: string;
  model: string;
  voice: string;
  volume: number;
  original_volume: number;
}

export interface ShortThumbnail {
  path: string;
  title: string;
  time_sec: number;
  width: number;
  height: number;
}

export interface ShortMetadata {
  title: string;
  description: string;
  hashtags: string[];
  platform: string;
  tone: string;
  character_limits: { title: number; description: number };
}

export interface ShortEditPayload {
  title?: string;
  start_sec?: number;
  end_sec?: number;
  aspect_ratio?: "9:16" | "1:1" | "16:9";
  burn_subtitles?: boolean;
  caption_style?: Record<string, unknown>;
}

export type HiltQuestionType = "text" | "textarea" | "choice" | "boolean" | "number" | "file";

export interface HiltQuestion {
  id: string;
  label: string;
  type: HiltQuestionType;
  required: boolean;
  options: unknown[];
  default: unknown;
  placeholder: string;
  help: string;
  accept: string[];
  max_mb: number;
}

export interface HiltFileRequest {
  id: string;
  label: string;
  required: boolean;
  accept: string[];
  max_mb: number;
  target: string;
  allow_replace: boolean;
  help: string;
}

export interface HiltArtifact {
  id: string;
  label: string;
  path: string;
  kind: string;
  description: string;
  exists: boolean;
  size_bytes: number;
  download_url?: string;
}

export interface HiltAttachment {
  request_id: string;
  original_name: string;
  stored_path: string;
  size_bytes: number;
  sha256: string;
  content_type: string;
}

export interface HiltResponse {
  interaction_id: string;
  action: "approve" | "reject" | "submit";
  answers: Record<string, unknown>;
  comment: string;
  attachments: HiltAttachment[];
  responder: string;
  response_channel: string;
  received_at: string;
  resumed_job_id: string;
}

export interface HiltInteraction {
  interaction_id: string;
  job_id: string;
  recipe_id: string;
  step_id: string;
  gate_id: string;
  kind: "approval" | "question" | "files" | "review";
  title: string;
  description: string;
  summary?: string;
  checklist?: string[];
  severity?: "info" | "warning" | "critical";
  next_step?: string;
  group?: string;
  approve_label: string;
  reject_label: string;
  questions: HiltQuestion[];
  files: HiltFileRequest[];
  artifacts: HiltArtifact[];
  channels: string[];
  status: string;
  created_at: string;
  expires_at: string;
  reminder_at: string;
  token_required: boolean;
  response_url: string;
  files_url: string;
  response?: HiltResponse | null;
  expired?: boolean;
}

export interface HiltPending {
  job_id: string;
  job_status: JobStatus;
  job_message: string;
  interaction: HiltInteraction;
}

export interface HiltChannelStatus {
  id: string;
  label: string;
  enabled: boolean;
  available: boolean;
  detail: string;
}

export interface Job {
  job_id: string;
  status: JobStatus;
  priority?: number;
  progress: number;
  stage: string;
  message: string;
  source: string;
  output: string;
  timeline_ready?: boolean;
  options: Partial<JobOptions>;
  result: {
    ok: boolean;
    mode?: string;
    recipe_id?: string;
    video_segment_count?: number;
    speech_interval_count?: number;
    transcript_sentence_count?: number;
    retake_cull_count?: number;
    retake_restored_count?: number;
    transcript_source?: string;
    warnings?: string[];
    artifacts?: Record<string, string>;
    cache_hits?: string[];
    cache_misses?: string[];
    step_runs?: StepRun[];
    variants?: Array<{
      name: string;
      output: string;
      summary: Record<string, unknown>;
    }>;
    shorts?: ShortClip[];
    broll_plan?: Record<string, Record<string, unknown>[]>;
    speaker_count?: number;
    diarization_method?: string;
    state_path?: string;
    report_path?: string;
    elapsed_seconds?: number;
    step_progress?: Record<string, number>;
  } | null;
  error: {
    ok: boolean;
    code: string;
    message: string;
    gate_id?: string;
    title?: string;
    step_id?: string;
    command?: string;
    stderr?: string;
    returncode?: number;
    signal?: number;
  } | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  step_progress?: Record<string, number>;
  log_count: number;
  stages: JobStage[];
  interaction?: HiltInteraction | null;
}

export interface RecipeStep {
  id: string;
  type: string;
  needs: string[];
  inputs?: Record<string, string>;
  media_override?: string;
  output_mode?: "pipeline" | "folder";
  output_dir?: string;
  enabled: boolean;
  params: Record<string, unknown>;
}

export interface StepPort {
  id: string;
  label: string;
  type: string;
  required?: boolean;
}

export interface RecipeNodeUi {
  x: number;
  y: number;
  expanded: boolean;
  pinned: boolean;
  width: number;
}

export interface RecipeGroup {
  id: string;
  label: string;
  description: string;
  color: string;
  x: number;
  y: number;
  width: number;
  height: number;
  nodes: string[];
}

export interface RecipeUi {
  version: number;
  viewport: { x: number; y: number; zoom: number };
  nodes: Record<string, RecipeNodeUi>;
  groups?: RecipeGroup[];
}

export interface Recipe {
  schema_version: 1;
  id: string;
  name: string;
  description: string;
  llm: {
    provider: "none" | "openai_compatible" | "opencode";
    base_url: string | null;
    model: string;
    api_key_env: string;
    timeout_seconds: number;
  };
  ui?: RecipeUi;
  variables?: Record<
    string,
    {
      type: "string" | "number" | "boolean" | "enum";
      default?: unknown;
      description?: string;
      options?: unknown[];
      required?: boolean;
    }
  >;
  profiles?: Record<string, Record<string, unknown>>;
  variants?: Array<Record<string, unknown>>;
  steps: RecipeStep[];
}

export interface StepManifest {
  type: string;
  title: string;
  description: string;
  requires: string[];
  produces: string[];
  params_schema: Record<string, unknown>;
  inputs?: StepPort[];
  outputs?: StepPort[];
  status?: "available" | "partial" | "planned";
  icon?: string;
  color?: string;
  bypass?: boolean;
}

export interface RecipeSummary {
  id: string;
  name: string;
  description: string;
  source: string;
  favorite: boolean;
  last_used_at: string;
  use_count: number;
  tags: string[];
}

export interface AppSettings {
  schema_version: 1;
  runtime: {
    host: string;
    port: number;
    open_browser: boolean;
    log_level: "debug" | "info" | "warning" | "error";
    max_jobs: number;
    history: number;
    locale: string;
  };
  paths: {
    allowed_roots: string[];
    ffmpeg: string;
    ffprobe: string;
    cache_dir: string;
    models_dir: string;
    output_root: string;
    temp_dir: string;
  };
  models: {
    defaults: Record<string, string>;
    device: "cpu" | "cuda" | "auto";
    compute_type: string;
    threads: number;
    hf_token_env: string;
  };
  automation: {
    scheduler_interval_seconds: number;
    max_retries: number;
    retry_backoff_seconds: number;
    enabled: boolean;
  };
  quality: {
    target_lufs: number;
    true_peak_db: number;
    vmaf_threshold: number;
    proxy_height: number;
  };
  ui: {
    theme: "dark" | "light" | "system" | "high-contrast";
    density: "comfortable" | "compact";
    timeline_snap: boolean;
  };
  llm: {
    temperature: number;
    timeout_seconds: number;
    max_tokens: number;
    retries: number;
    json_mode: boolean;
  };
  speech: {
    engine: "auto" | "faster-whisper" | "whisper-cli";
    quality_profile:
      | "auto"
      | "custom"
      | "fast"
      | "balanced"
      | "quality"
      | "vulkan"
      | "remote";
    language: string;
    device: "cpu" | "cuda" | "auto";
    compute_type: string;
    beam_size: number;
    cpu_threads: number;
    word_timestamps: "auto" | "always" | "off";
    condition_on_previous_text: boolean;
    vad_filter: boolean;
    remote_base_url: string;
    remote_model: string;
    remote_api_key_env: string;
    diarization_model: string;
  };
  tts: {
    provider: "openai_compatible" | "piper";
    voice: string;
    model: string;
    format: "mp3" | "wav";
    speed: number;
  };
  stock: {
    provider: "local" | "pexels";
    pexels_key_env: string;
    pixabay_key_env: string;
    openverse_token_env: string;
    asset_dir: string;
    youtube_fair_use_seconds: number;
    youtube_max_per_video: number;
    allow_fair_use: boolean;
  };
  translation: {
    target_language: string;
    source_language: string;
  };
  notifications: {
    enabled: boolean;
    ui_level: "off" | "required" | "important" | "all";
    desktop_level: "off" | "required" | "important" | "all";
    notify_hitl: boolean;
    notify_job_failed: boolean;
    notify_job_finished: boolean;
    notify_job_cancelled: boolean;
    notify_warnings: boolean;
    notify_system: boolean;
    default_channels: string[];
    base_url: string;
    interaction_ttl_hours: number;
    reminder_hours: number;
    local: { enabled: boolean; desktop: boolean };
    email: {
      enabled: boolean;
      smtp_host: string;
      smtp_port: number;
      smtp_starttls: boolean;
      smtp_ssl: boolean;
      smtp_user: string;
      smtp_password_secret: string;
      from_address: string;
      to_addresses: string[];
      imap_host: string;
      imap_port: number;
      imap_ssl: boolean;
      imap_user: string;
      imap_password_secret: string;
      imap_folder: string;
      allowed_senders: string[];
      poll_seconds: number;
      max_attachment_mb: number;
    };
    slack: {
      enabled: boolean;
      mode: "webhook" | "bot";
      webhook_secret: string;
      bot_token_secret: string;
      signing_secret: string;
      channel: string;
      allowed_users: string[];
      poll_seconds: number;
      use_events: boolean;
    };
    signal: {
      enabled: boolean;
      api_url: string;
      number: string;
      recipients: string[];
      allowed_senders: string[];
      password_secret: string;
      poll_seconds: number;
    };
  };
  intelligence: {
    enabled: boolean;
    provider_order: string[];
    allow_network: boolean;
    budget_usd: number;
    cache_enabled: boolean;
    default_timeout_seconds: number;
    opencode_base_url: string;
    opencode_token_env: string;
    opencode_model: string;
    deepseek_base_url: string;
    deepseek_model: string;
    deepseek_api_key_env: string;
    tasks: Record<string, Record<string, unknown>>;
  };
  search: {
    enabled: boolean;
    providers: string[];
    local_paths: string[];
    seed_urls: string[];
    searxng_url: string;
    wikipedia_language: string;
    max_results: number;
    fetch_pages: number;
    allow_network: boolean;
    timeout_seconds: number;
    max_bytes: number;
    cache_ttl_hours: number;
  };
}

export interface ServiceDefinition {
  id: string;
  name: string;
  command: string;
  args: string[];
  cwd: string;
  env: Record<string, string>;
  port: number;
  health_url: string;
  autostart: boolean;
  enabled: boolean;
}

export interface ServiceDefinitionStatus {
  id: string;
  name: string;
  status: "stopped" | "running" | "exited";
  pid: number | null;
  healthy: boolean | null;
  port: number;
  started_at: string;
  last_error: string;
}

export interface RecipeSchedule {
  id: string;
  kind: "once" | "interval" | "watch";
  recipe_id: string;
  source: string;
  output: string;
  interval_seconds: number;
  watch_dir: string;
  pattern: string;
  enabled: boolean;
  last_run: string;
  status: string;
  last_error: string;
  created_at: string;
  seen_paths: string[];
}

export interface BatchItem {
  source: string;
  output: string;
  status: "pending" | "running" | "succeeded" | "failed" | "cancelled";
  job_id: string | null;
  message: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface Batch {
  batch_id: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  message: string;
  source_dir: string;
  output_root: string;
  recipe_id: string;
  resume: boolean;
  total: number;
  completed: number;
  failed: number;
  current_job_id: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  items: BatchItem[];
}

export interface RunRecord {
  job_id: string;
  status: string;
  recipe_id: string;
  created_at: string;
  started_at: string | null;
  duration_ms: number;
  step_runs: StepRun[];
  cache_hits: string[];
  cache_misses: string[];
  artifacts: Record<string, string>;
  warnings: string[];
  error?: { ok: boolean; code: string; message: string } | null;
  message?: string;
}

export interface StepRun {
  id: string;
  type: string;
  status: "cached" | "executed" | "skipped";
  elapsed_ms: number;
  progress?: number;
  fingerprint: string;
  outputs: string[];
}

export interface PublishTarget {
  name: string;
  description: string;
  webhook_url: string;
  secret_name: string;
  enabled: boolean;
}

export interface PublishQueueItem {
  id: string;
  target: string;
  asset_path: string;
  title: string;
  description: string;
  hashtags: string[];
  platform: string;
  scheduled_at: string;
  status: string;
  attempts: number;
  last_error: string;
}

export interface ProjectTemplate {
  name: string;
  description: string;
  options: Record<string, unknown>;
}

export interface BrandTemplate {
  name: string;
  description: string;
  caption_style: Record<string, unknown>;
  overlay: Record<string, unknown>;
  music: Record<string, unknown>;
  intro_outro: Record<string, unknown>;
}

export interface MusicAsset {
  file: string;
  name: string;
  size_bytes: number;
}

export interface ImageAsset {
  file: string;
  name: string;
  size_bytes: number;
}

export interface FontAsset {
  file: string;
  name: string;
  family: string;
  size_bytes: number;
}

export interface Capability {
  id: string;
  name: string;
  category: string;
  status: "available" | "blocked" | "partial" | "planned";
  description: string;
  api: string;
  mcp: string;
  requires: string[];
  reason?: string;
}

export interface CapabilitiesResponse {
  ok: boolean;
  external_services_allowed: boolean;
  capabilities: Capability[];
}

export interface Sentence {
  id: number;
  start_sample: number;
  end_sample: number;
  text: string;
  words: unknown[];
}

export interface JobState {
  transcript: Sentence[];
  retake_culls: number[];
  retake_guard_restores: number[];
  vad_intervals: { start_sample: number; end_sample: number }[];
  video_segments: unknown[];
  audio_segments: unknown[];
}

export interface LogLine {
  timestamp: string;
  level: "debug" | "info" | "warning" | "error";
  module: string;
  message: string;
}

export { ApiError, formatBackendDetail, describeError } from "./api/client";

export interface StyleSummary {
  style_id: string;
  name: string;
  aspect_ratio: string;
  summary: string;
  file_path: string;
  updated_at: string;
}

export async function listStyles(): Promise<StyleSummary[]> {
  const response = await request<{ ok: boolean; styles: StyleSummary[] }>("/api/v1/styles");
  return response.styles ?? [];
}

export interface WorkflowSummary {
  workflow_id: string;
  name: string;
  description: string;
  aspect_ratio: string;
  platforms: string[];
  steps: number;
  file_path: string;
  updated_at: string;
}

export interface WorkflowDetail {
  ok: boolean;
  workflow: Record<string, unknown>;
  markdown: string;
  file: string;
}

export interface StyleDetail {
  ok: boolean;
  style: Record<string, unknown>;
  markdown: string;
  file: string;
}

export async function listWorkflows(): Promise<WorkflowSummary[]> {
  const response = await request<{ ok: boolean; workflows: WorkflowSummary[] }>(
    "/api/v1/system/opencode/workflows"
  );
  return response.workflows ?? [];
}

export async function getWorkflow(workflowId: string): Promise<WorkflowDetail> {
  return request<WorkflowDetail>(
    `/api/v1/system/opencode/workflows/${encodeURIComponent(workflowId)}`
  );
}

export async function saveWorkflow(payload: {
  workflow_id?: string;
  name?: string;
  markdown_content?: string;
  workspace_dir?: string;
  overwrite?: boolean;
}): Promise<{ ok: boolean; workflow_id: string }> {
  return request("/api/v1/system/opencode/workflows", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function deleteWorkflow(workflowId: string): Promise<{ ok: boolean }> {
  return request(`/api/v1/system/opencode/workflows/${encodeURIComponent(workflowId)}`, {
    method: "DELETE"
  });
}

export async function duplicateWorkflow(
  workflowId: string,
  payload: { new_id?: string; name?: string }
): Promise<{ ok: boolean; workflow_id: string }> {
  return request(
    `/api/v1/system/opencode/workflows/${encodeURIComponent(workflowId)}/duplicate`,
    { method: "POST", body: JSON.stringify(payload) }
  );
}

export async function restoreWorkflow(workflowId: string): Promise<{ ok: boolean }> {
  return request(
    `/api/v1/system/opencode/workflows/${encodeURIComponent(workflowId)}/restore`,
    { method: "POST" }
  );
}

export async function getStyle(styleId: string): Promise<StyleDetail> {
  return request<StyleDetail>(`/api/v1/styles/${encodeURIComponent(styleId)}`);
}

export async function saveStyleMarkdown(payload: {
  style_id?: string;
  name?: string;
  markdown_content?: string;
  workspace_dir?: string;
  overwrite?: boolean;
}): Promise<{ ok: boolean; style_id: string }> {
  return request("/api/v1/styles", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function deleteStyle(styleId: string): Promise<{ ok: boolean }> {
  return request(`/api/v1/styles/${encodeURIComponent(styleId)}`, { method: "DELETE" });
}

export async function getAgentsFile(workspaceDir: string): Promise<{ ok: boolean; content: string; path: string }> {
  return request(
    `/api/v1/system/opencode/agents?workspace_dir=${encodeURIComponent(workspaceDir)}`
  );
}

export async function saveAgentsFile(
  workspaceDir: string,
  content: string
): Promise<{ ok: boolean; path: string }> {
  return request("/api/v1/system/opencode/agents", {
    method: "PUT",
    body: JSON.stringify({ workspace_dir: workspaceDir, content })
  });
}

export async function restoreAgentsFile(
  workspaceDir: string
): Promise<{ ok: boolean; path: string; content: string }> {
  return request("/api/v1/system/opencode/agents/restore", {
    method: "POST",
    body: JSON.stringify({ workspace_dir: workspaceDir, content: "" })
  });
}

export interface OpenCodeBootstrapRequest {
  target_dir: string;
  mcp_profile: "opencode" | "core" | "decupagem" | "broll" | "audio" | "vision" | "full";
  register_global_opencode?: boolean;
  overwrite?: boolean;
  include_sample_project?: boolean;
  register_root?: boolean;
  prompts?: boolean;
  workflow_ids?: string[];
  style_ids?: string[];
}

export interface OpenCodeBootstrapResult {
  ok: boolean;
  status: "ok" | "warning";
  target_dir: string;
  created_files: string[];
  skipped_files: string[];
  copied_styles: string[];
  copied_workflows?: string[];
  mcp_servers: string[];
  launch_command: string;
  sample_project: Record<string, unknown>;
  registered_root: boolean;
  warnings: string[];
}

export async function bootstrapOpenCode(
  payload: OpenCodeBootstrapRequest
): Promise<OpenCodeBootstrapResult> {
  return request<OpenCodeBootstrapResult>("/api/v1/system/bootstrap/opencode", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function listServices(): Promise<ServicesResponse> {
  return request<ServicesResponse>("/api/v1/services");
}

export async function getServiceLog(lines = 200): Promise<{ ok: boolean; path: string; text: string }> {
  return request(`/api/v1/services/log?lines=${lines}`);
}

export async function cleanupServices(): Promise<{
  ok: boolean;
  stopped: number[];
  failed: number[];
}> {
  return request("/api/v1/services/cleanup", { method: "POST" });
}

export async function stopServicePid(pid: number): Promise<{ ok: boolean; stopped: boolean; pid: number }> {
  return request(`/api/v1/services/${pid}/stop`, { method: "POST" });
}

export async function restartService(): Promise<void> {
  await request("/api/v1/system/restart", { method: "POST" });
}

export async function stopService(): Promise<void> {
  await request("/api/v1/system/shutdown", { method: "POST" });
}

export async function listLocalModels(): Promise<LocalModel[]> {
  const response = await request<{ ok: boolean; models: LocalModel[] }>("/api/v1/models");
  return response.models;
}

export async function registerLocalModel(payload: {
  id: string;
  label: string;
  capability: string;
  path: string;
  kind?: string;
  license?: string;
}): Promise<void> {
  await request("/api/v1/models/local", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function verifyLocalModel(
  modelId: string
): Promise<{ id: string; ok: boolean; path: string; invalid?: string[] }> {
  const response = await request<{
    ok: boolean;
    verification: { id: string; ok: boolean; path: string; invalid?: string[] };
  }>(`/api/v1/models/${encodeURIComponent(modelId)}/verify`, { method: "POST" });
  return response.verification;
}

export async function updateLocalModel(modelId: string): Promise<void> {
  await request(`/api/v1/models/${encodeURIComponent(modelId)}/update`, {
    method: "POST",
    body: JSON.stringify({ allow_external_services: true })
  });
}

export async function removeLocalModel(modelId: string): Promise<void> {
  await request(`/api/v1/models/${encodeURIComponent(modelId)}`, { method: "DELETE" });
}

export async function startModelDownload(modelId: string): Promise<ModelDownload> {
  const response = await request<{ ok: boolean; download: ModelDownload }>(
    `/api/v1/models/${encodeURIComponent(modelId)}/download`,
    {
      method: "POST",
      body: JSON.stringify({ allow_external_services: true })
    }
  );
  return response.download;
}

export async function listModelDownloads(): Promise<ModelDownload[]> {
  const response = await request<{ ok: boolean; downloads: ModelDownload[] }>(
    "/api/v1/models/downloads"
  );
  return response.downloads;
}

export async function cancelModelDownload(modelId: string): Promise<void> {
  await request(`/api/v1/models/downloads/${encodeURIComponent(modelId)}`, {
    method: "DELETE"
  });
}

export async function listProviders(): Promise<{
  providers: ProviderConfig[];
  fallbacks: Record<string, ProviderConfig[]>;
  secret_backend?: string;
}> {
  return request("/api/v1/providers");
}

export async function setProviderSecret(providerId: string, value: string): Promise<void> {
  await request(`/api/v1/providers/${encodeURIComponent(providerId)}/secret`, {
    method: "POST",
    body: JSON.stringify({ value })
  });
}

export async function deleteProviderSecret(providerId: string): Promise<void> {
  await request(`/api/v1/providers/${encodeURIComponent(providerId)}/secret`, {
    method: "DELETE"
  });
}

export async function saveProvider(provider: ProviderConfig): Promise<ProviderConfig> {
  const response = await request<{ ok: boolean; provider: ProviderConfig }>(
    `/api/v1/providers/${encodeURIComponent(provider.id)}`,
    { method: "PUT", body: JSON.stringify(provider) }
  );
  return response.provider;
}

export async function deleteProvider(providerId: string): Promise<void> {
  await request(`/api/v1/providers/${encodeURIComponent(providerId)}`, { method: "DELETE" });
}

export async function setDefaultProvider(providerId: string): Promise<void> {
  await request(`/api/v1/providers/${encodeURIComponent(providerId)}/default`, {
    method: "POST"
  });
}

export interface ProviderTestResult {
  ok: boolean;
  status_code: number | null;
  code?: string;
  message: string;
  hint?: string;
  provider_message?: string;
  secret_present: boolean;
  secret_source?: "request" | "environment" | "stored" | "missing";
  latency_ms?: number;
  mode?: string;
  endpoint?: string;
}

export async function testProvider(payload: {
  provider_id?: string;
  base_url?: string;
  api_key_env?: string;
  secret_value?: string;
  model?: string;
  path?: string;
  mode?: "models" | "chat";
}): Promise<ProviderTestResult> {
  return request("/api/v1/providers/test", {
    method: "POST",
    body: JSON.stringify(payload),
    silent: true,
    redactBody: true
  });
}

export async function getDoctor(): Promise<{ ok: boolean; checks: Record<string, unknown> }> {
  return request("/api/v1/system/doctor");
}

export function supportBundleUrl(): string {
  return "/api/v1/system/support-bundle";
}

export function getSystem(): Promise<SystemInfo> {
  return request<SystemInfo>("/api/v1/system");
}

export async function listDirectory(params: {
  path?: string;
  mode: "file" | "directory";
  extensions?: string[];
  q?: string;
  showHidden?: boolean;
  limit?: number;
}): Promise<FsListing> {
  const query = new URLSearchParams({ mode: params.mode });
  if (params.path) query.set("path", params.path);
  if (params.extensions?.length) query.set("extensions", params.extensions.join(","));
  if (params.q) query.set("q", params.q);
  if (params.showHidden) query.set("show_hidden", "true");
  if (params.limit) query.set("limit", String(params.limit));
  return request<FsListing>(`/api/v1/fs/list?${query.toString()}`);
}

export async function createDirectory(parent: string, name: string): Promise<FsEntry> {
  const response = await request<{ ok: boolean; entry: FsEntry }>("/api/v1/fs/mkdir", {
    method: "POST",
    body: JSON.stringify({ parent, name })
  });
  return response.entry;
}

export async function getPublishTargets(): Promise<PublishTarget[]> {
  const response = await request<{ ok: boolean; targets: PublishTarget[] }>(
    "/api/v1/publish/targets"
  );
  return response.targets;
}

export async function savePublishTarget(
  name: string,
  webhookUrl: string,
  description = ""
): Promise<PublishTarget> {
  const response = await request<{ ok: boolean; target: PublishTarget }>(
    `/api/v1/publish/targets/${encodeURIComponent(name)}`,
    {
      method: "PUT",
      body: JSON.stringify({
        description,
        webhook_url: webhookUrl,
        secret_name: "VIDEOWFLOW_PUBLISH_TOKEN",
        enabled: true
      })
    }
  );
  return response.target;
}

export async function scheduleShortPublish(
  jobId: string,
  index: number,
  payload: {
    target: string;
    platform: string;
    tone: string;
    scheduled_at?: string | null;
    allow_external_services?: boolean;
    allowed_external_hosts?: string[];
  }
): Promise<PublishQueueItem> {
  const response = await request<{ ok: boolean; item: PublishQueueItem }>(
    `/api/v1/jobs/${jobId}/shorts/${index}/publish`,
    { method: "POST", body: JSON.stringify(payload) }
  );
  return response.item;
}

export async function getProjectTemplates(): Promise<ProjectTemplate[]> {
  const response = await request<{ ok: boolean; templates: ProjectTemplate[] }>(
    "/api/v1/project-templates"
  );
  return response.templates;
}

export async function saveProjectTemplate(
  name: string,
  description: string,
  options: Record<string, unknown>
): Promise<ProjectTemplate> {
  const response = await request<{ ok: boolean; template: ProjectTemplate }>(
    `/api/v1/project-templates/${encodeURIComponent(name)}`,
    { method: "PUT", body: JSON.stringify({ name, description, options }) }
  );
  return response.template;
}

export async function deleteProjectTemplate(name: string): Promise<void> {
  await request(`/api/v1/project-templates/${encodeURIComponent(name)}`, { method: "DELETE" });
}

export async function applyProjectTemplate(name: string): Promise<Record<string, unknown>> {
  const response = await request<{ ok: boolean; options: Record<string, unknown> }>(
    `/api/v1/project-templates/${encodeURIComponent(name)}/apply`,
    { method: "POST" }
  );
  return response.options;
}

export async function getPresets(): Promise<Array<{ name: string; preset: Record<string, unknown> }>> {
  const response = await request<{
    ok: boolean;
    presets: Array<{ name: string; preset: Record<string, unknown> }>;
  }>("/api/v1/presets");
  return response.presets;
}

export async function savePreset(
  name: string,
  preset: Record<string, unknown>
): Promise<void> {
  await request(`/api/v1/presets/${encodeURIComponent(name)}`, {
    method: "PUT",
    body: JSON.stringify(preset)
  });
}

export async function getBrandTemplates(): Promise<BrandTemplate[]> {
  const response = await request<{ ok: boolean; templates: BrandTemplate[] }>(
    "/api/v1/brand-templates"
  );
  return response.templates;
}

export async function saveBrandTemplate(
  name: string,
  template: Omit<BrandTemplate, "name">
): Promise<BrandTemplate> {
  const response = await request<{ ok: boolean; template: BrandTemplate }>(
    `/api/v1/brand-templates/${encodeURIComponent(name)}`,
    { method: "PUT", body: JSON.stringify({ ...template, name }) }
  );
  return response.template;
}

export async function deleteBrandTemplate(name: string): Promise<void> {
  await request(`/api/v1/brand-templates/${encodeURIComponent(name)}`, { method: "DELETE" });
}

export async function applyBrandTemplate(name: string): Promise<Record<string, unknown>> {
  const response = await request<{ ok: boolean; options: Record<string, unknown> }>(
    `/api/v1/brand-templates/${encodeURIComponent(name)}/apply`,
    { method: "POST" }
  );
  return response.options;
}

export async function getMusic(): Promise<MusicAsset[]> {
  const response = await request<{ ok: boolean; music: MusicAsset[] }>("/api/v1/assets/music");
  return response.music;
}

export async function uploadMusic(file: File): Promise<MusicAsset> {
  const path = `/api/v1/assets/music?name=${encodeURIComponent(file.name)}`;
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: file
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) raiseApiError(response, payload, path, "music_upload_failed");
  return payload.music as MusicAsset;
}

export async function getSfx(): Promise<MusicAsset[]> {
  const response = await request<{ ok: boolean; sfx: MusicAsset[] }>("/api/v1/assets/sfx");
  return response.sfx;
}

export async function uploadSfx(file: File): Promise<MusicAsset> {
  const path = `/api/v1/assets/sfx?name=${encodeURIComponent(file.name)}`;
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: file
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) raiseApiError(response, payload, path, "sfx_upload_failed");
  return payload.sfx as MusicAsset;
}

export async function deleteSfxAsset(name: string): Promise<void> {
  await request(`/api/v1/assets/sfx/${encodeURIComponent(name)}`, {
    method: "DELETE"
  });
}

export async function getImages(): Promise<ImageAsset[]> {
  const response = await request<{ ok: boolean; images: ImageAsset[] }>("/api/v1/assets/images");
  return response.images;
}

export async function uploadImage(file: File): Promise<ImageAsset> {
  const path = `/api/v1/assets/images?name=${encodeURIComponent(file.name)}`;
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: file
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) raiseApiError(response, payload, path, "image_upload_failed");
  return payload.image as ImageAsset;
}

export async function getFonts(): Promise<FontAsset[]> {
  const response = await request<{ ok: boolean; fonts: FontAsset[] }>("/api/v1/assets/fonts");
  return response.fonts;
}

export async function uploadFont(file: File): Promise<FontAsset> {
  const path = `/api/v1/assets/fonts?name=${encodeURIComponent(file.name)}`;
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: file
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) raiseApiError(response, payload, path, "font_upload_failed");
  return payload.font as FontAsset;
}

export interface PluginPayload {
  ok: boolean;
  plugins: Array<Record<string, unknown>>;
  panels: Array<Record<string, unknown>>;
}

export async function loadPluginCatalog(reload = false): Promise<PluginPayload> {
  return request<PluginPayload>(reload ? "/api/v1/plugins/reload" : "/api/v1/plugins", {
    method: reload ? "POST" : "GET"
  });
}

export async function setPluginEnabled(pluginId: string, enabled: boolean): Promise<void> {
  await request(`/api/v1/plugins/${encodeURIComponent(pluginId)}/enable`, {
    method: "POST",
    body: JSON.stringify({ enabled })
  });
}

export async function getCapabilities(allowExternal = false): Promise<CapabilitiesResponse> {
  return request<CapabilitiesResponse>(
    `/api/v1/capabilities?allow_external=${allowExternal ? "true" : "false"}`
  );
}

export async function listRecipeSteps(): Promise<StepManifest[]> {
  const response = await request<{ ok: boolean; steps: StepManifest[] }>("/api/v1/steps");
  return response.steps;
}

export async function listRecipes(): Promise<RecipeSummary[]> {
  const response = await request<{ ok: boolean; recipes: RecipeSummary[] }>("/api/v1/recipes");
  return response.recipes ?? [];
}

export async function getJobReview(jobId: string): Promise<{
  review: Record<string, unknown>;
  approval: Record<string, unknown>;
}> {
  return request(`/api/v1/jobs/${encodeURIComponent(jobId)}/review`);
}

export async function decideJobReview(
  jobId: string,
  payload: { approved: boolean; comment?: string; reviewer?: string }
): Promise<void> {
  await request(`/api/v1/jobs/${encodeURIComponent(jobId)}/review`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
}

export async function getJobThumbnails(jobId: string): Promise<{
  variants: string[];
  selected: string;
}> {
  return request(`/api/v1/jobs/${encodeURIComponent(jobId)}/thumbnails`);
}

export async function getThumbnailMetrics(
  jobId: string
): Promise<Array<{ name: string; impressions: number; clicks: number; ctr: number }>> {
  const response = await request<{
    ok: boolean;
    metrics: Array<{ name: string; impressions: number; clicks: number; ctr: number }>;
  }>(`/api/v1/jobs/${encodeURIComponent(jobId)}/thumbnails/metrics`);
  return response.metrics;
}

export async function recordThumbnailMetric(
  jobId: string,
  name: string,
  payload: { impressions?: number; clicks?: number }
): Promise<void> {
  await request(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/thumbnails/${encodeURIComponent(name)}/metric`,
    { method: "POST", body: JSON.stringify(payload) }
  );
}

export async function getReviewComments(
  jobId: string
): Promise<Array<{ author: string; text: string; time_sec: number | null; at: string }>> {
  const response = await request<{
    ok: boolean;
    comments: Array<{ author: string; text: string; time_sec: number | null; at: string }>;
  }>(`/api/v1/jobs/${encodeURIComponent(jobId)}/review/comments`);
  return response.comments;
}

export async function addReviewComment(
  jobId: string,
  payload: { author?: string; text: string; time_sec?: number | null }
): Promise<void> {
  await request(`/api/v1/jobs/${encodeURIComponent(jobId)}/review/comments`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function selectJobThumbnail(jobId: string, name: string): Promise<void> {
  await request(`/api/v1/jobs/${encodeURIComponent(jobId)}/thumbnails/select`, {
    method: "POST",
    body: JSON.stringify({ name })
  });
}

export function jobThumbnailUrl(jobId: string, name: string): string {
  return `/api/v1/jobs/${encodeURIComponent(jobId)}/thumbnails/${encodeURIComponent(name)}`;
}

export async function getSettings(): Promise<{
  settings: AppSettings;
  env: Record<string, string>;
  restart_required: string[];
}> {
  return request("/api/v1/settings");
}

export interface IntelligenceProviderStatus {
  provider: string;
  kind: string;
  ready: boolean;
  detail: string;
  models: string[];
}

export interface IntelligenceStatus {
  ok: boolean;
  enabled: boolean;
  order: string[];
  providers: IntelligenceProviderStatus[];
  telemetry: Record<string, unknown>;
}

export async function getIntelligenceStatus(): Promise<IntelligenceStatus> {
  return request("/api/v1/intelligence/status");
}

export async function getIntelligenceModels(
  provider = "opencode_v2"
): Promise<{ ok: boolean; provider: string; models: Record<string, unknown>[] }> {
  return request(`/api/v1/intelligence/models?provider=${encodeURIComponent(provider)}`);
}

export async function saveSettings(settings: AppSettings): Promise<AppSettings> {
  const response = await request<{ ok: boolean; settings: AppSettings }>(
    "/api/v1/settings",
    { method: "PUT", body: JSON.stringify(settings) }
  );
  return response.settings;
}

export async function resetSettings(): Promise<AppSettings> {
  const response = await request<{ ok: boolean; settings: AppSettings }>(
    "/api/v1/settings/reset",
    { method: "POST" }
  );
  return response.settings;
}

export async function listServiceDefinitions(): Promise<{
  services: ServiceDefinition[];
  statuses: ServiceDefinitionStatus[];
}> {
  return request("/api/v1/services/definitions");
}

export async function saveServiceDefinition(
  service: ServiceDefinition
): Promise<ServiceDefinition> {
  const response = await request<{ ok: boolean; service: ServiceDefinition }>(
    `/api/v1/services/definitions/${encodeURIComponent(service.id)}`,
    { method: "PUT", body: JSON.stringify(service) }
  );
  return response.service;
}

export async function deleteServiceDefinition(serviceId: string): Promise<void> {
  await request(`/api/v1/services/definitions/${encodeURIComponent(serviceId)}`, {
    method: "DELETE"
  });
}

export async function startManagedService(
  serviceId: string
): Promise<ServiceDefinitionStatus> {
  const response = await request<{ ok: boolean; service: ServiceDefinitionStatus }>(
    `/api/v1/services/definitions/${encodeURIComponent(serviceId)}/start`,
    { method: "POST" }
  );
  return response.service;
}

export async function stopManagedService(
  serviceId: string
): Promise<ServiceDefinitionStatus> {
  const response = await request<{ ok: boolean; service: ServiceDefinitionStatus }>(
    `/api/v1/services/definitions/${encodeURIComponent(serviceId)}/stop`,
    { method: "POST" }
  );
  return response.service;
}

export async function getManagedServiceLogs(
  serviceId: string,
  lines = 200
): Promise<string> {
  const response = await request<{ ok: boolean; text: string }>(
    `/api/v1/services/definitions/${encodeURIComponent(serviceId)}/logs?lines=${lines}`
  );
  return response.text;
}

export async function listSchedules(): Promise<RecipeSchedule[]> {
  const response = await request<{ ok: boolean; schedules: RecipeSchedule[] }>(
    "/api/v1/schedules"
  );
  return response.schedules;
}

export async function saveSchedule(schedule: RecipeSchedule): Promise<RecipeSchedule> {
  const response = await request<{ ok: boolean; schedule: RecipeSchedule }>(
    `/api/v1/schedules/${encodeURIComponent(schedule.id)}`,
    { method: "PUT", body: JSON.stringify(schedule) }
  );
  return response.schedule;
}

export async function deleteSchedule(scheduleId: string): Promise<void> {
  await request(`/api/v1/schedules/${encodeURIComponent(scheduleId)}`, { method: "DELETE" });
}

export async function runScheduleNow(scheduleId: string): Promise<RecipeSchedule> {
  const response = await request<{ ok: boolean; schedule: RecipeSchedule }>(
    `/api/v1/schedules/${encodeURIComponent(scheduleId)}/run`,
    { method: "POST" }
  );
  return response.schedule;
}

export async function getRecipe(recipeId: string): Promise<Recipe> {
  const response = await request<{ ok: boolean; recipe: Recipe }>(
    `/api/v1/recipes/${encodeURIComponent(recipeId)}`
  );
  return response.recipe;
}

export async function saveRecipe(recipe: Recipe): Promise<Recipe> {
  const response = await request<{ ok: boolean; recipe: Recipe }>(
    `/api/v1/recipes/${encodeURIComponent(recipe.id)}`,
    { method: "PUT", body: JSON.stringify(recipe) }
  );
  return response.recipe;
}

export interface RecipeHistoryEntry {
  version: string;
  name: string;
  description: string;
  step_count: number;
}

export async function getRecipeHistory(recipeId: string): Promise<RecipeHistoryEntry[]> {
  const response = await request<{ ok: boolean; history: RecipeHistoryEntry[] }>(
    `/api/v1/recipes/${encodeURIComponent(recipeId)}/history`
  );
  return response.history;
}

export async function getRecipeVersion(
  recipeId: string,
  version: string
): Promise<Recipe> {
  const response = await request<{ ok: boolean; recipe: Recipe }>(
    `/api/v1/recipes/${encodeURIComponent(recipeId)}/history/${encodeURIComponent(version)}`
  );
  return response.recipe;
}

export async function restoreRecipeVersion(
  recipeId: string,
  version: string
): Promise<Recipe> {
  const response = await request<{ ok: boolean; recipe: Recipe }>(
    `/api/v1/recipes/${encodeURIComponent(recipeId)}/history/${encodeURIComponent(version)}/restore`,
    { method: "POST" }
  );
  return response.recipe;
}

export async function validateRecipe(
  recipe: Recipe,
  through?: string
): Promise<{ ok: boolean; recipe: Recipe; order: string[] }> {
  const query = through ? `?through=${encodeURIComponent(through)}` : "";
  return request<{ ok: boolean; recipe: Recipe; order: string[] }>(
    `/api/v1/recipes/validate${query}`,
    {
      method: "POST",
      body: JSON.stringify(recipe)
    }
  );
}

export interface PreflightCheck {
  id: string;
  category: "recipe" | "input" | "runtime" | "provider" | "optional";
  status: "ok" | "warning" | "error";
  label: string;
  detail: string;
  fix: string;
  step_id: string;
}

export interface PreflightReport {
  ok: boolean;
  ready: boolean;
  errors: number;
  warnings: number;
  checks: PreflightCheck[];
}

export async function preflightRecipe(payload: {
  source: string;
  output: string;
  recipe: Recipe;
  variables?: Record<string, unknown>;
  through?: string | null;
}): Promise<PreflightReport> {
  return request<PreflightReport>("/api/v1/recipes/preflight", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function runRecipe(payload: {
  source: string;
  output: string;
  recipe: Recipe;
  save_recipe?: boolean;
  resume?: boolean;
  through?: string | null;
  variables?: Record<string, unknown>;
  profile?: string | null;
}): Promise<Job> {
  const response = await request<{ ok: boolean; job: Job }>("/api/v1/recipes/run", {
    method: "POST",
    body: JSON.stringify(payload)
  });
  return response.job;
}

export async function dryRunRecipe(payload: {
  source: string;
  output: string;
  recipe: Recipe;
  variables?: Record<string, unknown>;
  profile?: string | null;
  through?: string | null;
}): Promise<{
  ok: boolean;
  recipe_id: string;
  profile: string;
  variables: Record<string, unknown>;
  steps: Array<{ id: string; type: string; needs: string[]; params: Record<string, unknown> }>;
}> {
  return request("/api/v1/recipes/dry-run", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function runBatch(payload: {
  source_dir: string;
  output_root: string;
  recipe: Recipe;
  recursive?: boolean;
  extensions?: string[];
  resume?: boolean;
  max_files?: number;
}): Promise<Batch> {
  const response = await request<{ ok: boolean; batch: Batch }>("/api/v1/batches", {
    method: "POST",
    body: JSON.stringify(payload)
  });
  return response.batch;
}

export interface NleExportCheck {
  ok: boolean;
  path: string;
  errors: string[];
  warnings: string[];
  [key: string]: unknown;
}

export interface NleValidationReport {
  ok: boolean;
  directory: string;
  exports: Record<string, NleExportCheck>;
}

export async function validateExports(output: string): Promise<NleValidationReport> {
  return request<NleValidationReport>("/api/v1/exports/validate", {
    method: "POST",
    body: JSON.stringify({ output })
  });
}

export async function getRunHistory(output: string): Promise<RunRecord[]> {
  const query = new URLSearchParams({ output });
  const response = await request<{ ok: boolean; runs: RunRecord[] }>(
    `/api/v1/runs?${query.toString()}`
  );
  return response.runs;
}

export async function listBatches(): Promise<Batch[]> {
  const response = await request<{ ok: boolean; batches: Batch[] }>("/api/v1/batches");
  return response.batches;
}

export async function getBatch(batchId: string): Promise<Batch> {
  const response = await request<{ ok: boolean; batch: Batch }>(
    `/api/v1/batches/${encodeURIComponent(batchId)}`
  );
  return response.batch;
}

export async function resumeBatch(batchId: string): Promise<Batch> {
  const response = await request<{ ok: boolean; batch: Batch }>(
    `/api/v1/batches/${encodeURIComponent(batchId)}/resume`,
    { method: "POST" }
  );
  return response.batch;
}

export async function cancelBatch(batchId: string): Promise<Batch> {
  const response = await request<{ ok: boolean; batch: Batch }>(
    `/api/v1/batches/${encodeURIComponent(batchId)}/cancel`,
    { method: "POST" }
  );
  return response.batch;
}

export async function resumeJob(
  jobId: string,
  payload: { approved: boolean; comment?: string }
): Promise<Job> {
  const response = await request<{ ok: boolean; job: Job; gate: string }>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/resume`,
    { method: "POST", body: JSON.stringify(payload) }
  );
  return response.job;
}

export async function listJobInteractions(jobId: string): Promise<HiltInteraction[]> {
  const response = await request<{ ok: boolean; interactions: HiltInteraction[] }>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/interactions`
  );
  return response.interactions ?? [];
}

export async function getJobInteraction(
  jobId: string,
  interactionId: string
): Promise<HiltInteraction> {
  const response = await request<{ ok: boolean; interaction: HiltInteraction }>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/interactions/${encodeURIComponent(interactionId)}`
  );
  return response.interaction;
}

export async function respondToInteraction(
  jobId: string,
  interactionId: string,
  payload: {
    action: "approve" | "reject" | "submit";
    answers?: Record<string, unknown>;
    comment?: string;
    responder?: string;
    channel?: string;
    token?: string;
  }
): Promise<Job> {
  const response = await request<{ ok: boolean; job: Job }>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/interactions/${encodeURIComponent(interactionId)}/respond`,
    { method: "POST", body: JSON.stringify(payload) }
  );
  return response.job;
}

export async function uploadInteractionFiles(
  jobId: string,
  interactionId: string,
  files: File[],
  requestId = ""
): Promise<HiltAttachment[]> {
  const form = new FormData();
  if (requestId) form.set("request_id", requestId);
  for (const file of files) form.append("files", file);
  const response = await request<{ ok: boolean; attachments: HiltAttachment[] }>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/interactions/${encodeURIComponent(interactionId)}/files`,
    { method: "POST", body: form }
  );
  return response.attachments;
}

export interface BulkApproveResult {
  ok: boolean;
  approved: Array<{
    job_id: string;
    interaction_id: string;
    status: string;
    resumed_job_id?: string;
  }>;
  failed: Array<{
    job_id: string;
    interaction_id: string;
    error: { code: string; message: string };
  }>;
}

export async function bulkApproveInteractions(
  items: Array<{ job_id: string; interaction_id: string }>,
  comment = ""
): Promise<BulkApproveResult> {
  return request<BulkApproveResult>("/api/v1/hilt/approve", {
    method: "POST",
    body: JSON.stringify({ items, comment })
  });
}

export async function listPendingInteractions(): Promise<HiltPending[]> {
  const response = await request<{ ok: boolean; interactions: HiltPending[] }>(
    "/api/v1/hilt/pending"
  );
  return response.interactions ?? [];
}

export async function listHiltChannels(): Promise<{
  default: string[];
  channels: HiltChannelStatus[];
}> {
  return request<{ default: string[]; channels: HiltChannelStatus[] }>(
    "/api/v1/hilt/channels"
  );
}

export async function testHiltChannel(
  channel: string,
  title = "VideoFlow HILT test"
): Promise<{ ok: boolean; channel: string; message: string }> {
  return request<{ ok: boolean; channel: string; message: string }>(
    "/api/v1/hilt/test",
    { method: "POST", body: JSON.stringify({ channel, title }) }
  );
}

export async function saveHiltSecret(
  name: string,
  value: string
): Promise<{ ok: boolean; name: string; present: boolean }> {
  return request<{ ok: boolean; name: string; present: boolean }>(
    "/api/v1/hilt/secrets",
    { method: "POST", body: JSON.stringify({ name, value }) }
  );
}

export async function runRecipeStep(
  stepId: string,
  payload: {
    source: string;
    output: string;
    recipe: Recipe;
    save_recipe?: boolean;
    resume?: boolean;
    variables?: Record<string, unknown>;
    profile?: string | null;
  }
): Promise<Job> {
  const response = await request<{ ok: boolean; job: Job }>(
    `/api/v1/steps/${encodeURIComponent(stepId)}/run`,
    {
      method: "POST",
      body: JSON.stringify(payload)
    }
  );
  return response.job;
}

export async function editShort(
  jobId: string,
  index: number,
  payload: ShortEditPayload
): Promise<{ ok: boolean; short: ShortClip; download: string }> {
  return request(`/api/v1/jobs/${jobId}/shorts/${index}/edit`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function generateShortEmoji(
  jobId: string,
  index: number,
  payload: {
    base_url?: string;
    model?: string;
    allow_external_services?: boolean;
    allowed_external_hosts?: string[];
  }
): Promise<{ ok: boolean; emoji_map: Record<string, string>; short: ShortClip }> {
  return request(`/api/v1/jobs/${jobId}/shorts/${index}/captions/emoji`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function generateShortMetadata(
  jobId: string,
  index: number,
  payload: { platform: string; tone: string; extra_hashtags?: string[] }
): Promise<{ ok: boolean; metadata: ShortMetadata; short: ShortClip }> {
  return request(`/api/v1/jobs/${jobId}/shorts/${index}/metadata`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function generateShortVoiceover(
  jobId: string,
  index: number,
  payload: {
    text: string;
    provider?: "openai_compatible" | "piper";
    base_url?: string;
    model?: string;
    voice?: string;
    binary?: string;
    model_path?: string;
    allow_external_services?: boolean;
    allowed_external_hosts?: string[];
  }
): Promise<{ ok: boolean; voiceover: ShortVoiceover; short: ShortClip }> {
  return request(`/api/v1/jobs/${jobId}/shorts/${index}/voiceover`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function analyzeShort(
  jobId: string,
  index: number
): Promise<{ ok: boolean; analysis: ShortAnalysis; short: ShortClip }> {
  return request(`/api/v1/jobs/${jobId}/shorts/${index}/analyze`, { method: "POST" });
}

export async function generateShortDubbing(
  jobId: string,
  index: number,
  payload: {
    text?: string;
    target_language: string;
    base_url?: string;
    model?: string;
    voice?: string;
    llm_base_url?: string;
    llm_model?: string;
    allow_external_services?: boolean;
    allowed_external_hosts?: string[];
  }
): Promise<{ ok: boolean; dubbing: ShortDubbing; short: ShortClip }> {
  return request(`/api/v1/jobs/${jobId}/shorts/${index}/dub`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function generateShortThumbnail(
  jobId: string,
  index: number,
  payload: { time_sec?: number; title?: string; caption_style?: Record<string, unknown> }
): Promise<{ ok: boolean; thumbnail: ShortThumbnail; short: ShortClip }> {
  return request(`/api/v1/jobs/${jobId}/shorts/${index}/thumbnail`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function getJob(
  jobId: string,
  options?: { silent?: boolean }
): Promise<Job> {
  const response = await request<{ ok: boolean; job: Job }>(
    `/api/v1/jobs/${jobId}`,
    { silent: options?.silent }
  );
  return response.job;
}

export interface WaveformPeaks {
  ok: boolean;
  peaks: number[];
  bucket_sec: number;
  start_sec: number;
  end_sec: number;
}

export interface TimelineClip {
  id: string;
  start_sec: number;
  end_sec: number;
  source_in_frame?: number;
  source_out_frame?: number;
  source_start_sec?: number;
  source_end_sec?: number;
  source_in_sec?: number;
  source_out_sec?: number;
  zoom?: number;
  pos_x?: number;
  pos_y?: number;
  keyframes?: number;
  transition?: string | null;
  transition_frames?: number;
  transition_audio?: boolean;
  fade_in_sec?: number;
  fade_out_sec?: number;
}

export interface TimelineTitleCue {
  start_sec: number;
  end_sec: number;
  text: string;
  style: "title" | "lower_third";
}

export interface LiveSourceState {
  status: "missing" | "preparing" | "ready" | "failed";
  url: string;
  reason: string;
  path: string;
  error: string;
  started_at: string;
  finished_at: string;
}

export interface TimelineData {
  ok: boolean;
  job_id: string;
  revision: number;
  can_undo: boolean;
  can_redo: boolean;
  fps: number;
  duration_sec: number;
  source_duration_sec: number;
  live_eligible: boolean;
  live_reason: string;
  live_source?: LiveSourceState;
  video: TimelineClip[];
  audio: TimelineClip[];
  captions: Array<{
    id: number;
    start_sec: number;
    end_sec: number;
    text: string;
    speaker: number;
  }>;
  shorts: ShortClip[];
  broll: Record<string, Array<Record<string, unknown>>>;
  broll_approval: Record<string, { approved: number[]; order: number[] }>;
  markers: TimelineMarker[];
  comments?: TimelineComment[];
  inactive: TimelineInactive[];
  overlays?: TimelineOverlay[];
  titles?: TimelineTitleCue[];
  tracks: Record<string, TrackState>;
  media?: { source_path: string; audio_sample_rate: number };
}

export interface TimelineInactive {
  id: string;
  reason: "silence" | "retake" | "manual" | "noise";
  video_start_sec: number;
  video_end_sec: number;
  audio_start_sec: number;
  audio_end_sec: number;
}

export interface TimelineSnapshot {
  id: string;
  name: string;
  created_at: string;
  revision: number;
  duration_sec: number;
  source_path: string;
  source_fingerprint: string;
  path: string;
  job_id: string;
}

export interface TimelineOverlay {
  overlay_id: string;
  asset_id: string;
  path: string;
  start_frame: number;
  duration_frames: number;
  position_x: number;
  position_y: number;
  width_ratio: number;
  opacity: number;
  kind: "image" | "video";
}

export interface TimelineComment {
  id: string;
  clip_id: string;
  text: string;
  author: string;
  created_at: string;
}

export interface TimelineMarker {
  id: string;
  time_sec: number;
  end_sec?: number;
  label: string;
  color: string;
}

export interface TrackState {
  muted: boolean;
  solo: boolean;
  locked: boolean;
}

export interface ProviderConfig {
  id: string;
  name: string;
  capability:
    | "llm"
    | "asr"
    | "tts"
    | "vision"
    | "stock"
    | "translation"
    | "diarization"
    | "publishing";
  base_url: string;
  api_key_env: string;
  model: string;
  enabled: boolean;
  is_default: boolean;
  fallback: string[];
  notes: string;
  secret_present?: boolean;
  configured?: boolean;
  missing?: string[];
}

export interface ModelDownload {
  model_id: string;
  status: "queued" | "downloading" | "installed" | "failed" | "cancelled" | "interrupted";
  percent: number;
  message: string;
  error: string;
  started_at: string;
  finished_at: string;
  cancel_requested: boolean;
  installed: boolean;
}

export interface AssetRecord {
  id: string;
  path: string;
  name: string;
  kind: "video" | "audio" | "image" | "font" | "other";
  suffix: string;
  size_bytes: number;
  modified_at: string;
  added_at: string;
  tags: string[];
  license: string;
  source: string;
}

export async function editTimeline(
  jobId: string,
  revision: number | null | undefined,
  payload: {
    clip_id: string;
    action:
      | "trim"
      | "move"
      | "delete"
      | "split"
      | "ripple"
      | "ripple_trim"
      | "slip"
      | "slide"
      | "duplicate"
      | "deactivate"
      | "activate"
      | "recut";
    start_sec?: number;
    end_sec?: number;
    delta_sec?: number;
    split_sec?: number;
  }
): Promise<{
  ok: boolean;
  revision: number;
  can_undo: boolean;
  can_redo: boolean;
  warning: string;
}> {
  return request(`/api/v1/jobs/${encodeURIComponent(jobId)}/timeline`, {
    method: "PATCH",
    headers: revision ? { "If-Match": `"timeline-${revision}"` } : undefined,
    body: JSON.stringify(payload)
  });
}

export async function editTimelineBatch(
  jobId: string,
  revision: number | null | undefined,
  edits: Array<{
    clip_id: string;
    action:
      | "trim"
      | "move"
      | "delete"
      | "split"
      | "ripple"
      | "ripple_trim"
      | "slip"
      | "slide"
      | "duplicate"
      | "deactivate"
      | "activate"
      | "recut";
    start_sec?: number;
    end_sec?: number;
    delta_sec?: number;
    split_sec?: number;
  }>
): Promise<{ ok: boolean; revision: number; applied: number }> {
  return request(`/api/v1/jobs/${encodeURIComponent(jobId)}/timeline/batch`, {
    method: "PATCH",
    headers: revision ? { "If-Match": `"timeline-${revision}"` } : undefined,
    body: JSON.stringify({ edits })
  });
}

export async function addTimelineOverlay(
  jobId: string,
  payload: {
    asset_id?: string;
    path: string;
    start_sec: number;
    duration_sec: number;
    position_x?: number;
    position_y?: number;
    width_ratio?: number;
    opacity?: number;
    kind?: "image" | "video";
  }
): Promise<TimelineOverlay[]> {
  const response = await request<{ ok: boolean; overlays: TimelineOverlay[] }>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/timeline/overlays`,
    { method: "POST", body: JSON.stringify(payload) }
  );
  return response.overlays;
}

export async function removeTimelineOverlay(
  jobId: string,
  overlayId: string
): Promise<TimelineOverlay[]> {
  const response = await request<{ ok: boolean; overlays: TimelineOverlay[] }>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/timeline/overlays/${encodeURIComponent(overlayId)}`,
    { method: "DELETE" }
  );
  return response.overlays;
}

export async function setRecipeFavorite(
  recipeId: string,
  favorite: boolean
): Promise<void> {
  await request(`/api/v1/recipes/${encodeURIComponent(recipeId)}/favorite`, {
    method: "POST",
    body: JSON.stringify({ favorite })
  });
}

export async function updateRecipeTags(
  recipeId: string,
  tags: string[]
): Promise<void> {
  await request(`/api/v1/recipes/${encodeURIComponent(recipeId)}/meta`, {
    method: "PATCH",
    body: JSON.stringify({ tags })
  });
}

export async function copilotRecipe(prompt: string): Promise<Record<string, unknown>> {
  const response = await request<{ ok: boolean; recipe: Record<string, unknown> }>(
    "/api/v1/copilot/recipe",
    { method: "POST", body: JSON.stringify({ prompt }) }
  );
  return response.recipe;
}

export async function copilotTimeline(
  jobId: string,
  prompt: string,
  apply: boolean
): Promise<{ edits: Array<Record<string, unknown>>; revision: number }> {
  return request(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/copilot/timeline`,
    { method: "POST", body: JSON.stringify({ prompt, apply }) }
  );
}

export async function getTimelineComments(
  jobId: string,
  clipId = ""
): Promise<TimelineComment[]> {
  const params = clipId ? `?clip_id=${encodeURIComponent(clipId)}` : "";
  const response = await request<{ ok: boolean; comments: TimelineComment[] }>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/timeline/comments${params}`
  );
  return response.comments;
}

export async function addTimelineComment(
  jobId: string,
  payload: { clip_id: string; text: string; author?: string }
): Promise<TimelineComment[]> {
  const response = await request<{ ok: boolean; comments: TimelineComment[] }>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/timeline/comments`,
    { method: "POST", body: JSON.stringify(payload) }
  );
  return response.comments;
}

export async function removeTimelineComment(
  jobId: string,
  commentId: string
): Promise<TimelineComment[]> {
  const response = await request<{ ok: boolean; comments: TimelineComment[] }>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/timeline/comments/${encodeURIComponent(commentId)}`,
    { method: "DELETE" }
  );
  return response.comments;
}

export async function addTimelineMarker(
  jobId: string,
  payload: { time_sec: number; label?: string; color?: string }
): Promise<TimelineMarker[]> {
  const response = await request<{ ok: boolean; markers: TimelineMarker[] }>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/timeline/markers`,
    { method: "POST", body: JSON.stringify(payload) }
  );
  return response.markers;
}

export async function removeTimelineMarker(
  jobId: string,
  markerId: string
): Promise<TimelineMarker[]> {
  const response = await request<{ ok: boolean; markers: TimelineMarker[] }>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/timeline/markers/${encodeURIComponent(markerId)}`,
    { method: "DELETE" }
  );
  return response.markers;
}

export async function updateTimelineTrack(
  jobId: string,
  track: string,
  state: TrackState
): Promise<Record<string, TrackState>> {
  const response = await request<{ ok: boolean; tracks: Record<string, TrackState> }>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/timeline/tracks/${encodeURIComponent(track)}`,
    { method: "PUT", body: JSON.stringify(state) }
  );
  return response.tracks;
}

export async function updateTimelineClip(
  jobId: string,
  clipId: string,
  payload: {
    transition_type?: "crossfade" | "fade_to_black" | "none";
    transition_duration_frames?: number;
    scale?: number;
    pos_x?: number;
    pos_y?: number;
    fade_in_sec?: number;
    fade_out_sec?: number;
  }
): Promise<{ ok: boolean; revision: number; can_undo: boolean; can_redo: boolean }> {
  return request(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/timeline/clip/${encodeURIComponent(clipId)}`,
    { method: "PATCH", body: JSON.stringify(payload) }
  );
}

export async function updateTimelineClips(
  jobId: string,
  clipIds: string[],
  payload: {
    transition_type?: "crossfade" | "fade_to_black" | "none";
    transition_duration_frames?: number;
    scale?: number;
    pos_x?: number;
    pos_y?: number;
    fade_in_sec?: number;
    fade_out_sec?: number;
  }
): Promise<{
  ok: boolean;
  revision: number;
  applied: number;
  can_undo: boolean;
  can_redo: boolean;
}> {
  if (!clipIds.length) {
    throw new Error("Select at least one clip");
  }
  return request(`/api/v1/jobs/${encodeURIComponent(jobId)}/timeline/clips`, {
    method: "PATCH",
    body: JSON.stringify({ ...payload, clip_ids: clipIds })
  });
}

export async function undoTimeline(jobId: string): Promise<void> {
  await request(`/api/v1/jobs/${encodeURIComponent(jobId)}/timeline/undo`, {
    method: "POST"
  });
}

export async function redoTimeline(jobId: string): Promise<void> {
  await request(`/api/v1/jobs/${encodeURIComponent(jobId)}/timeline/redo`, {
    method: "POST"
  });
}

export async function approveBroll(
  jobId: string,
  payload: { title: string; approved: number[]; order: number[] }
): Promise<Record<string, { approved: number[]; order: number[] }>> {
  const response = await request<{
    ok: boolean;
    approval: Record<string, { approved: number[]; order: number[] }>;
  }>(`/api/v1/jobs/${encodeURIComponent(jobId)}/broll`, {
    method: "PATCH",
    body: JSON.stringify(payload)
  });
  return response.approval;
}

export async function updateJobCaption(
  jobId: string,
  sentenceId: number,
  text: string
): Promise<void> {
  await request(`/api/v1/jobs/${encodeURIComponent(jobId)}/captions/${sentenceId}`, {
    method: "PATCH",
    body: JSON.stringify({ text })
  });
}

export async function getClipWaveform(
  jobId: string,
  startSec: number,
  endSec: number,
  buckets: number
): Promise<number[]> {
  const params = new URLSearchParams({
    start: String(startSec),
    end: String(endSec),
    buckets: String(buckets)
  });
  const response = await request<WaveformPeaks>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/timeline/waveform?${params.toString()}`
  );
  return response.peaks;
}

export async function getTimeline(jobId: string): Promise<TimelineData> {
  return request<TimelineData>(`/api/v1/jobs/${encodeURIComponent(jobId)}/timeline`);
}

export async function listTimelineSnapshots(): Promise<TimelineSnapshot[]> {
  const response = await request<{ ok: boolean; timelines: TimelineSnapshot[] }>(
    "/api/v1/timelines"
  );
  return response.timelines;
}

export async function saveTimelineSnapshot(
  jobId: string,
  name: string
): Promise<TimelineSnapshot> {
  const response = await request<{ ok: boolean; timeline: TimelineSnapshot }>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/timeline/snapshots`,
    { method: "POST", body: JSON.stringify({ name }) }
  );
  return response.timeline;
}

export async function loadTimelineSnapshot(
  snapshotId: string,
  jobId: string
): Promise<number> {
  const response = await request<{ ok: boolean; revision: number }>(
    `/api/v1/timelines/${encodeURIComponent(snapshotId)}/load`,
    { method: "POST", body: JSON.stringify({ job_id: jobId }) }
  );
  return response.revision;
}

export function timelineSnapshotFileUrl(snapshotId: string): string {
  return `/api/v1/timelines/${encodeURIComponent(snapshotId)}/file`;
}

export async function importTimelineSnapshot(
  payload: Record<string, unknown>,
  name = ""
): Promise<TimelineSnapshot> {
  const response = await request<{ ok: boolean; timeline: TimelineSnapshot }>(
    "/api/v1/timelines/import",
    { method: "POST", body: JSON.stringify({ payload, name }) }
  );
  return response.timeline;
}

export async function deleteTimelineSnapshot(snapshotId: string): Promise<void> {
  await request<{ ok: boolean }>(
    `/api/v1/timelines/${encodeURIComponent(snapshotId)}`,
    { method: "DELETE" }
  );
}

export async function listAssets(q = "", kind = ""): Promise<AssetRecord[]> {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (kind) params.set("kind", kind);
  const response = await request<{ ok: boolean; assets: AssetRecord[] }>(
    `/api/v1/assets?${params.toString()}`
  );
  return response.assets;
}

export async function scanAssets(
  directory: string,
  tags: string[] = [],
  recursive = true
): Promise<AssetRecord[]> {
  const response = await request<{ ok: boolean; assets: AssetRecord[] }>(
    "/api/v1/assets/scan",
    {
      method: "POST",
      body: JSON.stringify({ directory, tags, recursive })
    }
  );
  return response.assets;
}

export async function removeAsset(assetId: string): Promise<void> {
  await request(`/api/v1/assets/${encodeURIComponent(assetId)}`, { method: "DELETE" });
}

export async function updateAssetTags(
  assetId: string,
  tags: string[]
): Promise<AssetRecord> {
  const response = await request<{ ok: boolean; asset: AssetRecord }>(
    `/api/v1/assets/${encodeURIComponent(assetId)}`,
    { method: "PATCH", body: JSON.stringify({ tags }) }
  );
  return response.asset;
}

export function assetFileUrl(assetId: string): string {
  return `/api/v1/assets/${encodeURIComponent(assetId)}/file`;
}

export async function listJobs(
  summary = true,
  options: { limit?: number; offset?: number; recipeId?: string } = {}
): Promise<Job[]> {
  const params = new URLSearchParams({
    summary: summary ? "true" : "false"
  });
  if (options.limit !== undefined) params.set("limit", String(options.limit));
  if (options.offset !== undefined) params.set("offset", String(options.offset));
  if (options.recipeId) params.set("recipe_id", options.recipeId);
  const response = await request<{ ok: boolean; jobs: Job[] }>(
    `/api/v1/jobs?${params.toString()}`
  );
  return response.jobs ?? [];
}

export async function pauseJob(jobId: string): Promise<Job> {
  const response = await request<{ ok: boolean; job: Job }>(
    `/api/v1/jobs/${jobId}/pause`,
    { method: "POST" }
  );
  return response.job;
}

export async function unpauseJob(jobId: string): Promise<Job> {
  const response = await request<{ ok: boolean; job: Job }>(
    `/api/v1/jobs/${jobId}/unpause`,
    { method: "POST" }
  );
  return response.job;
}

export async function setJobPriority(jobId: string, priority: number): Promise<Job> {
  const response = await request<{ ok: boolean; job: Job }>(
    `/api/v1/jobs/${jobId}/priority`,
    { method: "PATCH", body: JSON.stringify({ priority }) }
  );
  return response.job;
}

export async function retryJob(jobId: string): Promise<Job> {
  const response = await request<{ ok: boolean; job: Job }>(`/api/v1/jobs/${jobId}/retry`, {
    method: "POST"
  });
  return response.job;
}

export async function cancelJob(jobId: string, force = false): Promise<Job> {
  const query = force ? "?force=true" : "";
  const response = await request<{ ok: boolean; job: Job }>(
    `/api/v1/jobs/${jobId}/cancel${query}`,
    { method: "POST" }
  );
  return response.job;
}

export async function deleteJob(jobId: string, force = false): Promise<void> {
  const query = force ? "?force=true" : "";
  await request<{ ok: boolean; removed: string }>(
    `/api/v1/jobs/${jobId}${query}`,
    { method: "DELETE" }
  );
}

export async function cancelAllJobs(force = true): Promise<Job[]> {
  const query = force ? "?force=true" : "";
  const response = await request<{ ok: boolean; jobs: Job[] }>(
    `/api/v1/jobs/cancel_all${query}`,
    { method: "POST" }
  );
  return response.jobs ?? [];
}

export async function getLogs(
  jobId: string,
  module?: string,
  level?: string,
  limit = 500
): Promise<LogLine[]> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (module) params.set("module", module);
  if (level) params.set("level", level);
  const response = await request<{ ok: boolean; logs: LogLine[] }>(
    `/api/v1/jobs/${jobId}/logs?${params.toString()}`
  );
  return response.logs;
}

export async function createJobPreview(
  jobId: string,
  force = false,
  background = false
): Promise<{
  ok: boolean;
  status?: PreviewStatus | "ready";
  path?: string;
  url: string;
}> {
  return request(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/preview?force=${force}&background=${background}`,
    { method: "POST" }
  );
}

export interface PreviewStatus {
  job_id: string;
  status: "idle" | "queued" | "rendering" | "ready" | "failed" | "cancelled" | "stale";
  percent: number;
  message?: string;
  error?: string;
  error_details?: Record<string, unknown>;
  revision?: number;
  ready?: boolean;
}

export interface RenderStatus {
  job_id?: string;
  status: "idle" | "queued" | "rendering" | "ready" | "failed" | "cancelled";
  percent: number;
  message?: string;
  error?: string;
  error_details?: Record<string, unknown>;
}

export async function startRender(jobId: string): Promise<RenderStatus> {
  const response = await request<{ ok: boolean; render: RenderStatus }>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/render`,
    { method: "POST" }
  );
  return response.render;
}

export async function getRenderStatus(jobId: string): Promise<RenderStatus> {
  return request<RenderStatus>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/render/status`
  );
}

export async function cancelRender(jobId: string): Promise<void> {
  await request(`/api/v1/jobs/${encodeURIComponent(jobId)}/render/cancel`, {
    method: "POST"
  });
}

export function renderFileUrl(jobId: string): string {
  return `/api/v1/jobs/${encodeURIComponent(jobId)}/render/file`;
}

export function previewFileUrl(jobId: string): string {
  return `/api/v1/jobs/${encodeURIComponent(jobId)}/preview/file`;
}

export function jobSourceFileUrl(jobId: string): string {
  return `/api/v1/jobs/${encodeURIComponent(jobId)}/source/file`;
}

export async function getLiveSourceStatus(jobId: string): Promise<LiveSourceState> {
  const response = await request<{ ok: boolean; live_source: LiveSourceState }>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/live-source/status`
  );
  return response.live_source;
}

export async function prepareLiveSource(jobId: string): Promise<LiveSourceState> {
  const response = await request<{ ok: boolean; live_source: LiveSourceState }>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/live-source`,
    { method: "POST" }
  );
  return response.live_source;
}

export function jobOverlayFileUrl(jobId: string, overlayId: string): string {
  return `/api/v1/jobs/${encodeURIComponent(jobId)}/overlays/${encodeURIComponent(overlayId)}/file`;
}

export async function getPreviewStatus(jobId: string): Promise<PreviewStatus> {
  return request<PreviewStatus>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/preview/status`
  );
}

export async function cancelPreview(jobId: string): Promise<void> {
  await request(`/api/v1/jobs/${encodeURIComponent(jobId)}/preview/cancel`, {
    method: "POST"
  });
}

export function jobFrameUrl(jobId: string, timeSec: number): string {
  return `/api/v1/jobs/${encodeURIComponent(jobId)}/frame?time=${Math.max(0, timeSec).toFixed(2)}&t=${Date.now()}`;
}

export async function updateJobArtifact(
  jobId: string,
  artifactName: string,
  payload: Record<string, unknown>
): Promise<{ ok: boolean; artifact: string; path: string; note: string }> {
  return request(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/artifacts/${encodeURIComponent(artifactName)}`,
    { method: "PATCH", body: JSON.stringify({ payload }) }
  );
}

export function jobArtifactUrl(jobId: string, artifactName: string): string {
  return `/api/v1/jobs/${encodeURIComponent(jobId)}/artifacts/${encodeURIComponent(artifactName)}`;
}

export function shortFileUrl(jobId: string, index: number): string {
  return `/api/v1/jobs/${encodeURIComponent(jobId)}/shorts/${index}/file`;
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return `${error.code}: ${error.message}`;
  if (error instanceof Error) return error.message;
  return String(error);
}


export async function deleteMusicAsset(name: string): Promise<void> {
  await request(`/api/v1/assets/music/${encodeURIComponent(name)}`, {
    method: "DELETE"
  });
}


export async function deleteImageAsset(name: string): Promise<void> {
  await request(`/api/v1/assets/images/${encodeURIComponent(name)}`, {
    method: "DELETE"
  });
}


export async function deleteFontAsset(name: string): Promise<void> {
  await request(`/api/v1/assets/fonts/${encodeURIComponent(name)}`, {
    method: "DELETE"
  });
}


export interface AssistantAction {
  id: string;
  tool: string;
  arguments: Record<string, unknown>;
}

export interface AssistantTurn {
  ok: boolean;
  message: string;
  actions: AssistantAction[];
  observations: Array<Record<string, unknown>>;
  diff: Array<Record<string, unknown>>;
  requires_approval: boolean;
  approval_id: string;
  tokens: number;
  cost_usd: number;
  budget_usd: number;
  remaining_usd: number | null;
}

export interface AssistantHistoryEntry {
  at: string;
  prompt: string;
  message: string;
  actions: AssistantAction[];
  applied: boolean;
  approval_id: string;
  tokens: number;
  cost_usd: number;
}

export async function assistantTurn(
  jobId: string,
  prompt: string
): Promise<AssistantTurn> {
  return request<AssistantTurn>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/assistant`,
    { method: "POST", body: JSON.stringify({ prompt }) }
  );
}

export async function approveAssistant(
  jobId: string,
  approvalId: string
): Promise<Array<Record<string, unknown>>> {
  const response = await request<{ ok: boolean; results: Array<Record<string, unknown>> }>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/assistant/approve`,
    { method: "POST", body: JSON.stringify({ approval_id: approvalId }) }
  );
  return response.results;
}

export async function getAssistantHistory(
  jobId: string
): Promise<AssistantHistoryEntry[]> {
  const response = await request<{
    ok: boolean;
    history: AssistantHistoryEntry[];
  }>(`/api/v1/jobs/${encodeURIComponent(jobId)}/assistant/history`);
  return response.history;
}


export interface RunDagNode {
  id: string;
  label: string;
  type: string;
  needs: string[];
  status: string;
  progress: number;
  duration_ms: number | null;
  message: string;
  error: string | null;
}

export interface RunDag {
  ok: boolean;
  job_id: string;
  recipe_id: string;
  attempts: number;
  nodes: RunDagNode[];
  edges: Array<{ from: string; to: string }>;
  timing: { duration_ms: number | null; p50_ms: number; p95_ms: number; samples: number };
  retry: { max_attempts: number; backoff_seconds: number };
  previous: { job_id: string; duration_ms: number | null } | null;
}

export async function getJobDag(jobId: string): Promise<RunDag> {
  return request<RunDag>(`/api/v1/jobs/${encodeURIComponent(jobId)}/dag`);
}


export interface VariantItem {
  id: string;
  kind: string;
  name: string;
  path?: string;
  score?: number;
  duration_sec?: number;
  metrics: Record<string, number | null>;
}

export interface VariantComparison {
  ok: boolean;
  items: VariantItem[];
  thumbnails: Array<{ name: string; metrics: Record<string, number> }>;
  winner: string;
  count: number;
}

export async function getJobVariants(jobId: string): Promise<VariantComparison> {
  return request<VariantComparison>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/variants`
  );
}

export async function selectJobVariant(
  jobId: string,
  name: string
): Promise<string> {
  const response = await request<{ ok: boolean; winner: string }>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/variants/select`,
    { method: "POST", body: JSON.stringify({ name }) }
  );
  return response.winner;
}


export interface FrameBatch {
  ok: boolean;
  revision: number;
  height: number;
  frames: Array<{ time: number; url: string; cached: boolean }>;
}

export async function prefetchJobFrames(
  jobId: string,
  start: number,
  count = 6,
  fps = 4,
  height = 180
): Promise<FrameBatch> {
  const params = new URLSearchParams({
    start: String(Math.max(0, start)),
    count: String(count),
    fps: String(fps),
    height: String(height)
  });
  return request<FrameBatch>(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/frames?${params.toString()}`
  );
}


export interface VoiceCloneStatus {
  ok: boolean;
  available: boolean;
  provider: string;
  providers: string[];
  consent_required: boolean;
  reason: string;
  profiles: number;
}

export interface VoiceProfile {
  id: string;
  name: string;
  provider: string;
  consent_ref: string;
  sample_count: number;
  sample_paths?: string[];
  provider_voice_id?: string;
  created_at: string;
  metadata: Record<string, string>;
}

export async function getVoiceCloneStatus(): Promise<VoiceCloneStatus> {
  return request<VoiceCloneStatus>("/api/v1/voice-clone/status");
}

export async function listVoiceProfiles(): Promise<VoiceProfile[]> {
  const response = await request<{ ok: boolean; profiles: VoiceProfile[] }>(
    "/api/v1/voice-clone/profiles"
  );
  return response.profiles;
}

export async function createVoiceProfile(payload: {
  name: string;
  consent_ref: string;
  sample_count: number;
  sample_paths?: string[];
}): Promise<VoiceProfile> {
  const response = await request<{ ok: boolean; profile: VoiceProfile }>(
    "/api/v1/voice-clone/profiles",
    { method: "POST", body: JSON.stringify(payload) }
  );
  return response.profile;
}

export async function deleteVoiceProfile(profileId: string): Promise<void> {
  await request(`/api/v1/voice-clone/profiles/${encodeURIComponent(profileId)}`, {
    method: "DELETE"
  });
}


export interface NodePreset {
  id: string;
  step_type: string;
  name: string;
  params: Record<string, unknown>;
  favorite: boolean;
  builtin: boolean;
  created_at: string;
}

export async function listNodePresets(stepType = ""): Promise<NodePreset[]> {
  const params = stepType ? `?step_type=${encodeURIComponent(stepType)}` : "";
  const response = await request<{ ok: boolean; presets: NodePreset[] }>(
    `/api/v1/node-presets${params}`
  );
  return response.presets ?? [];
}

export async function createNodePreset(payload: {
  step_type: string;
  name: string;
  params: Record<string, unknown>;
}): Promise<NodePreset> {
  const response = await request<{ ok: boolean; preset: NodePreset }>(
    "/api/v1/node-presets",
    { method: "POST", body: JSON.stringify(payload) }
  );
  return response.preset;
}

export async function updateNodePreset(
  presetId: string,
  payload: { name?: string; params?: Record<string, unknown> }
): Promise<NodePreset> {
  const response = await request<{ ok: boolean; preset: NodePreset }>(
    `/api/v1/node-presets/${encodeURIComponent(presetId)}`,
    { method: "PATCH", body: JSON.stringify(payload) }
  );
  return response.preset;
}

export async function deleteNodePreset(presetId: string): Promise<void> {
  await request(`/api/v1/node-presets/${encodeURIComponent(presetId)}`, {
    method: "DELETE"
  });
}

export async function favoriteNodePreset(
  presetId: string,
  favorite: boolean
): Promise<NodePreset> {
  const response = await request<{ ok: boolean; preset: NodePreset }>(
    `/api/v1/node-presets/${encodeURIComponent(presetId)}/favorite`,
    { method: "POST", body: JSON.stringify({ favorite }) }
  );
  return response.preset;
}


export interface ProviderOption {
  id: string;
  name: string;
  capability: string;
  base_url: string;
  model: string;
  api_key_env: string;
  enabled: boolean;
  is_default: boolean;
  configured?: boolean;
  missing?: string[];
}

export interface NodeOptions {
  ok: boolean;
  providers: Record<string, ProviderOption[]>;
  services: ServiceDefinition[];
  models: Array<Record<string, unknown>>;
}

export interface StepOutputPort {
  id: string;
  label: string;
  type: string;
  hash: string;
  size_bytes: number;
  has_value: boolean;
}

export interface StepOutputs {
  ok: boolean;
  step_id: string;
  type: string;
  status: string;
  fingerprint: string;
  elapsed_ms: number;
  ports: StepOutputPort[];
  files: Array<{ name: string; path: string; exists: boolean; size_bytes: number }>;
  artifacts: Array<{ name: string; path: string }>;
}

export async function getStepOutputs(
  jobId: string,
  stepId: string
): Promise<StepOutputs> {
  return request(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/steps/${encodeURIComponent(stepId)}/outputs`
  );
}

export async function getStepOutputPort(
  jobId: string,
  stepId: string,
  portId: string
): Promise<{ ok: boolean; step_id: string; port: { id: string; label: string; type: string; value: unknown } }> {
  return request(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/steps/${encodeURIComponent(stepId)}/outputs/${encodeURIComponent(portId)}`
  );
}

export async function saveStepOutputs(
  jobId: string,
  stepId: string,
  targetDir: string
): Promise<{ ok: boolean; saved: string[] }> {
  return request(
    `/api/v1/jobs/${encodeURIComponent(jobId)}/steps/${encodeURIComponent(stepId)}/save`,
    { method: "POST", body: JSON.stringify({ target_dir: targetDir }) }
  );
}

export function stepOutputFileUrl(jobId: string, stepId: string, name: string): string {
  return `/api/v1/jobs/${encodeURIComponent(jobId)}/steps/${encodeURIComponent(stepId)}/files/${encodeURIComponent(name)}`;
}

export async function getNodeOptions(): Promise<NodeOptions> {
  const response = await request<NodeOptions>("/api/v1/node-options");
  return {
    ok: Boolean(response.ok),
    providers: response.providers ?? {},
    services: response.services ?? [],
    models: response.models ?? []
  };
}
