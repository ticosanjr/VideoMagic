import type { Job } from "./api";

export type JobFilter =
  | "all"
  | "active"
  | "queued"
  | "paused"
  | "attention"
  | "failed"
  | "succeeded";

export interface JobCounts {
  total: number;
  active: number;
  queued: number;
  paused: number;
  waiting: number;
  failed: number;
  succeeded: number;
}

export interface JobQuery {
  filter: JobFilter;
  query: string;
}

const ACTIVE_STATUSES = new Set(["running"]);
const ATTENTION_STATUSES = new Set(["waiting_approval", "waiting_input", "failed"]);

export function jobCounts(jobs: Job[]): JobCounts {
  return jobs.reduce<JobCounts>(
    (counts, job) => {
      counts.total += 1;
      if (ACTIVE_STATUSES.has(job.status)) counts.active += 1;
      if (job.status === "queued") counts.queued += 1;
      if (job.status === "paused") counts.paused += 1;
      if (job.status === "waiting_approval") counts.waiting += 1;
      if (job.status === "waiting_input") counts.waiting += 1;
      if (job.status === "failed") counts.failed += 1;
      if (job.status === "succeeded") counts.succeeded += 1;
      return counts;
    },
    { total: 0, active: 0, queued: 0, paused: 0, waiting: 0, failed: 0, succeeded: 0 }
  );
}

export function matchesJobFilter(job: Job, filter: JobFilter): boolean {
  switch (filter) {
    case "active":
      return ACTIVE_STATUSES.has(job.status);
    case "queued":
      return job.status === "queued";
    case "paused":
      return job.status === "paused";
    case "attention":
      return ATTENTION_STATUSES.has(job.status);
    case "failed":
      return job.status === "failed";
    case "succeeded":
      return job.status === "succeeded";
    default:
      return true;
  }
}

export function jobSearchText(job: Job): string {
  return [
    job.job_id,
    job.status,
    job.stage,
    job.message,
    job.source,
    job.result?.recipe_id
  ]
    .filter(Boolean)
    .join(" ")
    .toLowerCase();
}

export function filterJobs(jobs: Job[], { filter, query }: JobQuery): Job[] {
  const needle = query.trim().toLowerCase();
  return jobs.filter((job) => {
    if (!matchesJobFilter(job, filter)) return false;
    if (!needle) return true;
    return jobSearchText(job).includes(needle);
  });
}

export function jobNextAction(job: Job): string {
  switch (job.status) {
    case "queued":
      return "Waiting for a free slot";
    case "paused":
      return "Resume when ready";
    case "running":
      return "Wait or cancel";
    case "waiting_approval":
      return "Review and approve";
    case "waiting_input":
      return "Answer or upload files";
    case "failed":
      return "Retry after fixing the error";
    case "succeeded":
      return "Open the artifacts";
    default:
      return "No action needed";
  }
}

export function jobDisplayName(job: Job): string {
  const source = job.source.split("/").filter(Boolean).at(-1);
  return source || job.result?.recipe_id || job.job_id;
}
