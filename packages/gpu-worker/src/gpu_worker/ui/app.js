const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt = (seconds) => {
  const value = Number(seconds || 0);
  if (value < 60) return `${Math.round(value)} s`;
  if (value < 3600) return `${Math.floor(value/60)} min`;
  return `${(value/3600).toFixed(1)} h`;
};
const when = (ts) => ts ? new Date(Number(ts) * 1000).toLocaleString() : "—";
let last = null;
let system = null;
let rawLog = "";
async function load() {
  const started = performance.now();
  try {
    const [overviewResponse, systemResponse] = await Promise.all([
      fetch("/api/overview", {cache:"no-store"}),
      fetch("/api/system", {cache:"no-store"})
    ]);
    if (!overviewResponse.ok) throw new Error(`HTTP ${overviewResponse.status}`);
    const data = await overviewResponse.json();
    last = data;
    if (systemResponse.ok) {
      system = await systemResponse.json();
      renderSystem(system);
    }
    render(data);
    $("latency").textContent = `${Math.round(performance.now()-started)} ms`;
  } catch (error) {
    $("dot").className = "dot bad";
    $("state").textContent = "offline";
    $("notice").hidden = false;
    $("notice").textContent = `Não foi possível ler o worker: ${error}`;
  }
}
function render(data) {
  const h = data.health || {};
  $("dot").className = `dot ${h.available ? "ok" : "bad"}`;
  $("state").textContent = h.available ? "online" : "offline";
  $("subtitle").textContent = `${h.hostname || "worker"} · ${h.platform || ""} · atualiza a cada 2 s`;
  const urls = h.lan_urls || [];
  const url = urls.length ? `http://${urls[0]}:${h.port}` : `http://${h.ip_local || "127.0.0.1"}:${h.port}`;
  $("lan-url").textContent = url;
  $("port").textContent = h.port || "—";
  $("discovery").textContent = "UDP 8767";
  $("auth").textContent = h.auth_mode === "lan_open" ? "LAN aberta (privada)" : "Token";
  $("firewall").textContent = "TCP 8766 / UDP 8767";
  const lastRequest = h.last_request || {};
  $("last-request").textContent = lastRequest.path ? `${lastRequest.method} ${lastRequest.path} · ${lastRequest.client || ""}` : "aguardando";
  $("gpu").textContent = h.gpu_name || "—";
  $("vram").textContent = `${h.vram_free_mb ?? 0} / ${h.vram_total_mb ?? 0} MB`;
  $("driver").textContent = h.driver_version || "—";
  $("encoder").textContent = h.encoder || "—";
  $("nvenc").textContent = h.nvenc ? "disponível" : "indisponível";
  $("version").textContent = h.version || "—";
  $("worker-id").textContent = h.worker_id || "—";
  $("uptime").textContent = fmt(h.uptime_sec);
  $("queue").textContent = String(h.queue_depth ?? 0);
  $("cpu-workers").textContent = String((data.runner || {}).cpu_workers ?? "—");
  $("disk").textContent = h.disk_free_mb != null ? `${h.disk_free_mb} MB` : "—";
  const warm = data.warmup || h.warmup || {};
  $("warmup").textContent = warm.running ? "aquecendo…" : (warm.loaded || []).length ? (warm.loaded || []).join(", ") : (warm.errors || []).length ? "falhou" : "não executado";
  $("notice").hidden = !(h.nvenc === false && h.nvenc_error);
  if (h.nvenc === false && h.nvenc_error) $("notice").textContent = `NVENC indisponível: ${h.nvenc_error}`;
  const current = h.current_job;
  const currentProgress = Number(current?.progress ?? 0);
  $("current").innerHTML = current
    ? `<div class="row"><span class="label">Job</span><code>${esc(current.job_id)}</code></div><div class="row"><span class="label">Capacidade</span><strong>${esc(current.capability)}</strong></div><div class="row"><span class="label">Etapa</span><span class="tag run">${esc(current.stage || current.status)}</span></div><div class="row"><span class="label">Progresso</span><strong>${currentProgress}%</strong></div><div class="progress"><span style="width:${currentProgress}%"></span></div><div class="row"><span class="label">Início</span><strong>${when(current.started_at || current.created_at)}</strong></div>`
    : "Nada em execução.";
  const queue = (data.runner || {}).queue || [];
  $("queue-list").innerHTML = queue.length ? queue.map((item) => `<span class="tag run">${esc(item.capability)} · ${esc(item.job_id).slice(0,8)} · espera ~${fmt(item.estimated_wait_sec)}</span>`).join(" ") : "Fila vazia.";
  const jobs = data.jobs || [];
  $("jobs").innerHTML = jobs.length ? jobs.map((job) => {
    const end = job.finished_at || (job.started_at ? Date.now()/1000 : null);
    const duration = job.started_at && end ? end - job.started_at : null;
    const cls = job.status === "succeeded" ? "ok" : job.status === "failed" ? "bad" : "run";
    const progress = Math.max(0, Math.min(100, Number(job.progress ?? (job.status === "succeeded" ? 100 : 0))));
    return `<tr><td><code>${esc(job.job_id).slice(0,10)}…</code></td><td>${esc(job.capability)}</td><td><span class="tag ${cls}">${esc(job.status)}</span><br><small>${esc(job.stage || "")}</small></td><td><div class="progress" style="min-width:80px"><span style="width:${progress}%"></span></div><small>${progress}%</small></td><td>${when(job.created_at)}</td><td>${duration ? fmt(duration) : "—"}</td><td>${esc(job.error || "")}</td></tr>`;
  }).join("") : `<tr><td colspan="7" class="muted">Sem jobs.</td></tr>`;
  rawLog = data.logs || "";
  applyLogFilter();
}

