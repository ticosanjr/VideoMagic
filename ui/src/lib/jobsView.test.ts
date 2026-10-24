import { describe, expect, it } from "vitest";
import type { Job } from "./api";
import { filterJobs, jobCounts, jobNextAction, matchesJobFilter } from "./jobsView";

function makeJob(overrides: Partial<Job>): Job {
  const base = {
    job_id: "job-a",
    status: "succeeded",
    progress: 100,
    stage: "done",
    message: "Done",
    source: "/media/source.mp4",
    output: "/out",
    options: {},
    result: null,
    error: null,
    created_at: "2026-10-20T10:00:00+00:00",
    started_at: "2026-10-20T10:00:00+00:00",
    finished_at: "2026-10-20T10:01:00+00:00",
    duration_ms: 60_000,
    log_count: 3,
    stages: []
  } as Job;
  return { ...base, ...overrides };
}

const jobs = [
  makeJob({ job_id: "job-a", status: "running", message: "Exporting" }),
  makeJob({ job_id: "job-b", status: "waiting_approval", message: "Approve the hook" }),
  makeJob({ job_id: "job-c", status: "failed", message: "ffmpeg failed" }),
  makeJob({ job_id: "job-d", status: "succeeded", message: "Ready" }),
  makeJob({ job_id: "job-e", status: "queued", message: "Waiting for a slot" })
];

describe("jobCounts", () => {
  it("counts every bucket the dashboard shows", () => {
    expect(jobCounts(jobs)).toEqual({
      total: 5,
      active: 1,
      queued: 1,
      paused: 0,
      waiting: 1,
      failed: 1,
      succeeded: 1
    });
  });
});

describe("matchesJobFilter", () => {
  it("matches the active bucket", () => {
    expect(matchesJobFilter(jobs[0], "active")).toBe(true);
    expect(matchesJobFilter(jobs[3], "active")).toBe(false);
  });

  it("matches attention for approvals and failures", () => {
    expect(matchesJobFilter(jobs[1], "attention")).toBe(true);
    expect(matchesJobFilter(jobs[2], "attention")).toBe(true);
    expect(matchesJobFilter(jobs[4], "attention")).toBe(false);
  });

  it("matches all statuses for the all bucket", () => {
    expect(jobs.every((job) => matchesJobFilter(job, "all"))).toBe(true);
  });
});

describe("filterJobs", () => {
  it("combines the bucket with a text query", () => {
    const result = filterJobs(jobs, { filter: "attention", query: "approve" });
    expect(result.map((job) => job.job_id)).toEqual(["job-b"]);
  });

  it("searches id, stage, message, source and recipe", () => {
    expect(filterJobs(jobs, { filter: "all", query: "job-" })).toHaveLength(5);
    expect(filterJobs(jobs, { filter: "all", query: "export" })[0].job_id).toBe("job-a");
    expect(filterJobs(jobs, { filter: "all", query: "source.mp4" })).toHaveLength(5);
  });

  it("is case insensitive and trims the query", () => {
    expect(filterJobs(jobs, { filter: "all", query: "  FFMPEG  " })[0].job_id).toBe("job-c");
  });
});

describe("jobNextAction", () => {
  it("tells the operator what to do next", () => {
    expect(jobNextAction(jobs[0])).toBe("Wait or cancel");
    expect(jobNextAction(jobs[1])).toBe("Review and approve");
    expect(jobNextAction(jobs[2])).toBe("Retry after fixing the error");
    expect(jobNextAction(jobs[4])).toBe("Waiting for a free slot");
    expect(jobNextAction(jobs[3])).toBe("Open the artifacts");
  });
});
