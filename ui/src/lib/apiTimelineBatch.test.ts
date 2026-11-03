import { afterEach, describe, expect, it, vi } from "vitest";
import { updateTimelineClips } from "./api";

describe("updateTimelineClips", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("sends one PATCH for the whole selection", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ok: true,
          revision: 4,
          applied: 2,
          can_undo: true,
          can_redo: false
        }),
        { status: 200, headers: { "content-type": "application/json" } }
      )
    );
    vi.stubGlobal("fetch", fetchMock);

    const result = await updateTimelineClips("job-1", ["v1", "v2"], {
      transition_type: "crossfade",
      transition_duration_frames: 8,
      scale: 1.2
    });

    expect(result).toMatchObject({ applied: 2, revision: 4 });
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [
      string,
      RequestInit
    ];
    expect(url).toBe("/api/v1/jobs/job-1/timeline/clips");
    expect(init.method).toBe("PATCH");
    expect(JSON.parse(String(init.body))).toEqual({
      transition_type: "crossfade",
      transition_duration_frames: 8,
      scale: 1.2,
      clip_ids: ["v1", "v2"]
    });
  });

  it("refuses an empty selection before calling the backend", async () => {
    const fetchMock = vi.fn();
    vi.stubGlobal("fetch", fetchMock);
    await expect(updateTimelineClips("job-1", [], { scale: 1 })).rejects.toThrow(
      "Select at least one clip"
    );
    expect(fetchMock).not.toHaveBeenCalled();
  });
});
