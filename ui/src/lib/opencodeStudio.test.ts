import { describe, expect, it } from "vitest";
import {
  bootstrapHighlights,
  bootstrapPayload,
  canBootstrap,
  defaultStudioForm
} from "./opencodeStudio";

describe("opencode studio form", () => {
  it("starts in full profile with root registration and prompts", () => {
    const form = defaultStudioForm();
    expect(form.profile).toBe("full");
    expect(form.registerRoot).toBe(true);
    expect(form.prompts).toBe(true);
    expect(canBootstrap(form)).toBe(false);
  });

  it("trims the target and serializes every option", () => {
    const form = {
      ...defaultStudioForm(),
      targetDir: "  /tmp/workspace  ",
      profile: "core" as const,
      globalConfig: true,
      overwrite: true,
      withSample: true,
      registerRoot: false,
      prompts: false
    };
    expect(canBootstrap(form)).toBe(true);
    expect(bootstrapPayload(form)).toEqual({
      target_dir: "/tmp/workspace",
      mcp_profile: "core",
      register_global_opencode: true,
      overwrite: true,
      include_sample_project: true,
      register_root: false,
      prompts: false
    });
  });

  it("summarizes created files, styles, MCP servers and sample", () => {
    const lines = bootstrapHighlights({
      ok: true,
      status: "ok",
      target_dir: "/tmp/workspace",
      created_files: ["a", "b"],
      skipped_files: ["c"],
      copied_styles: ["canal-paula-reels"],
      mcp_servers: ["core", "fetch"],
      launch_command: 'cd "/tmp/workspace" && opencode',
      sample_project: { ok: true },
      registered_root: true,
      warnings: []
    });
    expect(lines).toEqual([
      "2 file(s) created",
      "1 style(s) synced",
      "MCP: core, fetch",
      "1 file(s) kept",
      "Sample 10s project ready"
    ]);
  });
});
