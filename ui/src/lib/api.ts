export type JobStatus = "queued" | "running" | "succeeded" | "failed" | "cancelled";

export interface SystemInfo {
  ok: boolean;
  version: string;
  home: string;
  allowed_roots: string[];
  ffmpeg: string | null;
  ffprobe: string | null;
}

export interface JobOptions {
  noise_db: number;
  min_silence_ms: number;
  jcut: boolean;
  lcut: boolean;
  zooms: boolean;
  dialect: "1.9" | "1.10";
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
    warnings?: string[];
    artifacts?: Record<string, string>;
    state_path?: string;
    report_path?: string;
    elapsed_seconds?: number;
  } | null;
  error: { ok: boolean; code: string; message: string } | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface NewJob {
  source: string;
  output: string;
  noise_db: number;
  min_silence_ms: number;
  jcut: boolean;
  lcut: boolean;
  zooms: boolean;
  dialect: "1.9" | "1.10";
  transcript: string | null;
  cull_retakes: boolean;
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

export async function createJob(payload: NewJob): Promise<Job> {
  const response = await request<{ ok: boolean; job: Job }>("/api/v1/jobs", {
    method: "POST",
    body: JSON.stringify(payload)
  });
  return response.job;
}

export async function getJob(jobId: string): Promise<Job> {
  const response = await request<{ ok: boolean; job: Job }>(`/api/v1/jobs/${jobId}`);
  return response.job;
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

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return `${error.code}: ${error.message}`;
  if (error instanceof Error) return error.message;
  return String(error);
}
