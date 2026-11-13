<script lang="ts">
  import { onMount, tick } from "svelte";
  import AssetsPanel from "$lib/AssetsPanel.svelte";
  import ActivityDrawer from "$lib/ActivityDrawer.svelte";
  import AutomationPanel from "$lib/AutomationPanel.svelte";
  import CapabilitiesPanel from "$lib/CapabilitiesPanel.svelte";
  import LameraWorkspace from "$lib/LameraWorkspace.svelte";
  import CommandPalette from "$lib/CommandPalette.svelte";
  import CopilotPanel from "$lib/CopilotPanel.svelte";
  import IntegrationsPanel from "$lib/IntegrationsPanel.svelte";
  import ErrorBanner from "$lib/ErrorBanner.svelte";
  import JobsPanel from "$lib/JobsPanel.svelte";
  import LibraryPanel from "$lib/LibraryPanel.svelte";
  import ModelsPanel from "$lib/ModelsPanel.svelte";
  import NotificationCenter from "$lib/NotificationCenter.svelte";
  import OnboardingCard from "$lib/OnboardingCard.svelte";
  import Modal from "$lib/ui/Modal.svelte";
  import PluginsPanel from "$lib/PluginsPanel.svelte";
  import HitlInbox from "$lib/HitlInbox.svelte";
  import ProduceHome from "$lib/ProduceHome.svelte";
  import RecipeWorkspace from "$lib/RecipeWorkspace.svelte";
  import RecipesPanel from "$lib/RecipesPanel.svelte";
  import ServicesPanel from "$lib/ServicesPanel.svelte";
  import SettingsPanel from "$lib/SettingsPanel.svelte";
  import ShortcutsModal from "$lib/ShortcutsModal.svelte";
  import TimelinePanel from "$lib/TimelinePanel.svelte";
  import Icon from "$lib/ui/Icon.svelte";
  import Logo from "$lib/ui/Logo.svelte";
  import Progress from "$lib/ui/Progress.svelte";
  import { errorMessage, getSettings, getSystem, listJobs, listPendingInteractions, restartService, retryJob, saveSettings, stopService, type AppSettings, type HiltPending, type Job, type SystemInfo } from "$lib/api";
  import type { Command } from "$lib/commandPalette";
  import { recordRecentCommand } from "$lib/commandPalette";
  import { t } from "$lib/i18n";
  import { i18n } from "$lib/i18n.svelte";
  import { translateTree } from "$lib/domI18n";
  import { jobDisplayName } from "$lib/jobsView";
