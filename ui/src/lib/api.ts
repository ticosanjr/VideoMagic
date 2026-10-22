export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";
export type StageStatus = "pending" | "running" | "succeeded" | "failed" | "cancelled";

export interface SystemInfo {
  ok: boolean;
  version: string;
  home: string;
  allowed_roots: string[];
  ffmpeg: string | null;
  ffprobe: string | null;
}

export interface LocalModel {
  id: string;
  label: string;
  size_mb: number;
  kind: string;
  installed: boolean;
  path: string;
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

export interface Job {
  job_id: string;
  status: JobStatus;
  progress: number;
  stage: string;
  message: string;
  source: string;
  output: string;
  options: Partial<JobOptions>;
  result: {
    ok: boolean;
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
    shorts?: ShortClip[];
    state_path?: string;
    report_path?: string;
    elapsed_seconds?: number;
  } | null;
  error: { ok: boolean; code: string; message: string } | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
  log_count: number;
  stages: JobStage[];
}

export interface RecipeStep {
  id: string;
  type: string;
  needs: string[];
  enabled: boolean;
  params: Record<string, unknown>;
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
  steps: RecipeStep[];
}

export interface StepManifest {
  type: string;
  title: string;
  description: string;
  requires: string[];
  produces: string[];
  params_schema: Record<string, unknown>;
}

export interface RecipeSummary {
  id: string;
  name: string;
  description: string;
  source: string;
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

export interface StepRun {
  id: string;
  type: string;
  status: "cached" | "executed";
  elapsed_ms: number;
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

export interface NewJob {
  source: string;
  output: string;
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
  shorts: boolean;
  shorts_count: number;
  shorts_min_sec: number;
  shorts_max_sec: number;
  shorts_subtitles: boolean;
  transcribe: boolean;
  asr_base_url: string | null;
  asr_model: string;
  asr_language: string;
  fade_in_ms: number;
  fade_out_ms: number;
  fade_curve: string;
  zoom_min_scale: number;
  zoom_max_scale: number;
  shorts_min_count: number;
  shorts_selection_mode: string;
  shorts_prompt: string;
  shorts_reprompt: string;
  shorts_prompt_mode: "replace" | "refine";
  shorts_hook_mode: "off" | "metadata" | "repeat" | "reorder";
  shorts_reframe_mode: "center_crop_9_16" | "motion_tracking" | "face_tracking" | "auto_face_tracking_yolo";
  shorts_audio_energy_boost: boolean;
  shorts_scene_change_boost: boolean;
  shorts_remove_fillers: boolean;
  shorts_filler_words: string[];
  shorts_aspect: string;
  shorts_resolution: number;
  shorts_source_start_sec: number;
  shorts_source_end_sec: number | null;
  allow_external_services: boolean;
  allowed_external_hosts: string[];
  audio_enhance: boolean;
  audio_highpass_hz: number;
  audio_denoise: boolean;
  audio_denoise_db: number;
  audio_noise_floor_db: number;
  audio_loudnorm: boolean;
  audio_target_lufs: number;
  audio_true_peak_db: number;
  overlay_enabled: boolean;
  overlay_asset: string;
  overlay_position: string;
  overlay_margin_px: number;
  overlay_width_ratio: number;
  overlay_opacity: number;
  music_enabled: boolean;
  music_asset: string;
  music_volume: number;
  music_ducking: boolean;
  music_fade_in_ms: number;
  music_fade_out_ms: number;
  intro_enabled: boolean;
  intro_asset: string;
  intro_duration_sec: number;
  outro_enabled: boolean;
  outro_asset: string;
  outro_duration_sec: number;
  caption_font_family: string;
  caption_font_size: number;
  caption_font_weight: string;
  caption_italic: boolean;
  caption_uppercase: boolean;
  caption_primary_color: string;
  caption_highlight_color: string;
  caption_outline_color: string;
  caption_outline_width: number;
  caption_shadow_color: string;
  caption_shadow_offset: number;
  caption_shadow_opacity: number;
  caption_background_color: string;
  caption_background_opacity: number;
  caption_background_padding: number;
  caption_alignment: number;
  caption_position_x: number;
  caption_position_y: number;
  caption_max_width: number;
  caption_animation: string;
  caption_word_timing: string;
  caption_censor_enabled: boolean;
  caption_censor_words: string[];
  caption_censor_replacement: string;
  caption_keyword_highlight_enabled: boolean;
  caption_keyword_color: string;
  caption_keyword_words: string[];
  caption_emoji_enabled: boolean;
  caption_emoji_map: Record<string, string>;
  caption_brand_vocabulary: Record<string, string>;
  overrides: { sentence_id: number; action: "keep" | "discard" }[];
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

class ApiError extends Error {
  code: string;

