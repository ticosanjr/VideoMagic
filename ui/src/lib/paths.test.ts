import { describe, expect, it } from "vitest";
import { baseName, parentPath, suggestOutputPath } from "./paths";

describe("path helpers", () => {
  it("reads names and parents on POSIX paths", () => {
    expect(baseName("/media/interview.mp4")).toBe("interview.mp4");
    expect(parentPath("/media/interview.mp4")).toBe("/media");
    expect(parentPath("/interview.mp4")).toBe("/");
  });

  it("reads names and parents on Windows paths", () => {
    expect(baseName("C:\\media\\interview.mp4")).toBe("interview.mp4");
    expect(parentPath("C:\\media\\interview.mp4")).toBe("C:\\media");
    expect(parentPath("C:\\interview.mp4")).toBe("C:\\");
  });

  it("suggests a sibling project directory", () => {
    expect(suggestOutputPath("/media/interview.mp4")).toBe("/media/interview-videoflow");
    expect(suggestOutputPath("C:\\media\\interview.mp4")).toBe(
      "C:\\media\\interview-videoflow"
    );
    expect(suggestOutputPath("interview.mp4")).toBe("interview-videoflow");
  });
});
