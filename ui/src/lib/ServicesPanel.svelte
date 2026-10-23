<script lang="ts">
  import {
    cleanupServices,
    errorMessage,
    getDoctor,
    getServiceLog,
    listServices,
    restartService,
    stopService,
    stopServicePid,
    type ServiceProcessInfo
  } from "$lib/api";

  let services = $state<ServiceProcessInfo[]>([]);
  let busy = $state<number | "all" | "restart" | "stop" | "">("");
  let error = $state("");
  let message = $state("");
  let stopped = $state(false);
  let logPath = $state("");
  let logText = $state("");
  let logOpen = $state(false);
  let logBusy = $state(false);
  let doctor = $state<Record<string, unknown> | null>(null);
  let doctorBusy = $state(false);

  const others = $derived(
    services.filter((service) => !service.current && !service.protected)
  );
  const current = $derived(services.find((service) => service.current) ?? null);

  async function refresh() {
    try {
      const response = await listServices();
      services = response.services;
      logPath = response.log_path;
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function stopOne(service: ServiceProcessInfo) {
    if (busy) return;
    if (!window.confirm(`Stop VideoFlow service PID ${service.pid}?`)) return;
    busy = service.pid;
    error = "";
    message = "";
    try {
      await stopServicePid(service.pid);
      message = `Service ${service.pid} stopped.`;
      await refresh();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = "";
    }
  }

  async function stopAllOthers() {
    if (busy || !others.length) return;
    if (!window.confirm(`Stop ${others.length} other VideoFlow service(s)?`)) return;
    busy = "all";
    error = "";
    message = "";
    try {
      const result = await cleanupServices();
      message = `${result.stopped.length} service(s) stopped.`;
      if (result.failed.length) {
        error = `Could not stop: ${result.failed.join(", ")}`;
      }
      await refresh();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = "";
    }
  }

  async function toggleLog() {
    if (logOpen) {
      logOpen = false;
      return;
    }
    logBusy = true;
    error = "";
    try {
      const response = await getServiceLog(200);
      logText = response.text;
      logPath = response.path;
      logOpen = true;
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      logBusy = false;
    }
  }

  async function runDoctor() {
    doctorBusy = true;
    error = "";
    try {
      doctor = (await getDoctor()).checks;
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      doctorBusy = false;
    }
  }

  async function restartCurrent() {
    if (busy) return;
    busy = "restart";
    error = "";
    message = "Restarting the service…";
    try {
      await restartService();
      await new Promise((resolve) => setTimeout(resolve, 1800));
      window.location.reload();
    } catch (reason) {
      error = errorMessage(reason);
      busy = "";
    }
  }

  async function stopCurrent() {
    if (busy) return;
    if (!window.confirm("Stop the current VideoFlow service? The UI will go offline.")) return;
    busy = "stop";
    error = "";
    try {
      await stopService();
      stopped = true;
    } catch (reason) {
      error = errorMessage(reason);
      busy = "";
    }
  }

  $effect(() => {
    void refresh();
  });
</script>

<section class="space-y-3">
  <div class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 class="text-sm font-semibold text-neutral-100">Local services</h2>
        <p class="mt-1 text-xs text-neutral-400">
          Inspect every VideoFlow service on this machine, stop an old version, or
          restart the service that is serving this UI.
        </p>
      </div>
      <button type="button" onclick={() => void refresh()} class="rounded-lg border border-neutral-700 px-3 py-1.5 text-[11px] text-neutral-300 hover:text-sky-200">
        Refresh
      </button>
    </div>
    {#if stopped}
      <div class="mt-3 rounded-xl border border-amber-400/20 bg-amber-950/30 p-3 text-xs text-amber-200">
        <p class="font-medium">The current service is stopped.</p>
        <p class="mt-1 text-amber-200/70">Close this tab, or run <span class="font-mono">videoflow restart</span> in a terminal.</p>
      </div>
    {:else if current}
      <div class="mt-3 grid gap-2 rounded-xl border border-neutral-800 bg-neutral-950/50 p-3 text-xs text-neutral-400 sm:grid-cols-2">
        <p>Version: <span class="text-neutral-100">{current.version ?? "unknown"}</span></p>
        <p>PID: <span class="font-mono text-neutral-100">{current.pid}</span></p>
        <p>Port: <span class="font-mono text-neutral-100">{current.port ?? "—"}</span></p>
        <p>URL: <span class="font-mono text-sky-300">{current.url ?? "—"}</span></p>
      </div>
      <div class="mt-3 flex flex-wrap gap-2">
        <button type="button" onclick={() => void restartCurrent()} disabled={Boolean(busy)} class="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-[11px] text-sky-200 disabled:opacity-40">
          {busy === "restart" ? "Restarting…" : "Restart current service"}
        </button>
        <button type="button" onclick={() => void stopCurrent()} disabled={Boolean(busy)} class="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-[11px] text-rose-200 disabled:opacity-40">
          {busy === "stop" ? "Stopping…" : "Stop current service"}
        </button>
      </div>
    {/if}
    {#if message}<p class="mt-2 text-[10px] text-emerald-300">{message}</p>{/if}
    {#if error}<p class="mt-2 text-[10px] text-rose-300">{error}</p>{/if}
    <div class="mt-3 border-t border-neutral-800 pt-3">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <p class="break-all font-mono text-[10px] text-neutral-600">{logPath}</p>
        <button type="button" onclick={() => void toggleLog()} disabled={logBusy} class="rounded-lg border border-neutral-700 px-2.5 py-1 text-[10px] text-neutral-300 disabled:opacity-40">
          {logBusy ? "Loading…" : logOpen ? "Hide server log" : "View server log"}
        </button>
      </div>
      {#if logOpen}
        <pre class="mt-2 max-h-64 overflow-auto rounded-lg border border-neutral-800 bg-neutral-950 p-3 font-mono text-[10px] leading-5 text-neutral-400">{logText || "The server log is empty."}</pre>
      {/if}
    </div>
  </div>

  <div class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div>
        <h3 class="text-xs font-semibold text-neutral-100">Doctor / diagnostics</h3>
        <p class="mt-1 text-[10px] text-neutral-500">FFmpeg, home, cache, disk, models, and environment checks.</p>
      </div>
      <button type="button" onclick={() => void runDoctor()} disabled={doctorBusy} class="rounded-lg border border-sky-500/40 px-3 py-1.5 text-[10px] text-sky-200 disabled:opacity-40">{doctorBusy ? "Running…" : "Run doctor"}</button>
    </div>
    {#if doctor}
      <pre class="mt-3 max-h-72 overflow-auto rounded-lg border border-neutral-800 bg-neutral-950 p-3 font-mono text-[10px] leading-5 text-neutral-400">{JSON.stringify(doctor, null, 2)}</pre>
    {/if}
  </div>

  <div class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div>
        <h3 class="text-xs font-semibold text-neutral-100">Other VideoFlow services</h3>
        <p class="mt-1 text-[10px] text-neutral-500">
          Only processes whose command line is a VideoFlow <span class="font-mono">serve</span>,
          <span class="font-mono">mcp</span>, or <span class="font-mono">desktop</span> process are shown.
        </p>
      </div>
      <button type="button" onclick={() => void stopAllOthers()} disabled={Boolean(busy) || !others.length} class="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-[10px] text-rose-200 disabled:opacity-40">
        {busy === "all" ? "Stopping…" : "Stop all others"}
      </button>
    </div>
    {#if others.length === 0}
      <p class="mt-3 text-xs text-neutral-500">No other services are running.</p>
    {:else}
      <div class="mt-3 space-y-2">
        {#each others as service}
          <div class="flex flex-wrap items-center gap-2 rounded-xl border border-neutral-800 bg-neutral-950/50 p-3 text-xs">
            <div class="min-w-0 flex-1">
              <p class="text-neutral-200">
                PID <span class="font-mono">{service.pid}</span>
                {#if service.version}· version {service.version}{/if}
                {#if service.port}· port <span class="font-mono">{service.port}</span>{/if}
              </p>
              <p class="mt-1 break-all font-mono text-[10px] text-neutral-600">{service.cmdline.join(" ")}</p>
            </div>
            <button type="button" onclick={() => void stopOne(service)} disabled={Boolean(busy) || service.protected} class="rounded-lg border border-rose-500/30 px-2.5 py-1 text-[10px] text-rose-200 disabled:opacity-40">
              {busy === service.pid ? "Stopping…" : "Stop"}
            </button>
          </div>
        {/each}
      </div>
    {/if}
  </div>
</section>
