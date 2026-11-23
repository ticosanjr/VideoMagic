import { describe, expect, it } from "vitest";
import { render } from "svelte/server";
import CurationBoard from "./CurationBoard.svelte";
import GpuPanel from "./GpuPanel.svelte";
import SetupPanel from "./SetupPanel.svelte";
import StylesPanel from "./StylesPanel.svelte";

describe("three-screen panels render", () => {
  it("renders the curation board shell", () => {
    const { body } = render(CurationBoard);
    expect(body).toContain('data-testid="curation-board"');
    expect(body).toContain("Pending boards");
  });

  it("renders the consolidated setup shell", () => {
    const { body } = render(SetupPanel);
    expect(body).toContain('data-testid="setup-panel"');
    expect(body).toContain("Worker GPU");
    expect(body).toContain("Styles &amp; Workflows");
    expect(body).toContain("OpenCode &amp; Workspace");
  });

  it("renders the reusable GPU and style panels", () => {
    expect(render(GpuPanel).body).toContain('data-testid="gpu-panel"');
    expect(render(StylesPanel).body).toContain('data-testid="styles-panel"');
  });
});
