import type { GpuWorkerStatus } from "./api";

export type GpuPillTone = "ready" | "busy" | "local" | "offline";

export interface GpuPillView {
  tone: GpuPillTone;
  label: string;
}

export function formatGb(mb: number): string {
  if (!Number.isFinite(mb) || mb <= 0) return "0";
  return (mb / 1024).toFixed(mb >= 10_240 ? 0 : 1);
}

export function gpuPill(status: GpuWorkerStatus | null | undefined): GpuPillView {
  if (!status) return { tone: "offline", label: "GPU: checking…" };
  if (!status.available) {
    if (status.mode === "local_only") {
      return { tone: "local", label: "Local mode (CPU)" };
    }
    return { tone: "offline", label: "GPU worker offline" };
  }
  const name = status.gpu_name || status.hostname || "Windows GPU";
  if (status.queue_depth > 0 || status.gpu_utilization >= 50) {
    return {
      tone: "busy",
      label: `GPU: ${name} · ${Math.round(status.gpu_utilization)}% busy`
    };
  }
  const free = formatGb(status.vram_free_mb);
  const total = formatGb(status.vram_total_mb);
  return {
    tone: "ready",
    label: `GPU: ${name} · ${free}/${total} GB`
  };
}

export function toggleCapability(
  capabilities: Record<string, boolean>,
  key: string,
  value: boolean
): Record<string, boolean> {
  return { ...capabilities, [key]: value };
}

export function vramLabel(mb: number): string {
  return `${formatGb(mb)} GB`;
}
