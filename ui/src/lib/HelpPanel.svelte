<script lang="ts">
  const sections = [
    {
      id: "start",
      title: "Quick start",
      body: `1. Setup → Workspace: choose a folder and click “Prepare workspace and install MCP”.
2. Open OpenCode in that folder.
3. Ask the agent to create a project with vf_project(action="init").
4. Run ingest, transcription, decupage, scenes, Shorts, export, and QA.`
    },
    {
      id: "worker",
      title: "Windows GPU worker",
      body: `Download the kit in Setup → GPU. Run “Instalar / reparar tudo”, then “Iniciar worker”.
The 3.8+ kit enables LAN discovery and LAN-open mode for private networks. The Linux app
discovers the worker automatically and reconnects every 5 seconds. Public clients still
need the token. Use Advanced pairing only when LAN-open is disabled.`
    },
    {
      id: "progress",
      title: "Job progress, priority and queue",
      body: `Every job exposes stage and progress. The worker dashboard and Setup → GPU show the current
stage, percentage, queue position, and estimated wait. POST /jobs/{capability} accepts
priority from -100 to 100; higher priority runs first and equal priority stays FIFO.
Submissions return HTTP 507 when disk free is below VF_GPU_MIN_FREE_DISK_MB.`
    },
    {
      id: "warmup",
      title: "Model warmup",
      body: `The worker caches faster-whisper and rembg sessions. Press “Aquecer modelos” in the worker
dashboard, call POST /api/warmup, or set VF_GPU_WARMUP=1. The Windows installer enables
warmup so the first transcription does not pay the cold-start load.`
    },
    {
      id: "transfers",
      title: "Transfers and shared mount",
      body: `With VF_GPU_SHARED_LOCAL_ROOT on Linux and VF_GPU_SHARED_ROOT on Windows, transport=auto
sends relative shared paths instead of uploading files. Uploads are SHA-256 deduplicated and
use a bounded pool (VF_GPU_UPLOAD_WORKERS). Each routed result reports transfer bytes,
seconds, dedup count, and MB/s.`
    },
    {
      id: "security",
      title: "Worker security and audit",
      body: `LAN-open accepts loopback and private RFC1918 clients. Set VF_GPU_ALLOWED_CLIENTS to a
comma-separated IP/CIDR allowlist, or VF_GPU_TOKEN_ONLY=1 to require the token even on the LAN
while keeping the dashboard available on loopback. Local-only endpoints: GET /api/security,
GET /api/audit, POST /api/token/rotate, POST /api/restart. Rotating writes worker.token in the
worker work directory and takes effect immediately.`
    },
    {
      id: "discovery",
      title: "Worker discovery",
      body: `Discovery tries UDP 8767 beacons, optional mDNS (_videoflow._tcp.local.), and a bounded
active scan of the real local subnets. Set VF_GPU_SCAN_CIDRS to override the subnets and
VF_GPU_SCAN_MAX_HOSTS to bound the scan. Results are cached for 15 seconds and deduplicated
by worker_id.`
    },
    {
      id: "workspace",
      title: "Workspace and MCP install",
      body: `The workspace holds projects, styles, workflows, references, and AGENTS.md.
The installer merges the VideoFlow MCP server into the OpenCode config, backs up the
existing file, registers the allowed root, and can create a 10-second sample project.`
    },
    {
      id: "styles",
      title: "Styles",
      body: `Styles are Markdown files with frontmatter. Create, edit, duplicate, restore, and delete
them in Setup → Styles. The same catalog is available through vf_style actions: list, get,
create, save, duplicate, restore, delete, sync, and learn_rule.`
    },
    {
      id: "formats",
      title: "Formats",
      body: `Formats define aspect ratio, resolution, FPS, caption preset, safe zones, platforms, and
export targets. Built-in formats are 9:16, 4:5, 1:1, and 16:9. Duplicate a built-in to
customize it. vf_format exposes list, get, save, delete, and duplicate.`
    },
    {
      id: "scenes",
      title: "Scene intelligence",
      body: `Run vf_exec(step_id="scene.analyze") after ingest. Outputs are scenes_manifest.json,
timeline_supercontext.json, and one 544px keyframe per scene. vf_scenes(action="manifest")
returns paged scenes and paths; vf_scenes(action="keyframe") returns metadata only.`
    },
    {
      id: "shorts",
      title: "Dynamic Shorts",
      body: `Recommended order: short.plan → short.captions → short.validate → short.render →
short.export → short.qa. Layouts: FULL_FACE, SPLIT_BROLL, SPLIT_SCREEN_SAFE, SPLIT_SCREEN_FILL.
Captions use 3–4 words, ≤18 chars per line, ≤2 lines. Safe zones: 380px bottom, 140px right.`
    },
    {
      id: "export",
      title: "Export and delivery",
      body: `vf_export builds the NLE bundle. Short FCPXML contains V1 base, V2 face panels, A1 voice,
A2 SFX, editable captions, and layout markers. Run scripts/fcpxml_smoke.py before Resolve.
Optionally run delivery.collect to group outputs under VideoFlow_Output.`
    },
    {
      id: "api",
      title: "Worker API reference",
      body: `GET /health, GET /api/overview, GET /api/jobs, GET /jobs/{id}, GET /api/history,
GET /api/system, GET /api/logs, POST /api/warmup, POST /api/restart (local), GET /api/security
(local), GET /api/audit (local), POST /api/token/rotate (local), POST /jobs/{capability},
GET /jobs/{id}/artifact/{name}. Health is public; other routes use LAN-open or X-VF-Token.`
    },
    {
      id: "retention",
      title: "Retention and disk",
      body: `Finished jobs are cleaned at startup and hourly. VF_GPU_JOB_RETENTION_HOURS defaults to
168. Unreferenced uploaded artifacts are removed by the same maintenance loop, metrics older
than VF_GPU_METRICS_RETENTION_HOURS (720) are pruned, and worker.log rotates when it exceeds
VF_GPU_LOG_MAX_MB (20).`
    },
    {
      id: "mcp",
      title: "MCP tools",
      body: `vf_project, vf_ingest, vf_exec, vf_catalog_search, vf_job, vf_scenes, vf_format, vf_style,
vf_timeline, vf_export, vf_qa_final, vf_gpu_preflight, and the domain servers fetch/audio/vision.
Resources: vf://docs/steps, vf://docs/contracts/*, vf://projects/<id>/scenes.`
    },
    {
      id: "troubleshoot",
      title: "Troubleshooting",
      body: `Worker not found: run Install/repair, confirm discovery is enabled, check firewall rules for
TCP 8766/UDP 8767 on all profiles, inspect /api/system, and try VF_GPU_SCAN_CIDRS with your
subnet. NVENC unavailable: the worker reports libx264 and remote render still works; the
dashboard shows the exact FFmpeg error. Token required: use LAN-open on a private network,
add the client to VF_GPU_ALLOWED_CLIENTS, or paste the token under Advanced pairing. Job stuck:
check /api/overview runner.queue, then POST /api/restart (local) to rebuild threads and
re-enqueue queued jobs.`
    }
  ];
  let query = $state("");
  const visible = $derived(
    sections.filter((item) =>
      `${item.title} ${item.body}`.toLowerCase().includes(query.trim().toLowerCase())
    )
  );
