import { describe, expect, it } from "vitest";
import {
  createNotice,
  noticeAllowed,
  noticeCounts,
  sortNotices,
  type Notice
} from "./notifications";

describe("createNotice", () => {
  it("fills defaults for a transient info notice", () => {
    const notice = createNotice({ kind: "info", title: "Hello" });
    expect(notice.kind).toBe("info");
    expect(notice.persistent).toBe(false);
    expect(notice.id).toMatch(/^notice-/);
    expect(notice.createdAt).toBeTypeOf("string");
  });

  it("keeps persistent errors visible", () => {
    const notice = createNotice({
      kind: "error",
      title: "Render failed",
      message: "ffmpeg exited with 1",
      code: "RENDER_FAILED",
      actionLabel: "Retry"
    });
    expect(notice.persistent).toBe(true);
    expect(notice.actionLabel).toBe("Retry");
    expect(notice.code).toBe("RENDER_FAILED");
  });

  it("always creates unique ids", () => {
    const ids = new Set(
      Array.from({ length: 25 }, () => createNotice({ kind: "success", title: "ok" }).id)
    );
    expect(ids.size).toBe(25);
  });
});

describe("sortNotices", () => {
  it("keeps errors above successes and newest first within a kind", () => {
    const notices: Notice[] = [
      { ...createNotice({ kind: "success", title: "done" }), createdAt: "2026-10-20T10:00:00.000Z" },
      { ...createNotice({ kind: "error", title: "boom" }), createdAt: "2026-10-20T09:00:00.000Z" },
      { ...createNotice({ kind: "error", title: "bang" }), createdAt: "2026-10-20T11:00:00.000Z" }
    ];
    expect(sortNotices(notices).map((notice) => notice.title)).toEqual([
      "bang",
      "boom",
      "done"
    ]);
  });

  it("does not mutate the input", () => {
    const notices = [createNotice({ kind: "info", title: "one" })];
    const copy = [...notices];
    sortNotices(notices);
    expect(notices).toEqual(copy);
  });
});

describe("noticeCounts", () => {
  it("separates errors from the rest", () => {
    const notices = [
      createNotice({ kind: "error", title: "a" }),
      createNotice({ kind: "warning", title: "b" }),
      createNotice({ kind: "success", title: "c" })
    ];
    expect(noticeCounts(notices)).toEqual({ total: 3, errors: 1, warnings: 1 });
  });
});


describe("noticeAllowed", () => {
  it("sends nothing while notifications are off", () => {
    expect(noticeAllowed("off", { kind: "info", category: "hilt", title: "Review" })).toBe(false);
    expect(noticeAllowed("off", { kind: "error", category: "blocker", title: "Boom" })).toBe(false);
  });

  it("keeps only HITL in required mode", () => {
    expect(noticeAllowed("required", { kind: "info", category: "hilt", title: "Review" })).toBe(true);
    expect(noticeAllowed("required", { kind: "info", category: "job_finished", title: "Done" })).toBe(false);
    expect(noticeAllowed("required", { kind: "error", category: "blocker", title: "Boom" })).toBe(false);
  });

  it("adds failures in important mode and everything in all", () => {
    expect(noticeAllowed("important", { kind: "error", category: "blocker", title: "Boom" })).toBe(true);
    expect(noticeAllowed("important", { kind: "warning", category: "job_failed", title: "Failed" })).toBe(true);
    expect(noticeAllowed("important", { kind: "info", category: "job_finished", title: "Done" })).toBe(false);
    expect(noticeAllowed("all", { kind: "info", category: "system", title: "Ping" })).toBe(true);
    expect(noticeAllowed("all", { kind: "success", category: "action", title: "Saved" })).toBe(true);
  });
});