  constructor(code: string, message: string) {
    super(message);
    this.code = code;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init
  });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload?.detail;
    if (detail && typeof detail === "object") {
      throw new ApiError(detail.code ?? "http_error", detail.message ?? response.statusText);
    }
    throw new ApiError("http_error", payload?.detail ?? response.statusText);
  }
  return payload as T;
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

export async function installLocalModel(
  modelId: string,
  allowExternal = true
): Promise<LocalModel> {
  const response = await request<{ ok: boolean; model: LocalModel }>(
    `/api/v1/models/${encodeURIComponent(modelId)}/install`,
    {
      method: "POST",
      body: JSON.stringify({ allow_external_services: allowExternal })
    }
  );
  return response.model;
}

export async function removeLocalModel(modelId: string): Promise<void> {
  await request(`/api/v1/models/${encodeURIComponent(modelId)}`, { method: "DELETE" });
}

export function getSystem(): Promise<SystemInfo> {
  return request<SystemInfo>("/api/v1/system");
}

export async function getFsRoots(): Promise<FsRoot[]> {
  const response = await request<{ ok: boolean; roots: FsRoot[] }>("/api/v1/fs/roots");
  return response.roots;
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

export async function importMedia(
  url: string,
  options: {
    max_height?: number;
    allow_playlist?: boolean;
    allow_external_services?: boolean;
    allowed_external_hosts?: string[];
  } = {}
): Promise<ImportedMedia> {
  return request<ImportedMedia>("/api/v1/media/import", {
    method: "POST",
    body: JSON.stringify({ url, ...options })
  });
}

export function probeMedia(path: string): Promise<ProbedMedia> {
  const query = new URLSearchParams({ path });
  return request<ProbedMedia>(`/api/v1/media/probe?${query.toString()}`);
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

export async function exportConfig(options: Record<string, unknown>): Promise<Record<string, unknown>> {
  const response = await request<{ ok: boolean; envelope: Record<string, unknown> }>(
    "/api/v1/config/export",
    { method: "POST", body: JSON.stringify({ options }) }
  );
  return response.envelope;
}

export async function importConfig(
  schemaVersion: number,
  options: Record<string, unknown>
): Promise<Record<string, unknown>> {
  const response = await request<{ ok: boolean; options: Record<string, unknown> }>(
    "/api/v1/config/import",
    { method: "POST", body: JSON.stringify({ schema_version: schemaVersion, options }) }
  );
  return response.options;
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
  const response = await fetch(`/api/v1/assets/music?name=${encodeURIComponent(file.name)}`, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: file
  });
  const payload = await response.json();
  if (!response.ok) {
    const detail = payload?.detail;
    throw new ApiError(
      detail?.code ?? "music_upload_failed",
      detail?.message ?? "Music upload failed"
    );
  }
  return payload.music as MusicAsset;
}

export async function getImages(): Promise<ImageAsset[]> {
  const response = await request<{ ok: boolean; images: ImageAsset[] }>("/api/v1/assets/images");
  return response.images;
}

export async function uploadImage(file: File): Promise<ImageAsset> {
  const response = await fetch(`/api/v1/assets/images?name=${encodeURIComponent(file.name)}`, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: file
  });
  const payload = await response.json();
  if (!response.ok) {
    const detail = payload?.detail;
    throw new ApiError(
      detail?.code ?? "image_upload_failed",
      detail?.message ?? "Image upload failed"
    );
  }
  return payload.image as ImageAsset;
}

export async function getFonts(): Promise<FontAsset[]> {
  const response = await request<{ ok: boolean; fonts: FontAsset[] }>("/api/v1/assets/fonts");
  return response.fonts;
}

export async function uploadFont(file: File): Promise<FontAsset> {
  const response = await fetch(`/api/v1/assets/fonts?name=${encodeURIComponent(file.name)}`, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: file
  });
  const payload = await response.json();
  if (!response.ok) {
    const detail = payload?.detail;
    throw new ApiError(
      detail?.code ?? "font_upload_failed",
      detail?.message ?? "Font upload failed"
    );
  }
  return payload.font as FontAsset;
}

export async function getCapabilities(allowExternal = false): Promise<CapabilitiesResponse> {
  return request<CapabilitiesResponse>(
    `/api/v1/capabilities?allow_external=${allowExternal ? "true" : "false"}`
  );
}

export async function createJob(payload: NewJob): Promise<Job> {
  const response = await request<{ ok: boolean; job: Job }>("/api/v1/jobs", {
    method: "POST",
    body: JSON.stringify(payload)
  });
  return response.job;
}

export async function listRecipeSteps(): Promise<StepManifest[]> {
  const response = await request<{ ok: boolean; steps: StepManifest[] }>("/api/v1/steps");
  return response.steps;
}

export async function listRecipes(): Promise<RecipeSummary[]> {
  const response = await request<{ ok: boolean; recipes: RecipeSummary[] }>("/api/v1/recipes");
  return response.recipes;
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

export async function validateRecipe(
  recipe: Recipe
): Promise<{ ok: boolean; recipe: Recipe; order: string[] }> {
  return request<{ ok: boolean; recipe: Recipe; order: string[] }>("/api/v1/recipes/validate", {
    method: "POST",
    body: JSON.stringify(recipe)
  });
}

export async function runRecipe(payload: {
  source: string;
  output: string;
  recipe: Recipe;
  save_recipe?: boolean;
  resume?: boolean;
  through?: string | null;
}): Promise<Job> {
  const response = await request<{ ok: boolean; job: Job }>("/api/v1/recipes/run", {
    method: "POST",
    body: JSON.stringify(payload)
  });
  return response.job;
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

export async function getBatch(batchId: string): Promise<Batch> {
  const response = await request<{ ok: boolean; batch: Batch }>(
    `/api/v1/batches/${encodeURIComponent(batchId)}`
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

export async function runRecipeStep(
  stepId: string,
  payload: {
    source: string;
    output: string;
    recipe: Recipe;
    save_recipe?: boolean;
    resume?: boolean;
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
    base_url?: string;
    model?: string;
    voice?: string;
    allow_external_services?: boolean;
    allowed_external_hosts?: string[];
  }
): Promise<{ ok: boolean; voiceover: ShortVoiceover; short: ShortClip }> {
  return request(`/api/v1/jobs/${jobId}/shorts/${index}/voiceover`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export async function analyzeShortLlm(
  jobId: string,
  index: number,
  payload: {
    base_url?: string;
    model?: string;
    max_frames?: number;
    allow_external_services?: boolean;
    allowed_external_hosts?: string[];
  }
): Promise<{ ok: boolean; analysis: ShortVisionAnalysis; short: ShortClip }> {
  return request(`/api/v1/jobs/${jobId}/shorts/${index}/analyze/llm`, {
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

export async function getJob(jobId: string): Promise<Job> {
  const response = await request<{ ok: boolean; job: Job }>(`/api/v1/jobs/${jobId}`);
  return response.job;
}

export async function listJobs(): Promise<Job[]> {
  const response = await request<{ ok: boolean; jobs: Job[] }>("/api/v1/jobs");
  return response.jobs;
}

export async function cancelJob(jobId: string): Promise<Job> {
  const response = await request<{ ok: boolean; job: Job }>(`/api/v1/jobs/${jobId}/cancel`, {
    method: "POST"
  });
  return response.job;
}

export function getJobState(jobId: string): Promise<JobState> {
  return request<JobState>(`/api/v1/jobs/${jobId}/state`);
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

export function logDownloadUrl(jobId: string, module?: string): string {
  const params = new URLSearchParams({ download: "1" });
  if (module) params.set("module", module);
  return `/api/v1/jobs/${jobId}/logs?${params.toString()}`;
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return `${error.code}: ${error.message}`;
  if (error instanceof Error) return error.message;
  return String(error);
}
