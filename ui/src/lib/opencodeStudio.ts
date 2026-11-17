import type {
  OpenCodeBootstrapRequest,
  OpenCodeBootstrapResult
} from "$lib/api";

export type McpProfile =
  | "core"
  | "decupagem"
  | "broll"
  | "audio"
  | "vision"
  | "full";

export const MCP_PROFILES: Array<{ id: McpProfile; label: string }> = [
  { id: "full", label: "Full (core + fetch + audio + vision)" },
  { id: "core", label: "Core" },
  { id: "decupagem", label: "Decupagem" },
  { id: "broll", label: "B-roll" },
  { id: "audio", label: "Audio" },
  { id: "vision", label: "Vision" }
];

export interface OpenCodeStudioForm {
  targetDir: string;
  profile: McpProfile;
  globalConfig: boolean;
  overwrite: boolean;
  withSample: boolean;
  registerRoot: boolean;
  prompts: boolean;
}

export function defaultStudioForm(): OpenCodeStudioForm {
  return {
    targetDir: "",
    profile: "full",
    globalConfig: false,
    overwrite: false,
    withSample: false,
    registerRoot: true,
    prompts: true
  };
}

export function canBootstrap(form: OpenCodeStudioForm): boolean {
  return form.targetDir.trim().length > 0;
}

export function bootstrapPayload(
  form: OpenCodeStudioForm
): OpenCodeBootstrapRequest {
  return {
    target_dir: form.targetDir.trim(),
    mcp_profile: form.profile,
    register_global_opencode: form.globalConfig,
    overwrite: form.overwrite,
    include_sample_project: form.withSample,
    register_root: form.registerRoot,
    prompts: form.prompts
  };
}

export function bootstrapHighlights(
  result: OpenCodeBootstrapResult
): string[] {
  const lines = [
    `${result.created_files.length} file(s) created`,
    `${result.copied_styles.length} style(s) synced`,
    `MCP: ${result.mcp_servers.join(", ") || "none"}`
  ];
  if (result.skipped_files.length) {
    lines.push(`${result.skipped_files.length} file(s) kept`);
  }
  if (result.sample_project?.ok) {
    lines.push("Sample 10s project ready");
  }
  return lines;
}
