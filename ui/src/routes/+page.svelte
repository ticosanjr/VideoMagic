<script lang="ts">
  import { onMount, tick } from "svelte";
  import CapabilitiesPanel from "$lib/CapabilitiesPanel.svelte";
  import ErrorBanner from "$lib/ErrorBanner.svelte";
  import FormatsPanel from "$lib/FormatsPanel.svelte";
  import GpuPanel from "$lib/GpuPanel.svelte";
  import GpuStatusPill from "$lib/GpuStatusPill.svelte";
  import HelpPanel from "$lib/HelpPanel.svelte";
  import HitlInbox from "$lib/HitlInbox.svelte";
  import IntegrationsPanel from "$lib/IntegrationsPanel.svelte";
  import JobsPanel from "$lib/JobsPanel.svelte";
  import ModelsPanel from "$lib/ModelsPanel.svelte";
  import PluginsPanel from "$lib/PluginsPanel.svelte";
  import ServicesPanel from "$lib/ServicesPanel.svelte";
  import StylesPanel from "$lib/StylesPanel.svelte";
  import WorkspacePanel from "$lib/WorkspacePanel.svelte";
  import SettingsPanel from "$lib/SettingsPanel.svelte";
  import SetupHealth from "$lib/SetupHealth.svelte";
  import Icon from "$lib/ui/Icon.svelte";
  import Logo from "$lib/ui/Logo.svelte";
  import {
    errorMessage,
    getSettings,
    getSystem,
    listJobs,
    listPendingInteractions,
    saveSettings,
    type AppSettings,
    type HiltPending,
    type Job,
    type SystemInfo
  } from "$lib/api";
  import { t } from "$lib/i18n";
  import { i18n } from "$lib/i18n.svelte";
  import { translateTree } from "$lib/domI18n";
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
    resolveRoute,
    type AreaId,
    type TabId
  } from "$lib/navigation";

  const TAB_HINTS: Record<TabId, string> = {
    overview: "MCP server health, setup checks, and recent jobs",
    jobs: "Jobs started by MCP tools and their outputs",
    models: "Optional on-demand speech and vision models",
    providers: "AI provider configuration, tests, and fallbacks",
    services: "Inspect, stop, and restart local VideoFlow processes",
    extensions: "Local plugin packages and sandbox status",
    connect: "MCP and REST setup for OpenCode, Paperclip, and DeepSeek",
    workspace: "Choose the workspace folder and install the MCP automatically",
    styles: "Edit the Markdown style catalog used by presets and agents",
    formats: "Aspect ratios, caption presets, and Shorts safe zones",
    help: "MCP workflow, example prompts, resources, and worker troubleshooting",
    gpu: "Pair a Windows GPU worker and validate its capabilities",
    settings: "Local runtime, paths, models, speech, TTS, and quality"
  };

  let system = $state<SystemInfo | null>(null);
  let activeTab = $state<TabId>("overview");
  const activeArea = $derived(areaForTab(activeTab));
  const subTabs = $derived(areaTabs(activeArea));
  let connecting = $state(true);
  let systemError = $state("");
  let locale = $state("en");
  let allowExternal = $state(false);
  let allowedHosts = $state("");
  let jobs = $state<Job[]>([]);
  let pendingHilt = $state<HiltPending[]>([]);
  let inboxOpen = $state(false);
  let jobsTimer: ReturnType<typeof setInterval> | undefined;

  const recentJobs = $derived(jobs.slice(0, 6));
  const runningJobs = $derived(
    jobs.filter((job) => ["running", "queued"].includes(job.status))
  );

  async function connectToService() {
    connecting = true;
    systemError = "";
    for (let attempt = 0; attempt < 30; attempt += 1) {
      try {
        system = await getSystem();
        if (system.settings_error) systemError = system.settings_error;
        if (system.database_error) systemError = system.database_error;
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

  async function refreshJobs() {
    try {
      jobs = await listJobs();
    } catch {
      // Keep the last snapshot while the service restarts.
    }
  }

  async function refreshHilt() {
    try {
      pendingHilt = await listPendingInteractions();
    } catch {
      pendingHilt = [];
    }
  }

  function selectTab(tab: TabId) {
    activeTab = tab;
    history.replaceState(null, "", hashFor(tab));
    localStorage.setItem("videoflow.tab", tab);
  }

  function syncHash() {
    activeTab = resolveRoute(window.location.hash).tab;
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

  const THEMES: AppSettings["ui"]["theme"][] = ["dark", "light", "high-contrast", "system"];

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
    } catch {
      // Theme persistence is best effort.
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
    document.title = `VideoFlow — ${t(locale, activeArea)} · ${t(locale, activeTab)}`;
  });

  onMount(() => {
    if (!window.location.hash) {
      const saved = localStorage.getItem("videoflow.tab");
      try {
        if (saved) history.replaceState(null, "", `#${saved}`);
      } catch {
        // Ignore an invalid stored tab.
      }
    }
    syncHash();
    window.addEventListener("hashchange", syncHash);
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
      })
      .catch(() => {});
    return () => {
      window.removeEventListener("hashchange", syncHash);
      clearInterval(jobsTimer);
    };
  });
