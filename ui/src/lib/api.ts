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
  shorts_aspect?: string;
  shorts_source_start_sec?: number;
  shorts_source_end_sec?: number | null;
  allow_external_services?: boolean;
  allowed_external_hosts?: string[];
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
  aspect_ratio?: string;
  width?: number;
  height?: number;
  subtitles?: string;
  caption_style?: Record<string, unknown>;
  edited_at?: string;
  edit_count?: number;
  previous_path?: string;
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
  shorts_aspect: string;
  shorts_source_start_sec: number;
  shorts_source_end_sec: number | null;
  allow_external_services: boolean;
  allowed_external_hosts: string[];
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

export function probeMedia(path: string): Promise<ProbedMedia> {
  const query = new URLSearchParams({ path });
  return request<ProbedMedia>(`/api/v1/media/probe?${query.toString()}`);
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
