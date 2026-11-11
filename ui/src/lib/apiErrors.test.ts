import { describe, expect, it } from "vitest";
import { ApiError, describeError, formatBackendDetail } from "./api";
import { raiseApiError } from "./api/client";

describe("API error detail", () => {
  it("keeps the backend code, status, command and stderr", () => {
    const error = new ApiError(
      "ingest_failed",
      "ffmpeg was killed by SIGKILL",
      500,
      {
        code: "ingest_failed",
        message: "ffmpeg was killed by SIGKILL",
        command: "ffmpeg -i source.mp4",
        returncode: -9,
        signal: 9,
        stderr: "line one"
      }
    );

    const text = describeError(error);
    expect(text).toContain("HTTP 500");
    expect(text).toContain("code: ingest_failed");
    expect(text).toContain("returncode: -9");
    expect(text).toContain("signal: 9");
    expect(text).toContain("line one");
    expect(text).toContain("ffmpeg -i source.mp4");
  });

  it("formats plain backend detail objects", () => {
    const text = formatBackendDetail({
      code: "export_failed",
      message: "FFmpeg did not write timeline.mp4"
    });
    expect(text).toContain("code: export_failed");
    expect(text).toContain("did not write");
  });

  it("handles non-error values", () => {
    expect(describeError("plain")).toBe("plain");
    expect(formatBackendDetail(null)).toBe("");
  });

  it("can suppress the global notification for background polling", () => {
    const events: Event[] = [];
    const globals = globalThis as { window?: unknown };
    const previous = globals.window;
    globals.window = {
      dispatchEvent: (event: Event) => {
        events.push(event);
        return true;
      }
    };
    try {
      expect(() =>
        raiseApiError(
          new Response("{}", { status: 404, statusText: "Not Found" }),
          { detail: { code: "job_not_found", message: "Unknown job" } },
          "/api/v1/jobs/missing",
          "http_error",
          { silent: true }
        )
      ).toThrow(ApiError);
      expect(events).toHaveLength(0);
    } finally {
      globals.window = previous;
    }
  });
});
