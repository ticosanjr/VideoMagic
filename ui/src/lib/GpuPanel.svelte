<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import {
    benchmarkGpu,
    connectGpuWorker,
    disconnectGpuWorker,
    discoverGpuWorkers,
    downloadGpuWorkerKit,
    getGpuActivity,
    getGpuStatus,
    patchGpuSettings,
    runGpuSelftest,
    unloadGpuModels,
    validateGpuShared,
    type GpuActivity,
    type GpuBenchmark,
    type GpuDiscoveredWorker,
    type GpuWorkerStatus
  } from "$lib/api";
  import { formatGb, vramLabel } from "$lib/gpuStatus";

  const CAPABILITIES = [
    ["asr", "Transcription (Whisper)"],
    ["forced_align", "Forced alignment"],
    ["scene_analyze", "Scene intelligence"],
    ["short_render", "Dynamic Short render"],
    ["ffmpeg_transcode", "FFmpeg transcode"],
    ["audio_events", "Acoustic event tagging"],
    ["vision_blur", "Visual blur audit"],
    ["render_nvenc", "NVENC master render"],
    ["segment_matte", "Background matte"],
    ["face_track", "Face tracking"],
    ["stems", "Stem separation"],
    ["upscale", "Upscale"],
    ["tts", "Text to speech"],
    ["comfyui", "ComfyUI"]
  ] as const;

  let status = $state<GpuWorkerStatus | null>(null);
  let capabilities = $state<Record<string, boolean>>({});
  let sharedEnabled = $state(false);
  let sharedPath = $state("");
  let maxVram = $state(10240);
  let maxUtilization = $state(70);
  let fallback = $state(true);
  let discoveryEnabled = $state(true);
  let workerUrl = $state("");
  let manualUrl = $state("");
  let manualToken = $state("");
  let manualWorkerId = $state("");
  let autoConnecting = $state(false);
  let activity = $state<GpuActivity | null>(null);
  let discovered = $state<GpuDiscoveredWorker[]>([]);
  let discoveryInfo = $state<{ udp: number; mdns?: number; tcp_scan: number; subnets?: string[]; elapsed_ms: number } | null>(null);
  let benchmark = $state<GpuBenchmark | null>(null);
  let selftest = $state<{ job_id: string; state: string; elapsed_sec: number } | null>(null);
  let busy = $state("");
  let error = $state("");
  let notice = $state("");
  let loading = $state(true);

  function applyStatus(next: GpuWorkerStatus) {
    status = next;
    workerUrl = next.worker_url || "";
    capabilities = { ...(next.capabilities_enabled ?? capabilities) };
    sharedEnabled = Boolean(next.shared_mount_enabled);
    sharedPath = next.shared_windows_path || "";
    maxVram = next.max_vram_mb ?? maxVram;
    maxUtilization = next.max_gpu_utilization_pct ?? maxUtilization;
    fallback = next.fallback_local ?? true;
    discoveryEnabled = next.discovery_enabled ?? true;
  }

  async function refresh() {
    try {
      const payload = await getGpuStatus();
      applyStatus(payload.status);
      error = "";
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    } finally {
      loading = false;
    }
  }

  async function patch(patch: Record<string, unknown>, label: string) {
    busy = label;
    try {
      const payload = await patchGpuSettings(patch);
      applyStatus(payload.status);
      notice = "Saved.";
      error = "";
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    } finally {
      busy = "";
    }
  }

  async function connect(url = manualUrl, workerId = manualWorkerId) {
    const target = url.trim();
    if (!target) {
      error = "Enter the Windows worker URL first.";
      return;
    }
    busy = "connect";
    try {
      const payload = await connectGpuWorker({
        worker_url: target,
        token: manualToken.trim(),
        worker_id: workerId.trim(),
        mode: "auto"
      });
      applyStatus(payload.status);
      notice = payload.connected ? "Worker connected." : "Worker saved but not reachable.";
      error = "";
      manualToken = "";
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    } finally {
      busy = "";
    }
  }

  async function runSelftest() {
    busy = "selftest";
    selftest = null;
    try {
      selftest = await runGpuSelftest();
      notice = `Worker executed selftest job ${selftest.job_id} in ${selftest.elapsed_sec}s.`;
      error = "";
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    } finally {
      busy = "";
    }
  }

  async function disconnect() {
    busy = "disconnect";
    try {
      const payload = await disconnectGpuWorker();
      applyStatus(payload.status);
      notice = "Worker disconnected.";
      error = "";
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    } finally {
      busy = "";
    }
  }

  async function discover() {
    busy = "discover";
    try {
      const payload = await discoverGpuWorkers();
      discovered = payload.workers;
      discoveryInfo = payload.diagnostics ?? null;
      notice = payload.workers.length
        ? `${payload.workers.length} worker(s) found.`
        : "No worker found on the LAN (UDP beacon and TCP scan).";
      error = "";
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    } finally {
      busy = "";
    }
  }

  async function refreshActivity() {
    if (!status?.available) {
      activity = null;
      return;
    }
    try {
      const payload = await getGpuActivity();
      activity = payload.ok ? payload.overview ?? null : null;
    } catch {
      activity = null;
    }
  }

  async function runBenchmark() {
    busy = "benchmark";
    try {
      benchmark = await benchmarkGpu();
      error = benchmark.ok ? "" : "Worker did not answer.";
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    } finally {
      busy = "";
    }
  }

  async function downloadKit() {
    busy = "kit";
    try {
      const blob = await downloadGpuWorkerKit({
        worker_id: manualWorkerId.trim(),
        shared_windows_path: sharedEnabled ? sharedPath : ""
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "videoflow-windows-gpu-worker.zip";
      link.click();
      URL.revokeObjectURL(url);
      notice = "Windows kit downloaded.";
      error = "";
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    } finally {
      busy = "";
    }
  }

  async function unload() {
    busy = "unload";
    try {
      const payload = await unloadGpuModels();
      const unloaded = Array.isArray(payload.result.unloaded)
        ? payload.result.unloaded.length
        : 0;
      notice = `Freed ${unloaded} model(s).`;
      error = "";
      await refresh();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    } finally {
      busy = "";
    }
  }

  async function validateShared() {
    busy = "shared";
    try {
      await validateGpuShared("videoflow-probe.txt");
      notice = "Shared mount is writable.";
      error = "";
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    } finally {
      busy = "";
    }
  }

  async function setCapability(key: string, value: boolean) {
    capabilities = { ...capabilities, [key]: value };
    await patch({ capabilities: { [key]: value } }, "capability");
  }

  async function autoConnect() {
    if (!discoveryEnabled || (status?.worker_url && status?.available) || autoConnecting) return;
    autoConnecting = true;
    try {
      if (status?.worker_url && !status.available) {
        await connect(status.worker_url);
        if (status?.available) return;
      }
      const payload = await discoverGpuWorkers();
      discovered = payload.workers;
      discoveryInfo = payload.diagnostics ?? null;
      const peer =
        payload.workers.find((item) => item.auth_mode === "lan_open") ??
        payload.workers[0];
      if (!peer) return;
      await connect(peer.url, peer.worker_id);
      if (!status?.available) {
        notice = "Worker found. If it asks for a token, use Advanced once.";
      }
    } catch {
      // Discovery is best-effort; manual pairing remains available.
    } finally {
      autoConnecting = false;
    }
  }

  let autoTimer: ReturnType<typeof setInterval> | undefined;
  let activityTimer: ReturnType<typeof setInterval> | undefined;
  let statusTimer: ReturnType<typeof setInterval> | undefined;

  onMount(() => {
    void refresh().then(() => autoConnect().then(() => refreshActivity()));
    activityTimer = setInterval(() => void refreshActivity(), 3000);
    statusTimer = setInterval(() => void refresh().then(() => refreshActivity()), 5000);
    autoTimer = setInterval(() => {
      if (discoveryEnabled && !status?.available) void autoConnect();
    }, 10000);
  });

  onDestroy(() => {
    if (autoTimer) clearInterval(autoTimer);
    if (activityTimer) clearInterval(activityTimer);
    if (statusTimer) clearInterval(statusTimer);
  });
</script>

<section class="space-y-4" data-testid="gpu-panel">
  <div class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p class="text-[length:var(--vf-text-2xs)] uppercase tracking-wide text-neutral-500">Setup · GPU</p>
        <h2 class="mt-1 text-[length:var(--vf-text-xl)] font-semibold text-white">GPU acceleration</h2>
        <p class="mt-1 max-w-3xl text-[length:var(--vf-text-xs)] text-neutral-400">
          Keep editing on this machine and send only the heavy capabilities to a Windows NVIDIA worker. Local execution is always the fallback.
        </p>
      </div>
      <div class="flex items-center gap-2">
        <span
          class={`h-2 w-2 rounded-full ${status?.available ? "bg-emerald-400" : "bg-neutral-600"}`}
          aria-hidden="true"
        ></span>
        <span class="text-[length:var(--vf-text-xs)] text-neutral-300" data-testid="gpu-status-line">
          {status?.mode === "local_gpu"
            ? `GPU local: ${status.gpu_name || "NVIDIA"}${status.nvenc ? " · NVENC" : ""}`
            : status?.available
              ? `${status.gpu_name || "GPU"} · ${formatGb(status.vram_free_mb)} / ${formatGb(status.vram_total_mb)} GB · ${status.encoder || "encoder?"}`
              : loading
                ? "Checking worker…"
                : status?.mode === "local_only"
                  ? "Local mode"
                  : "No worker connected"}
        </span>
      </div>
      {#if status?.asr_ready === false}
        <p class="mt-1 max-w-3xl text-[length:var(--vf-text-2xs)] text-amber-300" data-testid="gpu-asr-error">
          ASR indisponível: {status.asr_error || "dependência do worker ausente"}
        </p>
      {/if}
    </div>

    {#if error}
      <p class="mt-3 rounded-lg border border-rose-400/20 bg-rose-950/30 px-3 py-2 text-[length:var(--vf-text-xs)] text-rose-200" role="alert" data-testid="gpu-error">{error}</p>
    {/if}
    {#if notice}
      <p class="mt-3 rounded-lg border border-emerald-400/20 bg-emerald-950/30 px-3 py-2 text-[length:var(--vf-text-xs)] text-emerald-200" role="status" data-testid="gpu-notice">{notice}</p>
    {/if}
  </div>

  <div class="grid gap-4 xl:grid-cols-2">
    <article class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4" data-testid="gpu-pairing-card">
      <h3 class="text-[length:var(--vf-text-sm)] font-semibold text-neutral-100">Pairing</h3>
      <p class="mt-1 text-[length:var(--vf-text-xs)] text-neutral-500">
        {autoConnecting
          ? "Looking for a Windows worker on the LAN…"
          : "Auto-discovery is on. Open the Windows worker and it connects automatically."}
      </p>
      <div class="mt-3 flex flex-wrap gap-2">
        <button type="button" data-testid="gpu-discover" disabled={busy !== ""} onclick={() => void discover()} class="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-1.5 text-[length:var(--vf-text-xs)] text-neutral-200 disabled:opacity-40">
          {busy === "discover" ? "Scanning…" : "Scan LAN"}
        </button>
        <button type="button" data-testid="gpu-download-kit" disabled={busy !== ""} onclick={() => void downloadKit()} class="rounded-lg border border-sky-400/25 bg-sky-500/10 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-sky-100 disabled:opacity-40">
          {busy === "kit" ? "Building kit…" : "Download Windows kit (.zip)"}
        </button>
      </div>
      {#if discoveryInfo}
        <p class="mt-2 text-[11px] text-neutral-500">
          Discovery: UDP {discoveryInfo.udp} · mDNS {discoveryInfo.mdns ?? 0} · TCP scan {discoveryInfo.tcp_scan} · {(discoveryInfo.subnets ?? []).join(", ") || "/24"} · {discoveryInfo.elapsed_ms} ms
        </p>
      {/if}
      {#if discovered.length}
        <ul class="mt-3 space-y-1.5" data-testid="gpu-discovered-list">
          {#each discovered as peer}
            <li class="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-white/10 px-2.5 py-2">
              <span class="text-[length:var(--vf-text-xs)] text-neutral-200">
                {peer.hostname || peer.worker_id} · {peer.gpu_name || "unknown GPU"} · {formatGb(peer.vram_free_mb)} GB free
              </span>
              <button type="button" class="rounded border border-sky-400/30 px-2 py-1 text-[11px] text-sky-200" onclick={() => void connect(peer.url, peer.worker_id)}>Connect</button>
            </li>
          {/each}
        </ul>
      {/if}
      <details class="mt-4 rounded-lg border border-white/5 p-3">
        <summary class="cursor-pointer text-[11px] uppercase tracking-wide text-neutral-500">Advanced pairing</summary>
        <div class="mt-3 grid gap-2">
        <label class="text-[11px] text-neutral-500" for="gpu-worker-url">Worker URL</label>
        <input id="gpu-worker-url" data-testid="gpu-manual-url" bind:value={manualUrl} placeholder="http://192.168.1.45:8766" class="rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 font-mono text-[length:var(--vf-text-xs)] text-neutral-100" />
        <label class="text-[11px] text-neutral-500" for="gpu-worker-token">Pairing token</label>
        <input id="gpu-worker-token" data-testid="gpu-manual-token" type="password" bind:value={manualToken} placeholder="token from worker.env" class="rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 font-mono text-[length:var(--vf-text-xs)] text-neutral-100" />
        <label class="text-[11px] text-neutral-500" for="gpu-worker-id">Worker id (optional)</label>
        <input id="gpu-worker-id" data-testid="gpu-manual-worker-id" bind:value={manualWorkerId} placeholder="BERNA-WIN-SERVE" class="rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 font-mono text-[length:var(--vf-text-xs)] text-neutral-100" />
        <div class="flex flex-wrap gap-2 pt-1">
          <button type="button" data-testid="gpu-connect" disabled={busy !== ""} onclick={() => void connect()} class="rounded-lg border border-emerald-400/25 bg-emerald-500/10 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-emerald-100 disabled:opacity-40">Connect</button>
          <button type="button" data-testid="gpu-disconnect" disabled={busy !== "" || !workerUrl} onclick={() => void disconnect()} class="rounded-lg border border-white/10 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-neutral-300 disabled:opacity-40">Disconnect</button>
        </div>
        </div>
      </details>
    </article>

    <article class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4" data-testid="gpu-capabilities-card">
      <h3 class="text-[length:var(--vf-text-sm)] font-semibold text-neutral-100">What runs on the GPU</h3>
      <p class="mt-1 text-[length:var(--vf-text-xs)] text-neutral-500">Light editing stays local. Enable only the capabilities you want to offload.</p>
      <div class="mt-3 grid gap-1.5 sm:grid-cols-2">
        {#each CAPABILITIES as [key, label]}
          <label class="flex items-center justify-between gap-2 rounded-lg border border-white/5 px-2.5 py-2 text-[length:var(--vf-text-xs)] text-neutral-300">
            <span>{label}</span>
            <input
              type="checkbox"
              data-testid={`gpu-cap-${key}`}
              checked={capabilities[key] ?? false}
              disabled={busy !== ""}
              onchange={(event) => void setCapability(key, event.currentTarget.checked)}
            />
          </label>
        {/each}
      </div>
      <div class="mt-4 rounded-lg border border-white/5 p-3">
        <p class="text-[11px] uppercase tracking-wide text-neutral-500">Benchmark</p>
        <div class="mt-2 flex flex-wrap items-center gap-2">
          <button type="button" data-testid="gpu-benchmark" disabled={busy !== "" || !workerUrl} onclick={() => void runBenchmark()} class="rounded-lg border border-sky-400/25 bg-sky-500/10 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-sky-100 disabled:opacity-40">
            {busy === "benchmark" ? "Testing…" : "Test connectivity"}
          </button>
          {#if benchmark}
            <span data-testid="gpu-benchmark-result" class="text-[length:var(--vf-text-xs)] text-neutral-400">
              {benchmark.latency_ms} ms · {benchmark.kind}
            </span>
          {/if}
        </div>
      </div>
    </article>

    <article class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4" data-testid="gpu-connection-card">
      <h3 class="text-[length:var(--vf-text-sm)] font-semibold text-neutral-100">Connection details</h3>
      <p class="mt-1 text-[length:var(--vf-text-xs)] text-neutral-500">Everything needed to connect or diagnose this worker.</p>
      <div class="mt-3 space-y-1.5 text-[length:var(--vf-text-xs)]">
        <div class="flex items-center justify-between gap-3 border-b border-white/5 pb-1.5"><span class="text-neutral-500">Worker URL</span><span class="truncate font-mono text-neutral-200">{status?.worker_url || "not connected"}</span></div>
        <div class="flex items-center justify-between gap-3 border-b border-white/5 pb-1.5"><span class="text-neutral-500">Worker id</span><span class="truncate text-neutral-200">{status?.worker_id || "—"}</span></div>
        <div class="flex items-center justify-between gap-3 border-b border-white/5 pb-1.5"><span class="text-neutral-500">Version</span><span class="text-neutral-200">{status?.version || "—"}</span></div>
        <div class="flex items-center justify-between gap-3 border-b border-white/5 pb-1.5"><span class="text-neutral-500">Authentication</span><span class="text-neutral-200">{status?.token_only ? "token-only" : status?.auth_mode === "lan_open" ? "LAN open (private)" : status?.auth_mode || "token"}</span></div>
        <div class="flex items-center justify-between gap-3 border-b border-white/5 pb-1.5"><span class="text-neutral-500">Allowlist</span><span class="truncate text-neutral-200">{status?.allowed_clients?.length ? status.allowed_clients.join(", ") : "private LAN"}</span></div>
        <div class="flex items-center justify-between gap-3 border-b border-white/5 pb-1.5"><span class="text-neutral-500">Disk free</span><span class="text-neutral-200">{status?.disk_free_mb ?? "—"} MB</span></div>
        <div class="flex items-center justify-between gap-3 border-b border-white/5 pb-1.5"><span class="text-neutral-500">Encoder</span><span class="text-neutral-200">{status?.encoder || "—"} · NVENC {status?.nvenc ? "yes" : "no"}</span></div>
        <div class="flex items-center justify-between gap-3"><span class="text-neutral-500">Discovery</span><span class="text-neutral-200">{discoveryEnabled ? "UDP 8767 + subnet scan" : "disabled"}</span></div>
      </div>
      {#if status?.worker_url}
        <div class="mt-3 flex flex-wrap gap-2">
          <button type="button" class="rounded-lg border border-white/10 px-2.5 py-1 text-[11px] text-neutral-300" onclick={() => void navigator.clipboard.writeText(status?.worker_url || "")}>Copy worker URL</button>
          <button type="button" disabled={busy !== ""} onclick={() => void runSelftest()} class="rounded-lg border border-emerald-400/25 bg-emerald-500/10 px-2.5 py-1 text-[11px] text-emerald-100 disabled:opacity-40">{busy === "selftest" ? "Testing…" : "Test execution"}</button>
        </div>
        {#if selftest}
          <p class="mt-2 text-[11px] text-emerald-200">Selftest job {selftest.job_id.slice(0, 8)} · {selftest.state} · {selftest.elapsed_sec}s</p>
        {/if}
      {/if}
    </article>

    <article class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4" data-testid="gpu-activity-card">
      <div class="flex items-center justify-between gap-2">
        <h3 class="text-[length:var(--vf-text-sm)] font-semibold text-neutral-100">Worker activity</h3>
        <span class="text-[11px] text-neutral-500">{status?.available ? "live · 3 s" : "offline"}</span>
      </div>
      <p class="mt-1 text-[length:var(--vf-text-xs)] text-neutral-500">What the worker is processing right now and the latest finished requests.</p>
      {#if activity}
        <div class="mt-3 grid gap-2 sm:grid-cols-2">
          <div class="rounded-lg border border-white/5 p-2">
            <p class="text-[10px] uppercase tracking-wide text-neutral-500">Current</p>
            {#if activity.jobs?.find((job) => job.status === "running" || job.status === "queued")}
              {@const current = activity.jobs.find((job) => job.status === "running" || job.status === "queued")}
              <p class="mt-1 text-[length:var(--vf-text-xs)] text-neutral-200">{current?.capability}</p>
              <p class="text-[11px] text-neutral-500">{current?.stage || current?.status} · {Math.round(current?.progress ?? 0)}% · job {current?.job_id.slice(0, 8)}</p>
              <div class="mt-1.5 h-1 overflow-hidden rounded-full bg-white/10">
                <div class="h-full bg-sky-400 transition-all" style={`width:${Math.max(0, Math.min(100, Number(current?.progress ?? 0)))}%`}></div>
              </div>
            {:else}
              <p class="mt-1 text-[length:var(--vf-text-xs)] text-neutral-500">Idle</p>
            {/if}
          </div>
          <div class="rounded-lg border border-white/5 p-2">
            <p class="text-[10px] uppercase tracking-wide text-neutral-500">Queue</p>
            <p class="mt-1 text-[length:var(--vf-text-xs)] text-neutral-200">{status?.queue_depth ?? 0} job(s)</p>
            {#if activity.runner?.queue?.length}
              {@const next = activity.runner.queue[0]}
              <p class="text-[11px] text-neutral-500">Next: {next.capability} · ~{Math.round(next.estimated_wait_sec)} s</p>
            {/if}
          </div>
        </div>
        <ul class="mt-3 max-h-44 space-y-1.5 overflow-auto">
          {#each (activity.jobs ?? []).slice(0, 6) as job}
            <li class="flex items-center justify-between gap-2 rounded-lg border border-white/5 px-2 py-1.5 text-[11px]">
              <span class="truncate text-neutral-300">{job.capability}</span>
              <span class="shrink-0 font-mono text-neutral-500">{job.stage || job.status} · {Math.round(job.progress ?? 0)}%</span>
            </li>
          {/each}
        </ul>
        {#if activity.logs}
          <pre class="mt-3 max-h-32 overflow-auto rounded-lg bg-black/40 p-2 font-mono text-[10px] leading-4 text-neutral-400">{activity.logs}</pre>
        {/if}
      {:else}
        <p class="mt-3 text-[length:var(--vf-text-xs)] text-neutral-500">Connect the worker to see live activity.</p>
      {/if}
    </article>

    <article class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4" data-testid="gpu-shared-card">
      <h3 class="text-[length:var(--vf-text-sm)] font-semibold text-neutral-100">Shared folder</h3>
      <p class="mt-1 text-[length:var(--vf-text-xs)] text-neutral-500">Zero-copy for longform masters. Short clips can use HTTP streaming.</p>
      <label class="mt-3 flex items-center gap-2 text-[length:var(--vf-text-xs)] text-neutral-300">
        <input type="checkbox" data-testid="gpu-shared-toggle" checked={sharedEnabled} disabled={busy !== ""} onchange={(event) => void patch({ shared_mount_enabled: event.currentTarget.checked }, "shared")} />
        Use a shared mount
      </label>
      <input data-testid="gpu-shared-path" bind:value={sharedPath} onchange={() => void patch({ shared_windows_path: sharedPath }, "shared")} placeholder="Z:\videoflow" class="mt-2 w-full rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 font-mono text-[length:var(--vf-text-xs)] text-neutral-100" />
      <button type="button" data-testid="gpu-shared-validate" disabled={busy !== "" || !workerUrl} onclick={() => void validateShared()} class="mt-2 rounded-lg border border-white/10 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-neutral-300 disabled:opacity-40">Validate read/write</button>
    </article>

    <article class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4" data-testid="gpu-resources-card">
      <h3 class="text-[length:var(--vf-text-sm)] font-semibold text-neutral-100">Resources</h3>
      <p class="mt-1 text-[length:var(--vf-text-xs)] text-neutral-500">VRAM cap, fallback, and loaded models.</p>
      <label class="mt-3 block text-[11px] text-neutral-500" for="gpu-vram">Maximum VRAM: {vramLabel(maxVram)}</label>
      <input id="gpu-vram" data-testid="gpu-vram-slider" type="range" min="4096" max="11264" step="512" bind:value={maxVram} onchange={() => void patch({ max_vram_mb: maxVram }, "vram")} class="mt-1 w-full" />
      <label class="mt-3 block text-[11px] text-neutral-500" for="gpu-max-utilization">Skip remote when GPU is busier than: {maxUtilization}%</label>
      <input id="gpu-max-utilization" data-testid="gpu-utilization-cap" type="range" min="0" max="100" step="5" bind:value={maxUtilization} onchange={() => void patch({ max_gpu_utilization_pct: maxUtilization }, "utilization")} class="mt-1 w-full" />
      <p class="mt-1 text-[length:var(--vf-text-xs)] text-neutral-500">0 disables the external load guard.</p>
      <label class="mt-3 flex items-center gap-2 text-[length:var(--vf-text-xs)] text-neutral-300">
        <input type="checkbox" data-testid="gpu-fallback" checked={fallback} disabled={busy !== ""} onchange={(event) => void patch({ fallback_local: event.currentTarget.checked }, "fallback")} />
        Fall back to local when the worker fails
      </label>
      <label class="mt-2 flex items-center gap-2 text-[length:var(--vf-text-xs)] text-neutral-300">
        <input type="checkbox" data-testid="gpu-discovery" checked={discoveryEnabled} disabled={busy !== ""} onchange={(event) => void patch({ discovery_enabled: event.currentTarget.checked }, "discovery")} />
        Listen for LAN worker beacons
      </label>
      <div class="mt-3 flex flex-wrap items-center gap-2">
        <button type="button" data-testid="gpu-unload" disabled={busy !== "" || !workerUrl} onclick={() => void unload()} class="rounded-lg border border-amber-400/25 bg-amber-500/10 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-amber-100 disabled:opacity-40">Free GPU memory</button>
        {#if status?.available}
          <span class="text-[length:var(--vf-text-xs)] text-neutral-500">{status.models.length} model(s) loaded · queue {status.queue_depth}</span>
        {/if}
      </div>
    </article>
  </div>
</section>