import { noticeCounts } from "$lib/notifications";
  import { notifications } from "$lib/notifications.svelte";
  import { UI_VERSION } from "$lib/version";
  import "../app.css";

  import {
    AREAS,
    AREA_ICONS,
    TAB_ICONS,
    areaForTab,
    areaTabs,
    defaultTabForArea,
    hashFor,
    isTabId,
    resolveRoute,
    type AreaId,
    type TabId
  } from "$lib/navigation";

  const TAB_HINTS: Record<TabId, string> = {
    overview: "Favorites, pending gates, and recent runs",
    recipes: "Visual recipe builder and runner",
    lamera: "Dedicated Lamera run console and HITL inbox",
    assistant: "LLM recipe drafts and timeline edit plans",
    timeline: "Canvas timeline with preview, trim, split, and undo",
    jobs: "Queue, progress, approvals, pauses, and failures",
    schedules: "Schedules and watch folders for recipes",
    media: "Local media, audio, images, fonts, tags, and licenses",
    brand: "Brand templates, presets, fonts, images, music, and SFX",
    models: "Optional on-demand speech and vision models",
    providers: "AI provider configuration, tests, and fallbacks",
    services: "Inspect, stop, and restart local VideoFlow processes",
    extensions: "Local plugin packages, sandbox status, and panels",
    connect: "MCP and REST setup for OpenCode, Paperclip, and DeepSeek",
    settings: "Local runtime, paths, models, speech, TTS, and quality"
  };

  const TAB_KEYS: Record<string, TabId> = {
    o: "overview",
    r: "recipes",
    d: "lamera",
    c: "assistant",
    t: "timeline",
    j: "jobs",
    u: "schedules",
    a: "media",
    l: "brand",
    m: "models",
    v: "services",
    p: "providers",
    e: "extensions",
    i: "connect",
    s: "settings"
  };

  let system = $state<SystemInfo | null>(null);
  let activeTab = $state<TabId>("recipes");
  const activeArea = $derived(areaForTab(activeTab));
  const subTabs = $derived(areaTabs(activeArea));
  let connecting = $state(true);
  let systemError = $state("");
  let serviceStopped = $state(false);
  let serviceBusy = $state<"" | "restart" | "stop">("");
  let serviceError = $state("");
  let allowExternal = $state(false);
  let locale = $state("en");
  let allowedHosts = $state("");
  let paletteOpen = $state(false);
  let recentCommands = $state<string[]>([]);
  let shortcutsOpen = $state(false);
  let activityOpen = $state(false);
  let noticesOpen = $state(false);
  let onboardingOpen = $state(false);
  let jobs = $state<Job[]>([]);
  let pendingHilt = $state<HiltPending[]>([]);
  let inboxOpen = $state(false);
  let workspaceJobId = $state("");
  let gPending = 0;
  let jobsTimer: ReturnType<typeof setInterval> | undefined;

  const counts = $derived(noticeCounts(notifications.items));
  const attentionJobs = $derived(
    jobs.filter((job) => ["waiting_approval", "failed"].includes(job.status))
  );
  const runningJobs = $derived(
    jobs.filter((job) => ["running", "queued"].includes(job.status))
  );
  const hasRunningJob = $derived(
    jobs.some((job) => job.status === "running")
  );

  const commands = $derived<Command[]>([
    ...AREAS.map((area) => ({
      id: `area:${area.id}`,
      title: `Go to ${t(locale, area.id)}`,
      group: "Navigate",
      hint: t(locale, `${area.id}_hint`),
      keywords: `area ${area.id}`
    })),
    ...AREAS.flatMap((area) =>
      area.tabs.map((tab) => ({
        id: `tab:${tab}`,
        title: `${t(locale, area.id)} · ${t(locale, tab)}`,
        group: "Navigate",
        hint: TAB_HINTS[tab],
        keywords: `go ${tab} ${area.id}`
      }))
    ),
    { id: "action:notices", title: "Open notifications", group: "View", keywords: "alerts errors", shortcut: "N" },
    { id: "action:activity", title: "Open activity drawer", group: "View", keywords: "running queue", shortcut: "U" },
    { id: "action:theme", title: "Cycle theme", group: "View", keywords: "dark light contrast system" },
    { id: "action:search-jobs", title: "Search jobs", group: "Jobs", keywords: "filter find", shortcut: "/" },
    { id: "action:shortcuts", title: "Show keyboard shortcuts", group: "Help", keywords: "keys help", shortcut: "?" },
    { id: "action:refresh", title: "Refresh jobs", group: "Jobs", keywords: "reload queue" },
    { id: "action:builder:add-step", title: "Recipe: add step", group: "Recipe builder", keywords: "node step palette", shortcut: "A" },
    { id: "action:builder:run", title: "Recipe: run", group: "Recipe builder", keywords: "execute start", shortcut: "Ctrl+Enter" },
    { id: "action:builder:dry-run", title: "Recipe: dry run", group: "Recipe builder", keywords: "plan preview" },
    { id: "action:builder:save", title: "Recipe: save", group: "Recipe builder", keywords: "persist", shortcut: "Ctrl+S" },
    { id: "action:builder:validate", title: "Recipe: validate", group: "Recipe builder", keywords: "check graph" },
    { id: "action:builder:inspector", title: "Recipe: toggle inspector", group: "Recipe builder", keywords: "panel details" },
    { id: "action:builder:auto-layout", title: "Recipe: auto layout", group: "Recipe builder", keywords: "arrange graph" },
    { id: "action:builder:json", title: "Recipe: open JSON", group: "Recipe builder", keywords: "source" },
    { id: "action:builder:runs", title: "Recipe: run history", group: "Recipe builder", keywords: "past executions" },
    {
      id: "action:support",
      title: "Download the support bundle",
      group: "Maintain",
      keywords: "diagnostics logs export",
      hint: "Redacted diagnostics for local debugging"
    },
    {
      id: "action:restart",
      title: "Restart the local service",
      group: "Maintain",
      keywords: "service restart reload",
      hint: "Reloads the local API and the studio"
    },
    {
      id: "action:stop",
      title: "Stop the local service",
      group: "Maintain",
      keywords: "service stop shutdown",
      hint: "Stops the local API; reopen VideoFlow to start again"
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

  function notify(
    kind: "info" | "success" | "warning" | "error",
    message: string,
    title = message,
    code = "",
    detail = ""
  ) {
    notifications.push({
      kind,
      category: kind === "error" || kind === "warning" ? "blocker" : "action",
      title,
      message: title === message ? "" : message,
      code,
      detail
    });
  }

  function onNoticeAction(actionId: string) {
    if (actionId.startsWith("tab:")) {
      selectTab(actionId.slice(4) as TabId);
      noticesOpen = false;
    } else if (actionId.startsWith("job:")) {
      selectTab("jobs");
      noticesOpen = false;
    }
  }

  const previousJobStatus = new Map<string, string>();

  async function refreshHilt() {
    try {
      pendingHilt = await listPendingInteractions();
    } catch {
      pendingHilt = [];
    }
  }

  async function refreshJobs() {
    try {
      const next = await listJobs();
      if (previousJobStatus.size) {
        for (const job of next) {
          const previous = previousJobStatus.get(job.job_id);
          if (!previous || previous === job.status) continue;
          if (job.status === "waiting_approval" || job.status === "waiting_input") {
            notifications.push({
              kind: "warning",
              category: "hilt",
              title: "Human review requested",
              message: jobDisplayName(job),
              actionLabel: "Open jobs",
              actionId: `job:${job.job_id}`
            });
          } else if (["succeeded", "failed", "cancelled"].includes(job.status)) {
            notifications.push({
              kind: job.status === "failed" ? "warning" : "info",
              category: "job_finished",
              title:
                job.status === "succeeded"
                  ? "Job finished"
                  : job.status === "failed"
                    ? "Job failed"
                    : "Job cancelled",
              message: jobDisplayName(job),
              actionLabel: "Open jobs",
              actionId: `job:${job.job_id}`
            });
          }
        }
      }
      for (const job of next) previousJobStatus.set(job.job_id, job.status);
      jobs = next;
    } catch {
      // The activity drawer and palette keep the last known snapshot.
    }
  }

  function runCommand(command: Command) {
    paletteOpen = false;
    recentCommands = recordRecentCommand(recentCommands, command.id);
    localStorage.setItem("videoflow.recent-commands", JSON.stringify(recentCommands));
    if (command.id.startsWith("area:")) {
      const area = command.id.slice(5) as AreaId;
      selectTab(defaultTabForArea(area));
      return;
    }
    if (command.id.startsWith("tab:")) {
      selectTab(command.id.slice(4) as TabId);
      return;
    }
    if (command.id.startsWith("action:builder:")) {
      const action = command.id.slice("action:builder:".length);
      selectTab("recipes");
      setTimeout(() => {
        window.dispatchEvent(new CustomEvent("videoflow:builder-action", { detail: action }));
      }, 60);
      return;
    }
    if (command.id === "action:notices") noticesOpen = true;
    else if (command.id === "action:activity") activityOpen = true;
    else if (command.id === "action:theme") void cycleTheme();
    else if (command.id === "action:search-jobs") {
      selectTab("jobs");
      requestAnimationFrame(() => {
        window.dispatchEvent(new CustomEvent("videoflow:focus-jobs-search"));
      });
    }
    else if (command.id === "action:shortcuts") shortcutsOpen = true;
    else if (command.id === "action:refresh") void refreshJobs();
    else if (command.id === "action:support") window.open("/api/v1/system/support-bundle", "_blank");
    else if (command.id === "action:restart") void restartLocalService();
    else if (command.id === "action:stop") void stopLocalService();
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
    if (event.key === "/") {
      event.preventDefault();
      if (activeTab !== "jobs") selectTab("jobs");
      requestAnimationFrame(() => {
        window.dispatchEvent(new CustomEvent("videoflow:focus-jobs-search"));
      });
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
        if (system.settings_error) {
          notify("warning", system.settings_error, "Settings file is invalid");
        }
        if (system.database_error) {
          notify("warning", system.database_error, "Database is degraded");
        }
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

  function onTabKey(
    event: KeyboardEvent,
    ids: string[],
    current: string,
    select: (id: string) => void
  ) {
    if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const index = ids.indexOf(current);
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? ids.length - 1
          : event.key === "ArrowRight"
            ? (index + 1) % ids.length
            : (index - 1 + ids.length) % ids.length;
    select(ids[next]);
    const parent = (event.currentTarget as HTMLElement).parentElement;
    requestAnimationFrame(() => {
      const tabs = parent?.querySelectorAll<HTMLElement>('[role="tab"]');
      tabs?.[next]?.focus();
    });
  }

  async function editRecipe(recipeId: string) {
    try {
      sessionStorage.setItem("videoflow:requested-recipe", recipeId);
    } catch {
      // Session storage is best effort; the builder can still be opened.
    }
    selectTab("recipes");
    await tick();
    window.dispatchEvent(
      new CustomEvent("videoflow:load-recipe", { detail: recipeId })
    );
  }

  function selectTab(tab: TabId) {
    workspaceJobId = "";
    activeTab = tab;
    history.replaceState(null, "", hashFor(tab));
    localStorage.setItem("videoflow.tab", tab);
    if (typeof window !== "undefined") {
      const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      window.scrollTo({ top: 0, behavior: reduce ? "auto" : "smooth" });
    }
  }

  $effect(() => {
    activeTab;
    locale;
    if (typeof document === "undefined") return;
    void tick().then(() => translateTree(document.body, locale));
  });

  $effect(() => {
    if (typeof document === "undefined") return;
    const area = t(locale, activeArea);
    const tab = t(locale, activeTab);
    const suffix = runningJobs.length ? ` · ${runningJobs.length} running` : "";
    document.title = `VideoFlow — ${area} · ${tab}${suffix}`;
  });

  function applyTheme(theme: string) {
    if (typeof document === "undefined") return;
    document.documentElement.dataset.theme = theme;
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute(
        "content",
        theme === "light" ? "#f8fafc" : theme === "high-contrast" ? "#000000" : "#09090b"
      );
    }
  }

  const THEMES: AppSettings["ui"]["theme"][] = [
    "dark",
    "light",
    "high-contrast",
    "system"
  ];

  async function cycleTheme() {
    const current = document.documentElement.dataset.theme || "dark";
    const index = THEMES.indexOf(current as AppSettings["ui"]["theme"]);
    const next = THEMES[(index + 1) % THEMES.length];
    applyTheme(next);
    try {
      const { settings } = await getSettings();
      if (!settings) return;
      settings.ui.theme = next;
      await saveSettings(settings);
      notify("success", `Theme set to ${next}.`, "Theme");
    } catch (reason) {
      notify("error", errorMessage(reason), "Could not save the theme");
    }
  }

  function syncHash() {
    const run = window.location.hash.match(/^#run\/([^/?]+)/);
    if (run) {
      workspaceJobId = decodeURIComponent(run[1]);
      activeTab = "jobs";
      return;
    }
    workspaceJobId = "";
    activeTab = resolveRoute(window.location.hash).tab;
  }

  function openWorkspace(jobId: string) {
    if (!jobId) return;
    workspaceJobId = jobId;
    activeTab = "jobs";
    history.replaceState(null, "", `#run/${encodeURIComponent(jobId)}`);
    window.scrollTo({ top: 0, behavior: "auto" });
  }

  function onUseTimeline(event: Event) {
    const path = String((event as CustomEvent<{ path?: string }>).detail?.path ?? "");
    if (!path) return;
    selectTab("recipes");
    setTimeout(() => {
      window.dispatchEvent(
        new CustomEvent("videoflow:builder-action", {
          detail: { action: "load-timeline", path }
        })
      );
    }, 80);
  }

  onMount(() => {
    try {
      const saved = JSON.parse(
        localStorage.getItem("videoflow.recent-commands") ?? "[]"
      );
      if (Array.isArray(saved)) {
        recentCommands = saved.filter((item) => typeof item === "string").slice(0, 5);
      }
    } catch {
      recentCommands = [];
    }
    if (!window.location.hash) {
      const saved = localStorage.getItem("videoflow.tab");
      if (saved && isTabId(saved)) {
        history.replaceState(null, "", hashFor(saved));
      }
    }
    syncHash();
    window.addEventListener("hashchange", syncHash);
    window.addEventListener("keydown", onGlobalKey);
    let lastApiError = "";
    let lastApiErrorAt = 0;
    const onApiError = (event: Event) => {
      const detail = (event as CustomEvent<{
        title?: string;
        code?: string;
        message?: string;
        detail?: string;
        path?: string;
      }>).detail;
      const key = `${detail.code ?? ""}|${detail.message ?? ""}|${detail.path ?? ""}`;
      const now = Date.now();
      if (key === lastApiError && now - lastApiErrorAt < 5000) return;
      lastApiError = key;
      lastApiErrorAt = now;
      notify(
        "error",
        detail.message ?? "Backend request failed",
        detail.title ?? "Backend error",
        detail.code ?? "",
        detail.detail ?? ""
      );
    };
    window.addEventListener("videoflow:api-error", onApiError);
    window.addEventListener("videoflow:use-timeline", onUseTimeline);
    void connectToService();
    void refreshJobs();
    void refreshHilt();
    jobsTimer = setInterval(() => {
      if (!document.hidden) {
        void refreshJobs();
        void refreshHilt();
      }
    }, 8000);
    void getSettings()
      .then(({ settings }) => {
        locale = settings.runtime.locale || "en";
        i18n.set(locale);
        applyTheme(settings.ui.theme);
        document.documentElement.dataset.density = settings.ui.density;
        notifications.setLevel(settings.notifications?.ui_level ?? "minimal");
      })
      .catch(() => {});
    return () => {
      window.removeEventListener("hashchange", syncHash);
      window.removeEventListener("keydown", onGlobalKey);
      window.removeEventListener("videoflow:api-error", onApiError);
      window.removeEventListener("videoflow:use-timeline", onUseTimeline);
      clearInterval(jobsTimer);
    };
  });
</script>

<svelte:head>
  <title>VideoFlow — Recipe studio</title>
  <meta name="description" content="Local, non-destructive video pre-edit pipeline." />
  <meta property="og:title" content="VideoFlow" />
  <meta property="og:description" content="Local, non-destructive video pre-edit studio with recipes, a canvas timeline, and NLE exports." />
  <meta property="og:type" content="website" />
  <meta name="twitter:card" content="summary" />
</svelte:head>

<div class="min-h-screen bg-neutral-950">
  <div class="vf-backdrop pointer-events-none fixed inset-0 -z-10" aria-hidden="true">
    <div class="absolute -top-48 left-1/2 h-[40rem] w-[70rem] -translate-x-1/2 rounded-full bg-sky-500/[0.07] blur-[130px]"></div>
    <div class="absolute -bottom-64 right-[-12rem] h-[34rem] w-[34rem] rounded-full bg-indigo-500/[0.07] blur-[130px]"></div>
    <div class="vf-ambient absolute inset-0"></div>
  </div>
  <div class="pointer-events-none fixed inset-x-0 top-0 z-50 h-px bg-gradient-to-r from-transparent via-sky-400/70 to-transparent" aria-hidden="true"></div>
  <a href="#workspace-content" class="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[80] focus:rounded-lg focus:bg-sky-500 focus:px-3 focus:py-2 focus:text-sm focus:text-neutral-950">Skip to content</a>
  <div class="vf-shell mx-auto min-h-screen px-3 py-4 sm:px-5 lg:px-6">
    <aside class="rounded-2xl border border-neutral-800 bg-neutral-950/80 p-3 lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto lg:p-4">
      <div class="flex items-center gap-3 lg:flex-col lg:items-start">
        <Logo size={40} />
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <h1 class="text-[length:var(--vf-text-xl)] font-semibold tracking-tight text-white">VideoFlow</h1>
            <span class="rounded-full border border-sky-400/20 bg-sky-400/[0.06] px-2 py-0.5 text-[length:var(--vf-text-2xs)] font-medium uppercase tracking-[0.16em] text-sky-200/80">studio</span>
          </div>
          <p class="mt-1 text-[length:var(--vf-text-xs)] leading-5 text-neutral-400">{t(locale, "subtitle")}</p>
        </div>
      </div>

      <nav class="mt-4" aria-label={t(locale, "workspace")}>
        <div class="flex gap-1 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible lg:pb-0" role="tablist" aria-label={t(locale, "workspace")}>
          {#each AREAS as area}
            <button
              type="button"
              role="tab"
              aria-selected={activeArea === area.id}
              aria-label={t(locale, area.id)}
              title={t(locale, `${area.id}_hint`)}
              onclick={() => selectTab(defaultTabForArea(area.id))}
              onkeydown={(event) => onTabKey(event, AREAS.map((item) => item.id), area.id, (id) => selectTab(defaultTabForArea(id as AreaId)))}
              class={`flex min-h-10 shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-left text-[length:var(--vf-text-sm)] font-medium transition-colors lg:w-full ${activeArea === area.id ? "bg-sky-500/15 text-sky-100 ring-1 ring-inset ring-sky-400/20" : "text-neutral-400 hover:bg-white/[0.04] hover:text-neutral-100"}`}
            >
              <Icon name={AREA_ICONS[area.id]} size={15} class={activeArea === area.id ? "text-sky-300" : ""} />
              <span class="whitespace-nowrap">{t(locale, area.id)}</span>
            </button>
          {/each}
        </div>

        {#if subTabs.length > 1}
          <div class="mt-3 border-t border-neutral-800 pt-3">
            <p class="vf-label mb-2 hidden lg:block">{t(locale, activeArea)}</p>
            <div class="flex gap-1 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible lg:pb-0" role="tablist" aria-label={t(locale, activeArea)}>
              {#each subTabs as tabId}
                <button
                  type="button"
                  role="tab"
                  aria-selected={activeTab === tabId}
                  aria-label={t(locale, tabId)}
                  title={TAB_HINTS[tabId]}
                  onclick={() => selectTab(tabId)}
                  onkeydown={(event) => onTabKey(event, subTabs, tabId, (id) => selectTab(id as TabId))}
                  class={`flex min-h-9 shrink-0 items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[length:var(--vf-text-xs)] transition-colors lg:w-full ${activeTab === tabId ? "bg-white/[0.07] text-neutral-100" : "text-neutral-500 hover:bg-white/[0.03] hover:text-neutral-200"}`}
                >
                  <Icon name={TAB_ICONS[tabId]} size={13} class={activeTab === tabId ? "text-sky-300" : ""} />
                  <span class="whitespace-nowrap">{t(locale, tabId)}</span>
                </button>
              {/each}
            </div>
          </div>
        {/if}
      </nav>

      <div class="mt-4 hidden space-y-2 border-t border-neutral-800 pt-3 lg:block">
        <span class="inline-flex w-full items-center rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1.5 font-mono text-[length:var(--vf-text-2xs)] text-neutral-400" title="Server version">
          <span class={`mr-1.5 h-1.5 w-1.5 rounded-full ${system ? "bg-emerald-400" : connecting ? "animate-pulse bg-amber-400" : "bg-rose-400"}`} aria-hidden="true"></span>
          server {system?.version ?? (connecting ? "connecting…" : "offline")}
        </span>
        <div class="flex items-center justify-between gap-2 px-1 text-[length:var(--vf-text-2xs)] text-neutral-500">
          <span title="UI bundle version">ui {UI_VERSION}</span>
          <span>FFmpeg {system?.ffmpeg ? "ready" : connecting ? "checking…" : "missing"}</span>
        </div>
      </div>
    </aside>

    <div class="flex min-w-0 flex-col gap-4">
      <header class="flex flex-wrap items-start justify-between gap-3 rounded-2xl border border-neutral-800 bg-neutral-950/80 px-4 py-3">
        <div class="min-w-0">
          <div class="flex items-center gap-1.5 text-[length:var(--vf-text-xs)] text-neutral-500">
            <span>{t(locale, activeArea)}</span>
            <span aria-hidden="true">/</span>
            <span class="text-neutral-300">{t(locale, activeTab)}</span>
          </div>
          <p class="mt-1 truncate text-[length:var(--vf-text-xl)] font-semibold tracking-tight text-white">{t(locale, activeTab)}</p>
          <p class="mt-0.5 hidden max-w-2xl truncate text-[length:var(--vf-text-xs)] text-neutral-500 sm:block">{TAB_HINTS[activeTab]}</p>
        </div>
        <div class="flex flex-wrap items-center justify-end gap-1.5">
          <span class="inline-flex items-center rounded-lg border border-white/10 bg-white/[0.03] px-2.5 py-1 font-mono text-[length:var(--vf-text-2xs)] text-neutral-400 lg:hidden" title="Server status">
            <span class={`mr-1.5 h-1.5 w-1.5 rounded-full ${system ? "bg-emerald-400" : connecting ? "animate-pulse bg-amber-400" : "bg-rose-400"}`} aria-hidden="true"></span>
            {system?.version ?? (connecting ? "connecting…" : "offline")}
          </span>
          <button
            type="button"
            onclick={() => void cycleTheme()}
            class="inline-flex h-9 items-center justify-center rounded-lg border border-white/10 bg-white/[0.03] px-2.5 text-neutral-400 transition-colors hover:border-sky-500/50 hover:text-sky-200"
            title="Cycle theme"
            aria-label="Theme"
          ><Icon name="palette" size={15} /><span class="sr-only">Theme</span></button>
          <button
            type="button"
            onclick={() => (onboardingOpen = true)}
            class="inline-flex h-9 items-center justify-center rounded-lg border border-white/10 bg-white/[0.03] px-2.5 text-neutral-400 transition-colors hover:border-sky-500/50 hover:text-sky-200"
            title="Open the getting-started guide"
            aria-label="Guide"
          ><Icon name="bulb" size={15} /><span class="sr-only md:not-sr-only md:ml-1.5">Guide</span></button>
          <button
            type="button"
            data-testid="needs-you"
            onclick={() => (inboxOpen = true)}
            class="relative inline-flex h-9 items-center justify-center rounded-lg border border-amber-400/25 bg-amber-400/10 px-2.5 text-[length:var(--vf-text-xs)] text-amber-100 transition-colors hover:border-amber-400/50 hover:bg-amber-400/15"
            title="Pending gates"
          >
            <Icon name="check" size={14} class="mr-1.5" /><span class="sr-only md:not-sr-only">{t(locale, "needs_you")}</span>
            {#if pendingHilt.length}<span class="ml-1.5 rounded-full bg-amber-400/20 px-1.5 py-0.5 font-mono text-[length:var(--vf-text-2xs)] text-amber-100">{pendingHilt.length}</span>{/if}
          </button>
          <button
            type="button"
            onclick={() => (activityOpen = true)}
            class="relative inline-flex h-9 items-center justify-center rounded-lg border border-white/10 bg-white/[0.03] px-2.5 text-[length:var(--vf-text-xs)] text-neutral-400 transition-colors hover:border-sky-500/50 hover:text-sky-200"
            title="Activity drawer (U)"
          >
            <Icon name="activity" size={14} class="mr-1.5" /><span class="sr-only md:not-sr-only">{t(locale, "activity")}</span>
            {#if runningJobs.length}
              <span class={`ml-1.5 rounded-full bg-sky-500/20 px-1.5 py-0.5 font-mono text-[length:var(--vf-text-2xs)] text-sky-200 ${hasRunningJob ? "animate-pulse" : ""}`}>{runningJobs.length}</span>
            {/if}
          </button>
          <button
            type="button"
            onclick={() => (noticesOpen = true)}
            class="relative inline-flex h-9 items-center justify-center rounded-lg border border-white/10 bg-white/[0.03] px-2.5 text-[length:var(--vf-text-xs)] text-neutral-400 transition-colors hover:border-sky-500/50 hover:text-sky-200"
            title="Notification center (N)"
          >
            <Icon name="info" size={14} class="mr-1.5" /><span class="sr-only md:not-sr-only">{t(locale, "notifications")}</span>
            {#if counts.errors + counts.warnings + attentionJobs.length}
              <span class={`ml-1.5 rounded-full px-1.5 py-0.5 font-mono text-[length:var(--vf-text-2xs)] ${counts.errors ? "bg-rose-500/20 text-rose-200" : "bg-amber-400/20 text-amber-200"}`}>{counts.errors + counts.warnings + attentionJobs.length}</span>
            {/if}
          </button>
          <button
            type="button"
            onclick={() => (paletteOpen = true)}
            class="hidden h-9 items-center justify-center rounded-lg border border-white/10 bg-white/[0.03] px-2.5 font-mono text-[length:var(--vf-text-xs)] text-neutral-400 transition-colors hover:border-sky-500/50 hover:text-sky-200 sm:inline-flex"
            title="Command palette (Ctrl/Cmd + K)"
          >⌘K</button>
          <button
            type="button"
            onclick={() => (shortcutsOpen = true)}
            class="hidden h-9 items-center justify-center rounded-lg border border-white/10 bg-white/[0.03] px-2.5 text-[length:var(--vf-text-xs)] text-neutral-400 transition-colors hover:border-sky-500/50 hover:text-sky-200 sm:inline-flex"
            aria-label={t(locale, "shortcuts")}
            title="Keyboard shortcuts (?)"
          >?</button>
          {#if serviceStopped}
            <span class="rounded-lg border border-amber-400/20 bg-amber-400/10 px-2.5 py-1 text-[length:var(--vf-text-2xs)] text-amber-200">Service stopped · close this tab</span>
          {:else}
            <button type="button" onclick={() => void restartLocalService()} disabled={Boolean(serviceBusy)} class="hidden h-9 items-center rounded-lg border border-white/10 bg-white/[0.03] px-2.5 text-[length:var(--vf-text-2xs)] text-neutral-400 transition-colors hover:border-sky-500/50 hover:text-sky-200 disabled:opacity-40 lg:inline-flex">
              {serviceBusy === "restart" ? "Restarting…" : "Restart service"}
            </button>
            <button type="button" onclick={() => void stopLocalService()} disabled={Boolean(serviceBusy)} class="hidden h-9 items-center rounded-lg border border-rose-500/20 bg-rose-500/[0.04] px-2.5 text-[length:var(--vf-text-2xs)] text-rose-300 transition-colors hover:border-rose-400/40 hover:bg-rose-500/10 disabled:opacity-40 lg:inline-flex">
              {serviceBusy === "stop" ? "Stopping…" : "Stop service"}
            </button>
          {/if}
        </div>
      </header>

      {#if runningJobs.length || attentionJobs.length}
        <div class="rounded-xl border border-sky-500/20 bg-sky-950/20 px-3 py-2 text-[length:var(--vf-text-xs)]">
          <div class="flex flex-wrap items-center justify-between gap-2">
            <p class="text-sky-100/80">
              {runningJobs.length} {t(locale, "running")}
              {#if attentionJobs.length}· {attentionJobs.length} {t(locale, "needs_you")}{/if}
            </p>
            <button type="button" onclick={() => selectTab("jobs")} class="rounded-lg border border-sky-400/20 bg-sky-400/10 px-2.5 py-1 text-sky-100 transition-colors hover:bg-sky-400/15">
              {t(locale, "open_runs")}
            </button>
          </div>
          {#if runningJobs[0]}
            <div class="mt-2 flex items-center gap-2">
              <Progress value={runningJobs[0].progress} label={runningJobs[0].message || runningJobs[0].stage} />
              <span class="shrink-0 font-mono text-[length:var(--vf-text-2xs)] text-sky-200/70">{runningJobs[0].progress}%</span>
            </div>
          {/if}
        </div>
      {/if}

      <p class="sr-only" aria-live="polite">{t(locale, activeArea)} · {t(locale, activeTab)}</p>

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
      <div
        class="relative overflow-hidden rounded-2xl border border-sky-400/20 bg-sky-950/20 px-4 py-4 text-xs text-sky-100"
        role="status"
        data-testid="startup-card"
      >
        <div class="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-sky-400/60 to-transparent"></div>
        <div class="flex flex-wrap items-center justify-between gap-4">
          <div class="flex items-start gap-3">
            <div class="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-sky-400/20 bg-sky-400/10">
              <Logo size={26} />
              {#if connecting}
                <span class="absolute -right-1 -top-1 h-2.5 w-2.5 animate-ping rounded-full bg-sky-400/70"></span>
              {/if}
            </div>
            <div>
              <p class="font-medium text-sky-50">
                {connecting ? "Starting the local studio…" : "Could not reach the local service."}
              </p>
              <p class="mt-1 max-w-xl text-sky-200/70">
                {connecting
                  ? "Unpacking the portable build, checking FFmpeg, and opening the local API. Everything stays on this machine."
                  : systemError || "Start VideoFlow again or run videoflow restart."}
              </p>
              {#if connecting}
                <div class="mt-3 flex flex-wrap gap-3 text-[10px] uppercase tracking-wide text-sky-200/50">
                  <span class="inline-flex items-center gap-1"><span class="h-1 w-1 rounded-full bg-sky-300/70"></span>unpack</span>
                  <span class="inline-flex items-center gap-1"><span class="h-1 w-1 rounded-full bg-sky-300/70"></span>ffmpeg</span>
                  <span class="inline-flex items-center gap-1"><span class="h-1 w-1 rounded-full bg-sky-300/70"></span>api</span>
                </div>
              {/if}
            </div>
          </div>
          <button type="button" onclick={() => void connectToService()} disabled={connecting} class="rounded-lg border border-sky-400/30 px-3 py-1.5 text-[11px] disabled:opacity-40">
            {connecting ? "Connecting…" : "Retry now"}
          </button>
        </div>
        {#if connecting}
          <div class="mt-4 h-1 overflow-hidden rounded-full bg-sky-400/10">
            <div class="h-full w-1/3 animate-[vf-slide_1.4s_ease-in-out_infinite] rounded-full bg-gradient-to-r from-sky-400/40 via-sky-300 to-sky-400/40"></div>
          </div>
        {/if}
      </div>
    {/if}

    {#if serviceStopped}
      <div class="rounded-2xl border border-amber-400/20 bg-amber-950/30 px-4 py-3 text-xs text-amber-200">
        <p class="font-medium">The local service is stopped.</p>
        <p class="mt-1 text-amber-200/70">Close this tab. To start again, reopen VideoFlow or run <span class="font-mono">videoflow restart</span> in a terminal.</p>
      </div>
    {/if}

    <div id="workspace-content" class="scroll-mt-24">
      {#if workspaceJobId}
        <RecipeWorkspace
          jobId={workspaceJobId}
          onback={() => selectTab("jobs")}
          onopenbuilder={(recipeId) => void editRecipe(recipeId)}
        />
      {:else if activeTab === "overview"}
        <ProduceHome
          onedit={(recipeId) => void editRecipe(recipeId)}
          onreview={(jobId) => (jobId ? openWorkspace(jobId) : selectTab("jobs"))}
          onstarted={(job) => openWorkspace(job.job_id)}
        />
      {:else if activeTab === "recipes"}
        <RecipesPanel />
      {:else if activeTab === "lamera"}
        <LameraWorkspace />
      {:else if activeTab === "media"}
        <AssetsPanel />
      {:else if activeTab === "timeline"}
        <TimelinePanel />
      {:else if activeTab === "jobs"}
        <JobsPanel
          onreview={(job) => (job.interaction ? openWorkspace(job.job_id) : selectTab("recipes"))}
          onopen={(job) => openWorkspace(job.job_id)}
          onopentimeline={() => selectTab("timeline")}
        />
      {:else if activeTab === "assistant"}
        <CopilotPanel />
      {:else if activeTab === "schedules"}
        <AutomationPanel />
      {:else if activeTab === "brand"}
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
      {:else if activeTab === "extensions"}
        <PluginsPanel />
      {:else if activeTab === "connect"}
        <IntegrationsPanel />
      {:else if activeTab === "settings"}
        <SettingsPanel />
      {/if}
    </div>

    <footer class="flex flex-wrap items-center justify-between gap-2 border-t border-white/5 pb-4 pt-4 text-[11px] text-neutral-500">
      <p class="inline-flex items-center gap-2">
        <span class="h-1.5 w-1.5 rounded-full bg-emerald-400/80" aria-hidden="true"></span>
        Local-first · nothing leaves this machine
      </p>
      <p class="text-neutral-600">Project state is the timeline source of truth · SQLite indexes jobs, assets, and batches</p>
    </footer>
    </div>
  </div>
</div>

<HitlInbox
  open={inboxOpen}
  items={pendingHilt}
  onclose={() => (inboxOpen = false)}
  onopen={(jobId) => {
    inboxOpen = false;
    openWorkspace(jobId);
  }}
  onrefresh={() => void refreshHilt()}
/>

<ActivityDrawer
  open={activityOpen}
  {jobs}
  onclose={() => (activityOpen = false)}
  onchanged={() => refreshJobs()}
  onopenjobs={() => {
    activityOpen = false;
    selectTab("jobs");
  }}
/>
<CommandPalette
  open={paletteOpen}
  {commands}
  recentIds={recentCommands}
  onrun={runCommand}
  onclose={() => (paletteOpen = false)}
/>
<ShortcutsModal open={shortcutsOpen} onclose={() => (shortcutsOpen = false)} />
<Modal
  open={onboardingOpen}
  title="Getting started"
  description="Set up the local studio, then run a first cut. Nothing leaves this machine."
  width="w-[min(1080px,96vw)]"
  onclose={() => (onboardingOpen = false)}
>
  <OnboardingCard
    force
    onnavigate={(tab) => {
      selectTab(isTabId(tab) ? tab : "recipes");
      onboardingOpen = false;
    }}
    ondismiss={() => (onboardingOpen = false)}
  />
</Modal>

<NotificationCenter
  open={noticesOpen}
  onclose={() => (noticesOpen = false)}
  onaction={onNoticeAction}
/>