</script>

<section class="space-y-4" data-testid="help-panel">
  <div class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4">
    <p class="vf-label text-sky-300/80">Setup · Help</p>
    <h2 class="mt-1 text-[length:var(--vf-text-xl)] font-semibold text-white">Documentation and MCP recipes</h2>
    <p class="mt-1 max-w-3xl text-[length:var(--vf-text-xs)] text-neutral-400">Search install, worker, styles, formats, scenes, Shorts, export, and troubleshooting.</p>
    <input bind:value={query} placeholder="Search help…" aria-label="Search help" class="mt-3 w-full max-w-md rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-[length:var(--vf-text-xs)] text-neutral-100" />
  </div>
  <div class="grid gap-3 xl:grid-cols-2">
    {#each visible as item}
      <details open={query.length > 0 || item.id === "start"} class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4">
        <summary class="cursor-pointer text-[length:var(--vf-text-sm)] font-semibold text-neutral-100">{item.title}</summary>
        <p class="mt-3 whitespace-pre-line text-[length:var(--vf-text-xs)] leading-6 text-neutral-300">{item.body}</p>
      </details>
    {/each}
  </div>
  <div class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4">
    <h3 class="text-[length:var(--vf-text-sm)] font-semibold text-neutral-100">Copyable prompt</h3>
    <pre class="mt-3 overflow-x-auto rounded-xl bg-black/40 p-3 font-mono text-[length:var(--vf-text-xs)] leading-5 text-neutral-300">Use o MCP VideoFlow no projeto &lt;project_id&gt;.
1. Analise as cenas e me mostre o manifesto resumido.
2. Planeje um Short de 45s com FULL_FACE, SPLIT_SCREEN_SAFE e SPLIT_BROLL.
3. Gere legendas, valide, renderize e exporte FCPXML.
4. Rode a QA final e me diga o status e os warnings.</pre>
  </div>
</section>
