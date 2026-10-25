import { afterEach, describe, expect, it, vi } from "vitest";
import { prefetchJobFrames } from "./api";

describe("prefetchJobFrames", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("requests a bounded batch and returns its urls", async () => {
    const fetchMock = vi.fn(async () =>
      new Response(
        JSON.stringify({
          ok: true,
          revision: 3,
          height: 180,
          frames: [
            { time: 1, url: "/frame?time=1&height=180", cached: true },
            { time: 1.25, url: "/frame?time=1.25&height=180", cached: false }
          ]
        }),
        { status: 200, headers: { "content-type": "application/json" } }
      )
    );
    vi.stubGlobal("fetch", fetchMock);
    const payload = await prefetchJobFrames("job-1", 1, 6, 4, 180);
    expect(payload.frames).toHaveLength(2);
    const calls = fetchMock.mock.calls as unknown as Array<[string]>;
    const url = String(calls[0][0]);
    expect(url).toContain("/api/v1/jobs/job-1/frames?");
    expect(url).toContain("count=6");
    expect(url).toContain("fps=4");
    expect(url).toContain("height=180");
  });
});