</script>

<svelte:head>
  <title>VideoFlow — MCP control panel</title>
  <meta name="description" content="Local MCP-first video pipeline control panel." />
</svelte:head>

<div class="min-h-screen bg-neutral-950">
  <div class="vf-backdrop pointer-events-none fixed inset-0 -z-10" aria-hidden="true">
    <div class="absolute -top-48 left-1/2 h-[40rem] w-[70rem] -translate-x-1/2 rounded-full bg-sky-500/[0.07] blur-[130px]"></div>
    <div class="absolute -bottom-64 right-[-12rem] h-[34rem] w-[34rem] rounded-full bg-indigo-500/[0.07] blur-[130px]"></div>
    <div class="vf-ambient absolute inset-0"></div>
  </div>
  <a href="#panel-content" class="sr-only focus:not-sr-only focus:fixed focus:left-3 focus:top-3 focus:z-[80] focus:rounded-lg focus:bg-sky-500 focus:px-3 focus:py-2 focus:text-sm focus:text-neutral-950">Skip to content</a>
  <div class="vf-shell mx-auto min-h-screen px-3 py-4 sm:px-5 lg:px-6">
    <aside class="rounded-2xl border border-neutral-800 bg-neutral-950/80 p-3 lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:overflow-y-auto lg:p-4">
      <div class="flex items-center gap-3 lg:flex-col lg:items-start">
        <Logo size={40} />
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <h1 class="text-[length:var(--vf-text-xl)] font-semibold tracking-tight text-white">VideoFlow</h1>
            <span class="rounded-full border border-sky-400/20 bg-sky-400/[0.06] px-2 py-0.5 text-[length:var(--vf-text-2xs)] font-medium uppercase tracking-[0.16em] text-sky-200/80">mcp</span>
          </div>
          <p class="mt-1 text-[length:var(--vf-text-xs)] leading-5 text-neutral-400">Local video pipeline controlled by MCP tools.</p>
        </div>
      </div>

      <nav class="mt-4" aria-label="Control panel">
        <div class="flex gap-1 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible lg:pb-0" role="tablist" aria-label="Areas">
          {#each AREAS as area}
            <button
              type="button"
              role="tab"
              aria-selected={activeArea === area.id}
              aria-label={t(locale, area.id)}
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
          <GpuStatusPill onopen={() => selectTab("gpu")} />
          <button
            type="button"
            onclick={() => void cycleTheme()}
            class="inline-flex h-9 items-center justify-center rounded-lg border border-white/10 bg-white/[0.03] px-2.5 text-neutral-400 transition-colors hover:border-sky-500/50 hover:text-sky-200"
            title="Cycle theme"
            aria-label="Theme"
          ><Icon name="palette" size={15} /><span class="sr-only">Theme</span></button>
          <button
            type="button"
            data-testid="needs-you"
            onclick={() => (inboxOpen = true)}
            class="relative inline-flex h-9 items-center justify-center rounded-lg border border-amber-400/25 bg-amber-400/10 px-2.5 text-[length:var(--vf-text-xs)] text-amber-100 transition-colors hover:border-amber-400/50 hover:bg-amber-400/15"
            title="Pending MCP approvals"
          >
            <Icon name="check" size={14} class="mr-1.5" /><span class="sr-only md:not-sr-only">Needs you</span>
            {#if pendingHilt.length}<span class="ml-1.5 rounded-full bg-amber-400/20 px-1.5 py-0.5 font-mono text-[length:var(--vf-text-2xs)] text-amber-100">{pendingHilt.length}</span>{/if}
          </button>
        </div>
      </header>

      <ErrorBanner
        message={systemError}
        title="The local service reported a problem"
        onDismiss={() => (systemError = "")}
        testId="global-error-banner"
      />

      {#if !system && !connecting}
        <div class="rounded-2xl border border-sky-400/20 bg-sky-950/20 px-4 py-4 text-xs text-sky-100" role="status">
          <p class="font-medium">Could not reach the local service.</p>
          <p class="mt-1 text-sky-200/70">{systemError || "Start VideoFlow again or run videoflow restart."}</p>
        </div>
      {/if}

      <div id="panel-content" class="scroll-mt-24">
        {#if activeTab === "overview"}
          <div class="space-y-4">
            <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-5">
              <p class="vf-label text-sky-300/80">MCP</p>
              <h2 class="mt-1 text-[length:var(--vf-text-2xl)] font-semibold tracking-tight text-white">Local pipeline, agent-controlled</h2>
              <p class="mt-2 max-w-3xl text-[length:var(--vf-text-sm)] leading-6 text-neutral-400">
                VideoFlow exposes its production surface through MCP. Use OpenCode, Paperclip, or any MCP client to create projects, run steps, inspect jobs, and export masters. This panel only configures and observes the local service.
              </p>
              <div class="mt-4 grid gap-3 sm:grid-cols-3">
                <div class="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2">
                  <p class="vf-label">Transport</p>
                  <p class="mt-1 font-mono text-[length:var(--vf-text-xs)] text-neutral-200">stdio · /mcp/</p>
                </div>
                <div class="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2">
                  <p class="vf-label">Running</p>
                  <p class="mt-1 text-[length:var(--vf-text-sm)] text-neutral-100">{runningJobs.length} jobs · {pendingHilt.length} approvals</p>
                </div>
                <div class="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2">
                  <p class="vf-label">Server</p>
                  <p class="mt-1 text-[length:var(--vf-text-sm)] text-neutral-100">{system?.version ?? "offline"}</p>
                </div>
              </div>
            </section>

            <SetupHealth />

            <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
              <div class="flex items-end justify-between gap-3">
                <div>
                  <p class="vf-label">Recent jobs</p>
                  <h3 class="mt-1 text-[length:var(--vf-text-lg)] font-semibold text-neutral-100">MCP activity</h3>
                </div>
                <button type="button" onclick={() => selectTab("jobs")} class="rounded-lg border border-white/10 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-neutral-300 hover:border-sky-500/40">Open jobs</button>
              </div>
              {#if recentJobs.length === 0}
                <p class="mt-4 text-[length:var(--vf-text-sm)] text-neutral-500">No jobs yet. Start one from your MCP client.</p>
              {:else}
                <div class="mt-3 overflow-x-auto">
                  <table class="w-full text-left text-[length:var(--vf-text-xs)]">
                    <thead class="text-neutral-500">
                      <tr><th class="py-1 pr-4">Job</th><th class="py-1 pr-4">Status</th><th class="py-1">Stage</th></tr>
                    </thead>
                    <tbody>
                      {#each recentJobs as job (job.job_id)}
                        <tr class="border-t border-white/5 text-neutral-300">
                          <td class="py-2 pr-4 font-mono">{job.job_id.slice(0, 10)}</td>
                          <td class="py-2 pr-4">{job.status}</td>
                          <td class="py-2">{job.stage || job.message || "—"}</td>
                        </tr>
                      {/each}
                    </tbody>
                  </table>
                </div>
              {/if}
            </section>
          </div>
        {:else if activeTab === "jobs"}
          <JobsPanel
            onreview={() => (inboxOpen = true)}
            onopen={() => void refreshJobs()}
          />
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
        {:else if activeTab === "workspace"}
          <WorkspacePanel />
        {:else if activeTab === "connect"}
          <IntegrationsPanel />
        {:else if activeTab === "styles"}
          <StylesPanel />
        {:else if activeTab === "formats"}
          <FormatsPanel />
        {:else if activeTab === "help"}
          <HelpPanel />
        {:else if activeTab === "gpu"}
          <GpuPanel />
        {:else if activeTab === "settings"}
          <SettingsPanel />
        {/if}
      </div>

      <footer class="flex flex-wrap items-center justify-between gap-2 border-t border-white/5 pb-4 pt-4 text-[11px] text-neutral-500">
        <p>Local-first · MCP is the production interface</p>
        <p class="text-neutral-600">Project state is the timeline source of truth</p>
      </footer>
    </div>
  </div>
</div>

<HitlInbox
  open={inboxOpen}
  items={pendingHilt}
  onclose={() => (inboxOpen = false)}
  onopen={() => {
    inboxOpen = false;
    selectTab("jobs");
  }}
  onrefresh={() => void refreshHilt()}
/>
