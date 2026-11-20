import { describe, expect, it } from "vitest";
import { render } from "svelte/server";
import FormatsPanel from "./FormatsPanel.svelte";
import GpuPanel from "./GpuPanel.svelte";
import HelpPanel from "./HelpPanel.svelte";
import StylesPanel from "./StylesPanel.svelte";

describe("setup panels render", () => {
  it("renders the format editor shell", () => {
    const { body } = render(FormatsPanel);
    expect(body).toContain('data-testid="formats-panel"');
    expect(body).toContain("Output formats");
  });

  it("renders the style editor shell", () => {
    const { body } = render(StylesPanel);
    expect(body).toContain('data-testid="styles-panel"');
    expect(body).toContain("Style catalog");
  });

  it("renders searchable help sections", () => {
    const { body } = render(HelpPanel);
    expect(body).toContain('data-testid="help-panel"');
    expect(body).toContain("Job progress, priority and queue");
    expect(body).toContain("Worker security and audit");
  });

  it("renders the GPU panel shell", () => {
    const { body } = render(GpuPanel);
    expect(body).toContain('data-testid="gpu-panel"');
    expect(body).toContain("Worker activity");
  });
});
