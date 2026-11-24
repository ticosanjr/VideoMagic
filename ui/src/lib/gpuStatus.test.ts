import { describe, expect, it } from "vitest";
import { formatGb, gpuPill, toggleCapability, vramLabel } from "./gpuStatus";
import type { GpuWorkerStatus } from "./api";

const base: GpuWorkerStatus = {
  ok: true,
  mode: "auto",
  worker_url: "http://192.168.1.45:8766",
  execution_node: "remote_gpu:worker-1",
  available: true,
  worker_id: "worker-1",
  hostname: "gpu-host",
  ip_local: "192.168.1.45",
  port: 8766,
  gpu_name: "RTX 3060",
  vram_free_mb: 4096,
  vram_total_mb: 12288,
  vram_used_mb: 8192,
  gpu_utilization: 10,
  temperature_c: 42,
  capabilities: ["asr"],
  models: [],
  queue_depth: 0,
  message: ""
};

describe("gpu pill", () => {
  it("describes local, offline, ready, and busy states", () => {
    expect(gpuPill(null).tone).toBe("offline");
    expect(gpuPill({ ...base, available: false, mode: "local_only" })).toMatchObject({
      tone: "local",
      label: "Local mode (CPU)"
    });
    expect(gpuPill({ ...base, available: false }).label).toBe("GPU worker offline");
    expect(gpuPill(base)).toMatchObject({
      tone: "ready",
      label: "GPU: RTX 3060 · 4.0/12 GB"
    });
    expect(gpuPill({ ...base, queue_depth: 1 })).toMatchObject({
      tone: "busy",
      label: "GPU: RTX 3060 · 10% busy"
    });
    expect(
      gpuPill({
        ...base,
        mode: "local_gpu",
        available: true,
        gpu_name: "RTX 3060",
        nvenc: true,
        worker_url: ""
      })
    ).toMatchObject({
      tone: "ready",
      label: "GPU local: RTX 3060 · NVENC"
    });
  });

  it("formats VRAM and toggles capabilities immutably", () => {
    expect(formatGb(0)).toBe("0");
    expect(vramLabel(10240)).toBe("10 GB");
    const original = { asr: true };
    const updated = toggleCapability(original, "asr", false);
    expect(updated).toEqual({ asr: false });
    expect(original).toEqual({ asr: true });
  });
});
