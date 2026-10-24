<script lang="ts">
  import { onMount } from "svelte";
  import AssetsPanel from "$lib/AssetsPanel.svelte";
  import ActivityDrawer from "$lib/ActivityDrawer.svelte";
  import AutomationPanel from "$lib/AutomationPanel.svelte";
  import CapabilitiesPanel from "$lib/CapabilitiesPanel.svelte";
  import CommandPalette from "$lib/CommandPalette.svelte";
  import ErrorBanner from "$lib/ErrorBanner.svelte";
  import JobsPanel from "$lib/JobsPanel.svelte";
  import LibraryPanel from "$lib/LibraryPanel.svelte";
  import ModelsPanel from "$lib/ModelsPanel.svelte";
  import NotificationCenter from "$lib/NotificationCenter.svelte";
  import RecipesPanel from "$lib/RecipesPanel.svelte";
  import ServicesPanel from "$lib/ServicesPanel.svelte";
  import SettingsPanel from "$lib/SettingsPanel.svelte";
  import ShortcutsModal from "$lib/ShortcutsModal.svelte";
  import TimelinePanel from "$lib/TimelinePanel.svelte";
  import { errorMessage, getSettings, getSystem, listJobs, restartService, retryJob, stopService, type Job, type SystemInfo } from "$lib/api";
  import type { Command } from "$lib/commandPalette";
  import { t } from "$lib/i18n";
  import { noticeCounts } from "$lib/notifications";
  import { notifications } from "$lib/notifications.svelte";
  import { UI_VERSION } from "$lib/version";
  import "../app.css";

  type Tab = "recipes" | "assets" | "timeline" | "jobs" | "automation" | "library" | "models" | "services" | "providers" | "settings";

  const TABS: { id: Tab; label: string; hint: string }[] = [
    { id: "recipes", label: "Recipes", hint: "Visual recipe builder and runner" },
    { id: "assets", label: "Assets", hint: "Local media, audio, images, fonts, tags, and licenses" },
    { id: "timeline", label: "Timeline", hint: "Canvas timeline with preview, trim, split, and undo" },
    { id: "jobs", label: "Jobs", hint: "Queue, progress, approvals, and failures" },
    { id: "automation", label: "Automation", hint: "Schedules and watch folders for recipes" },
    { id: "library", label: "Library", hint: "Brand templates, presets, fonts, images, and music" },
    { id: "models", label: "Models", hint: "Optional on-demand speech and vision models" },
    { id: "services", label: "Services", hint: "Inspect, stop, and restart local VideoFlow processes" },
    { id: "providers", label: "Providers", hint: "Persistent provider configuration and fallbacks" },
    { id: "settings", label: "Settings", hint: "Local runtime, paths, models, speech, TTS, and quality" }
  ];

  const TAB_KEYS: Record<string, Tab> = {
    r: "recipes",
    a: "assets",
    t: "timeline",
    j: "jobs",
    u: "automation",
    l: "library",
    m: "models",
    v: "services",
    p: "providers",
    s: "settings"
  };

  let system = $state<SystemInfo | null>(null);
  let activeTab = $state<Tab>("recipes");
  let connecting = $state(true);
  let systemError = $state("");
  let serviceStopped = $state(false);
  let serviceBusy = $state<"" | "restart" | "stop">("");
  let serviceError = $state("");
  let allowExternal = $state(false);
  let locale = $state("en");
  let allowedHosts = $state("");
  let paletteOpen = $state(false);
  let shortcutsOpen = $state(false);
  let activityOpen = $state(false);
  let noticesOpen = $state(false);
  let jobs = $state<Job[]>([]);
  let gPending = 0;
  let jobsTimer: ReturnType<typeof setInterval> | undefined;

  const counts = $derived(noticeCounts(notifications.items));
  const attentionJobs = $derived(
    jobs.filter((job) => ["waiting_approval", "failed"].includes(job.status))
  );

  const commands = $derived<Command[]>([
    ...TABS.map((tab) => ({
      id: `tab:${tab.id}`,
      title: `Open ${tab.label}`,
      group: "Navigate",
      hint: tab.hint,
      keywords: `go ${tab.id}`
    })),
    { id: "action:notices", title: "Open notifications", group: "View", keywords: "alerts errors", shortcut: "N" },
    { id: "action:activity", title: "Open activity drawer", group: "View", keywords: "running queue", shortcut: "U" },
    { id: "action:shortcuts", title: "Show keyboard shortcuts", group: "Help", keywords: "keys help", shortcut: "?" },
    { id: "action:refresh", title: "Refresh jobs", group: "Jobs", keywords: "reload queue" },
    {
      id: "action:support",
      title: "Download the support bundle",
      group: "Maintain",
      keywords: "diagnostics logs export",
      hint: "Redacted diagnostics for local debugging"
    },
    ...jobs
      .filter((job) => ["running", "queued"].includes(job.status))
      .map((job) => ({
        id: `cancel:${job.job_id}`,
        title: `Cancel job ${job.job_id.slice(0, 8)}`,
        group: "Jobs",
        hint: job.message || job.stage,
        keywords: "stop abort"
      })),
    ...jobs
      .filter((job) => ["failed", "cancelled"].includes(job.status))
      .map((job) => ({
        id: `retry:${job.job_id}`,
        title: `Retry job ${job.job_id.slice(0, 8)}`,
        group: "Jobs",
        hint: job.message || job.stage,
        keywords: "again reenqueue"
      }))
  ]);

  function notify(kind: "info" | "success" | "warning" | "error", message: string, title = message) {
    notifications.push({ kind, title, message: title === message ? "" : message });
  }

  function onNoticeAction(actionId: string) {
    if (actionId.startsWith("tab:")) {
      selectTab(actionId.slice(4) as Tab);
      noticesOpen = false;
    } else if (actionId.startsWith("job:")) {
      selectTab("jobs");
      noticesOpen = false;
    }
  }

  async function refreshJobs() {
    try {
      jobs = await listJobs();
    } catch {
      // The activity drawer and palette keep the last known snapshot.
    }
  }

  function runCommand(command: Command) {
    paletteOpen = false;
    if (command.id.startsWith("tab:")) {
      selectTab(command.id.slice(4) as Tab);
      return;
    }
    if (command.id === "action:notices") noticesOpen = true;
    else if (command.id === "action:activity") activityOpen = true;
    else if (command.id === "action:shortcuts") shortcutsOpen = true;
    else if (command.id === "action:refresh") void refreshJobs();
    else if (command.id === "action:support") window.open("/api/v1/system/support-bundle", "_blank");
    else if (command.id.startsWith("retry:")) {
      const jobId = command.id.slice(6);
      void retryJob(jobId)
        .then(() => {
          notify("success", "Job retried.", "Job retried");
          return refreshJobs();
        })
        .catch((reason) => notify("error", errorMessage(reason), "Could not retry the job"));
    }
  }

  function onGlobalKey(event: KeyboardEvent) {
    const target = event.target as HTMLElement | null;
    const typing = target
      ? ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) || target.isContentEditable
      : false;
    const modifier = event.ctrlKey || event.metaKey;

    if (modifier && event.key.toLowerCase() === "k") {
      event.preventDefault();
      paletteOpen = !paletteOpen;
      return;
    }
    if (event.key === "Escape") {
      paletteOpen = false;
      shortcutsOpen = false;
      activityOpen = false;
      noticesOpen = false;
      return;
    }
    if (typing || modifier || event.altKey) return;

    if (event.key === "?") {
      event.preventDefault();
      shortcutsOpen = true;
      return;
    }
    if (event.key.toLowerCase() === "n") {
      noticesOpen = !noticesOpen;
      return;
    }
    if (event.key.toLowerCase() === "u") {
      activityOpen = !activityOpen;
      return;
    }
    if (event.key.toLowerCase() === "g") {
      gPending = Date.now();
      return;
    }
    const tab = TAB_KEYS[event.key.toLowerCase()];
    if (tab && Date.now() - gPending < 1200) {
      gPending = 0;
      selectTab(tab);
    }
  }

  async function connectToService() {
    connecting = true;
    systemError = "";
    for (let attempt = 0; attempt < 30; attempt += 1) {
      try {
        system = await getSystem();
        connecting = false;
        return;
      } catch (reason) {
        systemError = errorMessage(reason);
        if (attempt === 29) {
          connecting = false;
          return;
        }
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
    }
  }

  async function restartLocalService() {
    if (serviceBusy) return;
    serviceBusy = "restart";
    serviceError = "";
    try {
      await restartService();
      await new Promise((resolve) => setTimeout(resolve, 1600));
      for (let attempt = 0; attempt < 30; attempt += 1) {
        try {
          const response = await fetch("/health", { cache: "no-store" });
          if (response.ok) {
            window.location.reload();
            return;
          }
        } catch {
          // The server is between processes; keep polling.
        }
        await new Promise((resolve) => setTimeout(resolve, 500));
      }
      serviceError = "The service did not answer after restarting. Reopen VideoFlow.";
    } catch (reason) {
      serviceError = errorMessage(reason);
    } finally {
      serviceBusy = "";
    }
  }

  async function stopLocalService() {
    if (serviceBusy) return;
    serviceBusy = "stop";
    serviceError = "";
    try {
      await stopService();
      serviceStopped = true;
    } catch (reason) {
      const message = errorMessage(reason);
      serviceStopped = message.includes("fetch") || message.includes("Failed");
      serviceError = serviceStopped ? "" : message;
    } finally {
      serviceBusy = "";
    }
  }

  function hardReload() {
    window.location.href = `/?v=${encodeURIComponent(UI_VERSION)}`;
  }

  function selectTab(tab: Tab) {
    activeTab = tab;
    history.replaceState(null, "", `#${tab}`);
  }

  function syncHash() {
    const hash = window.location.hash.replace("#", "") as Tab;
    if (TABS.some((tab) => tab.id === hash)) activeTab = hash;
  }

  onMount(() => {
    syncHash();
    window.addEventListener("hashchange", syncHash);
    window.addEventListener("keydown", onGlobalKey);
    void connectToService();
    void refreshJobs();
    jobsTimer = setInterval(() => void refreshJobs(), 8000);
    void getSettings()
      .then(({ settings }) => {
        locale = settings.runtime.locale || "en";
        document.documentElement.dataset.theme = settings.ui.theme;
        document.documentElement.dataset.density = settings.ui.density;
      })
      .catch(() => {});
    return () => {
      window.removeEventListener("hashchange", syncHash);
      window.removeEventListener("keydown", onGlobalKey);
      clearInterval(jobsTimer);
    };
  });
</script>

<svelte:head>
  <title>VideoFlow — Recipe studio</title>
  <meta name="description" content="Local, non-destructive video pre-edit pipeline." />
</svelte:head>

<div class="min-h-screen bg-neutral-950">
  <a href="#workspace-content" class="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[80] focus:rounded-lg focus:bg-sky-500 focus:px-3 focus:py-2 focus:text-sm focus:text-neutral-950">Skip to content</a>
  <div class={`mx-auto flex min-h-screen flex-col gap-5 px-4 py-6 sm:px-6 lg:px-8 ${activeTab === "recipes" || activeTab === "timeline" ? "max-w-[1800px]" : "max-w-[1600px]"}`}>
    <header class="flex flex-wrap items-center justify-between gap-4">
      <div class="flex items-center gap-3">
        <div class="flex h-11 w-11 items-center justify-center rounded-2xl bg-sky-500/15 text-sky-300 ring-1 ring-inset ring-sky-400/20">
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <rect x="3" y="5" width="18" height="14" rx="2" />
            <path d="M7 5v14M17 5v14M3 9h4M3 15h4M17 9h4M17 15h4" />
          </svg>
        </div>
        <div>
          <div class="flex items-center gap-2">
            <h1 class="text-xl font-semibold tracking-tight text-white">VideoFlow</h1>
            <span class="rounded-full border border-white/10 px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide text-neutral-500">recipe studio</span>
          </div>
          <p class="mt-0.5 text-xs text-neutral-500">{t(locale, "subtitle")}</p>
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-2 text-xs">
        <span class="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 font-mono text-[11px] text-neutral-400" title="Server version">server {system?.version ?? (connecting ? "connecting…" : "offline")}</span>
        <span class="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 font-mono text-[11px] text-neutral-500" title="UI bundle version">ui {UI_VERSION}</span>
        <span class="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[11px] text-neutral-500">FFmpeg {system?.ffmpeg ? "ready" : connecting ? "checking…" : "missing"}</span>
        <button
          type="button"
          onclick={() => (activityOpen = true)}
          class="relative rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[11px] text-neutral-400 transition hover:border-sky-500/50 hover:text-sky-300"
          title="Activity drawer (U)"
        >
          Activity
          {#if jobs.filter((job) => ["running", "queued"].includes(job.status)).length}
            <span class="ml-1 rounded-full bg-sky-500/20 px-1.5 py-0.5 font-mono text-[10px] text-sky-200">{jobs.filter((job) => ["running", "queued"].includes(job.status)).length}</span>
          {/if}
        </button>
        <button
          type="button"
          onclick={() => (noticesOpen = true)}
          class="relative rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[11px] text-neutral-400 transition hover:border-sky-500/50 hover:text-sky-300"
          title="Notification center (N)"
        >
          Notifications
          {#if counts.errors + counts.warnings + attentionJobs.length}
            <span class={`ml-1 rounded-full px-1.5 py-0.5 font-mono text-[10px] ${counts.errors ? "bg-rose-500/20 text-rose-200" : "bg-amber-400/20 text-amber-200"}`}>{counts.errors + counts.warnings + attentionJobs.length}</span>
          {/if}
        </button>
        <button
          type="button"
          onclick={() => (paletteOpen = true)}
          class="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 font-mono text-[11px] text-neutral-400 transition hover:border-sky-500/50 hover:text-sky-300"
          title="Command palette (Ctrl/Cmd + K)"
        >⌘K</button>
        <button
          type="button"
          onclick={() => (shortcutsOpen = true)}
          class="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[11px] text-neutral-400 transition hover:border-sky-500/50 hover:text-sky-300"
          aria-label="Keyboard shortcuts"
          title="Keyboard shortcuts (?)"
        >?</button>
        {#if serviceStopped}
          <span class="rounded-full border border-amber-400/20 bg-amber-400/10 px-3 py-1 text-[11px] text-amber-200">Service stopped · close this tab</span>
        {:else}
          <button type="button" onclick={() => void restartLocalService()} disabled={Boolean(serviceBusy)} class="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[11px] text-neutral-400 transition hover:border-sky-500/50 hover:text-sky-300 disabled:opacity-40">
            {serviceBusy === "restart" ? "Restarting…" : "Restart service"}
          </button>
          <button type="button" onclick={() => void stopLocalService()} disabled={Boolean(serviceBusy)} class="rounded-full border border-rose-500/20 bg-rose-500/[0.04] px-3 py-1 text-[11px] text-rose-300 transition hover:border-rose-400/40 hover:bg-rose-500/10 disabled:opacity-40">
            {serviceBusy === "stop" ? "Stopping…" : "Stop service"}
          </button>
        {/if}
      </div>
    </header>

    <nav class="sticky top-0 z-30 -mx-1 overflow-x-auto rounded-2xl border border-neutral-800 bg-neutral-950/95 p-1 shadow-lg shadow-black/30 backdrop-blur" aria-label={t(locale, "workspace")}>
      <div class="flex min-w-max gap-1" role="tablist" aria-label={t(locale, "workspace")}>
        {#each TABS as tab}
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            title={tab.hint}
            onclick={() => selectTab(tab.id)}
            class={`rounded-xl px-3 py-2 text-xs font-medium transition ${activeTab === tab.id ? "bg-sky-500/15 text-sky-200 ring-1 ring-inset ring-sky-400/20" : "text-neutral-400 hover:bg-white/[0.04] hover:text-neutral-200"}`}
          >
            {t(locale, tab.id)}
          </button>
        {/each}
      </div>
    </nav>

    <ErrorBanner
      message={[serviceError, systemError].filter(Boolean).join(" · ")}
      title="The local service reported a problem"
      onDismiss={() => {
        serviceError = "";
        systemError = "";
      }}
      testId="global-error-banner"
    />

    {#if system && system.version !== UI_VERSION}
      <div class="rounded-2xl border border-amber-400/20 bg-amber-950/30 px-4 py-3 text-xs text-amber-200">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <p>Server <span class="font-mono">{system.version}</span> and UI <span class="font-mono">{UI_VERSION}</span> are different. Reload the UI from this server.</p>
          <button type="button" onclick={hardReload} class="rounded-lg border border-amber-400/30 px-3 py-1.5 text-[11px]">Reload UI</button>
        </div>
      </div>
    {/if}

    {#if !system && !serviceStopped}
      <div class="rounded-2xl border border-sky-400/20 bg-sky-950/30 px-4 py-3 text-xs text-sky-200">
        <div class="flex flex-wrap items-center justify-between gap-2">
          <div>
            <p class="font-medium">{connecting ? "Connecting to the local VideoFlow service…" : "Could not reach the local service."}</p>
            <p class="mt-1 text-sky-200/70">
              {connecting ? "The portable build can take a few seconds to unpack on first launch." : systemError || "Start VideoFlow again or run videoflow restart."}
            </p>
          </div>
          <button type="button" onclick={() => void connectToService()} disabled={connecting} class="rounded-lg border border-sky-400/30 px-3 py-1.5 text-[11px] disabled:opacity-40">
            {connecting ? "Connecting…" : "Retry now"}
          </button>
        </div>
      </div>
    {/if}

    {#if serviceStopped}
      <div class="rounded-2xl border border-amber-400/20 bg-amber-950/30 px-4 py-3 text-xs text-amber-200">
        <p class="font-medium">The local service is stopped.</p>
        <p class="mt-1 text-amber-200/70">Close this tab. To start again, reopen VideoFlow or run <span class="font-mono">videoflow restart</span> in a terminal.</p>
      </div>
    {/if}

    <div id="workspace-content" class="scroll-mt-24">
      {#if activeTab === "recipes"}
        <RecipesPanel />
      {:else if activeTab === "assets"}
        <AssetsPanel />
      {:else if activeTab === "timeline"}
        <TimelinePanel />
      {:else if activeTab === "jobs"}
        <JobsPanel
          onreview={() => selectTab("recipes")}
          onopentimeline={() => selectTab("timeline")}
        />
      {:else if activeTab === "automation"}
        <AutomationPanel />
      {:else if activeTab === "library"}
        <LibraryPanel />
      {:else if activeTab === "models"}
        <ModelsPanel />
      {:else if activeTab === "services"}
        <ServicesPanel />
      {:else if activeTab === "providers"}
        <CapabilitiesPanel
          allowExternal={allowExternal}
          {allowedHosts}
          onToggle={(value) => (allowExternal = value)}
          onHosts={(value) => (allowedHosts = value)}
        />
      {:else if activeTab === "settings"}
        <SettingsPanel />
      {/if}
    </div>

    <footer class="pb-4 text-xs text-neutral-500">
      <p>Local only. The server binds to 127.0.0.1. Project state stays the timeline source of truth; SQLite is the operational store for jobs, assets, and batches.</p>
    </footer>
  </div>
</div>

<ActivityDrawer
  open={activityOpen}
  {jobs}
  onclose={() => (activityOpen = false)}
  onopenjobs={() => {
    activityOpen = false;
    selectTab("jobs");
  }}
/>
<CommandPalette
  open={paletteOpen}
  {commands}
  onrun={runCommand}
  onclose={() => (paletteOpen = false)}
/>
<ShortcutsModal open={shortcutsOpen} onclose={() => (shortcutsOpen = false)} />
<NotificationCenter
  open={noticesOpen}
  onclose={() => (noticesOpen = false)}
  onaction={onNoticeAction}
/>