function applyLogFilter() {
  const needle = ($("log-filter").value || "").trim().toLowerCase();
  const lines = rawLog ? rawLog.split("\n") : [];
  const visible = needle ? lines.filter((line) => line.toLowerCase().includes(needle)) : lines;
  $("log").textContent = visible.length ? visible.join("\n") : (needle ? "Nenhuma linha corresponde ao filtro." : "Sem log disponível.");
}

function drawChart(samples) {
  const points = (samples || []).slice(-120);
  if (!points.length) return;
  const width = 600;
  const height = 110;
  const line = (key, maxValue) => points.map((sample, index) => {
    const x = points.length === 1 ? 0 : (index / (points.length - 1)) * width;
    const raw = Number(sample[key] || 0);
    const y = height - Math.max(0, Math.min(1, maxValue > 0 ? raw / maxValue : 0)) * height;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  $("chart-gpu").setAttribute("points", line("gpu_utilization", 100));
  $("chart-queue").setAttribute("points", line("queue_depth", Math.max(1, ...points.map((item) => Number(item.queue_depth || 0)))));
  const vramUsed = points.map((item) => Math.max(0, Number(item.vram_total_mb || 0) - Number(item.vram_free_mb || 0)));
  const vramMax = Math.max(1, ...points.map((item, index) => Number(item.vram_total_mb || 0) || vramUsed[index]));
  const vramLine = points.map((sample, index) => {
    const x = points.length === 1 ? 0 : (index / (points.length - 1)) * width;
    const y = height - Math.max(0, Math.min(1, vramUsed[index] / vramMax)) * height;
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(" ");
  $("chart-vram").setAttribute("points", vramLine);
}

function renderSystem(data) {
  $("sec-mode").textContent = data.token_only ? "token-only" : "LAN aberta + token";
  $("sec-allow").textContent = (data.allowed_clients || []).length ? (data.allowed_clients || []).join(", ") : "qualquer IP privado";
  $("sec-clients").textContent = `${(data.clients || []).length} cliente(s) · ${data.request_count ?? 0} pedidos`;
  const firewall = data.firewall || {};
  $("sec-firewall").textContent = firewall.supported ? `${(firewall.rules || []).length} regra(s)` : "não verificável neste sistema";
  const audit = (data.audit || []).slice(-1)[0];
  $("sec-audit").textContent = audit ? `${audit.method} ${audit.path} · ${audit.client} · ${audit.outcome}` : "—";
  drawChart(data.history || []);
}
$("refresh").onclick = () => void load();
if (["127.0.0.1", "localhost", "::1"].includes(location.hostname)) {
  $("rotate").hidden = false;
}
$("rotate").onclick = async () => {
  if (!confirm("Gerar um novo token? O token antigo deixa de funcionar.")) return;
  try {
    const response = await fetch("/api/token/rotate", {method:"POST"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Falha ao rotacionar");
    $("notice").hidden = false;
    $("notice").textContent = `Novo token: ${data.token} (salvo em ${data.token_file})`;
    try { await navigator.clipboard.writeText(data.token); } catch {}
  } catch (error) {
    $("notice").hidden = false; $("notice").textContent = `Rotação falhou: ${error}`;
  }
};
$("log-filter").oninput = () => applyLogFilter();
$("restart").onclick = async () => {
  if (!confirm("Reiniciar as threads do worker e reenfileirar jobs?")) return;
  try {
    $("notice").hidden = false;
    $("notice").textContent = "Reiniciando worker…";
    const response = await fetch("/api/restart", {method:"POST"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Falha ao reiniciar");
    $("notice").textContent = "Worker reiniciado.";
    void load();
  } catch (error) {
    $("notice").hidden = false; $("notice").textContent = `Reinício falhou: ${error}`;
  }
};
$("warm").onclick = async () => {
  try {
    $("notice").hidden = false;
    $("notice").textContent = "Aquecendo modelos…";
    const response = await fetch("/api/warmup", {method:"POST"});
    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || "Falha no warmup");
    $("notice").textContent = `Warmup: ${(data.loaded || []).join(", ") || "nada carregado"}${(data.errors || []).length ? " · erros: " + data.errors.join("; ") : ""}`;
    void load();
  } catch (error) {
    $("notice").hidden = false; $("notice").textContent = `Warmup falhou: ${error}`;
  }
};
$("benchmark").onclick = async () => {
  try {
    const response = await fetch("/probe", {method:"POST"});
    const data = await response.json();
    $("notice").hidden = false;
    $("notice").textContent = `Benchmark: ok=${data.ok} · cuda=${data.cuda} · nvenc=${data.nvenc} · ${data.latency_ms} ms`;
  } catch (error) {
    $("notice").hidden = false; $("notice").textContent = `Benchmark falhou: ${error}`;
  }
};
$("copy").onclick = async () => {
  try { await navigator.clipboard.writeText($("lan-url").textContent); $("copy").textContent = "Copiado"; setTimeout(()=>$("copy").textContent="Copiar URL",1200); } catch {}
};
$("logs").onclick = async () => {
  try { const response = await fetch("/api/open-logs", {method:"POST"}); const data = await response.json(); if (!response.ok) throw new Error(data.detail || "Falha ao abrir logs"); }
  catch (error) { $("notice").hidden=false; $("notice").textContent = String(error); }
};
load(); setInterval(load, 2000);
