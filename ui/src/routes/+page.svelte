<script lang="ts">
  import { onMount, tick } from "svelte";
  import CurationBoard from "$lib/CurationBoard.svelte";
  import ErrorBanner from "$lib/ErrorBanner.svelte";
  import GpuStatusPill from "$lib/GpuStatusPill.svelte";
  import HitlInbox from "$lib/HitlInbox.svelte";
  import JobsPanel from "$lib/JobsPanel.svelte";
  import SetupPanel from "$lib/SetupPanel.svelte";
  import Icon from "$lib/ui/Icon.svelte";
  import Logo from "$lib/ui/Logo.svelte";
  import {
    errorMessage,
    getSettings,
    getSystem,
    listPendingInteractions,
    saveSettings,
    type AppSettings,
    type HiltPending,
    type SystemInfo
  } from "$lib/api";
  import { t } from "$lib/i18n";
  import { i18n } from "$lib/i18n.svelte";
  import { translateTree } from "$lib/domI18n";
  import { UI_VERSION } from "$lib/version";
  import "../app.css";

  import {
    TABS,
    TAB_ICONS,
    hashFor,
    resolveRoute,
    type TabId
  } from "$lib/navigation";

  const TAB_HINTS: Record<TabId, string> = {
    curation: "Review style, music, SFX, B-roll, and image candidates",
    jobs: "Queued, running, paused, and finished jobs with human approvals",
    setup: "Windows GPU, styles, workspace, and OpenCode bootstrap"
  };

  let system = $state<SystemInfo | null>(null);
  let activeTab = $state<TabId>("curation");
  let connecting = $state(true);
  let systemError = $state("");
  let locale = $state("en");
  let pendingHilt = $state<HiltPending[]>([]);
  let inboxOpen = $state(false);
  let setupNonce = $state(0);
  let hitlTimer: ReturnType<typeof setInterval> | undefined;

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

  async function refreshHilt() {
    try {
      pendingHilt = await listPendingInteractions();
    } catch {
      pendingHilt = [];
    }
  }

  function openGpuSetup() {
    setupNonce += 1;
    selectTab("setup");
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
    document.title = `VideoFlow — ${t(locale, activeTab)}`;
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
    void refreshHilt();
    hitlTimer = setInterval(() => {
      if (!document.hidden) void refreshHilt();
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
      clearInterval(hitlTimer);
    };
  });
</script>

<svelte:head>
  <title>VideoFlow — curation, jobs, and setup</title>
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
        <div class="flex gap-1 overflow-x-auto pb-1 lg:flex-col lg:overflow-visible lg:pb-0" role="tablist" aria-label="Screens">
          {#each TABS as tab (tab.id)}
            <button
              type="button"
              role="tab"
              aria-selected={activeTab === tab.id}
              aria-label={t(locale, tab.id)}
              title={TAB_HINTS[tab.id]}
              onclick={() => selectTab(tab.id)}
              onkeydown={(event) => onTabKey(event, TABS.map((item) => item.id), tab.id, (id) => selectTab(id as TabId))}
              class={`flex min-h-10 shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-left text-[length:var(--vf-text-sm)] font-medium transition-colors lg:w-full ${activeTab === tab.id ? "bg-sky-500/15 text-sky-100 ring-1 ring-inset ring-sky-400/20" : "text-neutral-400 hover:bg-white/[0.04] hover:text-neutral-100"}`}
            >
              <Icon name={TAB_ICONS[tab.id]} size={15} class={activeTab === tab.id ? "text-sky-300" : ""} />
              <span class="whitespace-nowrap">{t(locale, tab.id)}</span>
            </button>
          {/each}
        </div>
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
            <span>VideoFlow</span>
            <span aria-hidden="true">/</span>
            <span class="text-neutral-300">{t(locale, activeTab)}</span>
          </div>
          <p class="mt-1 truncate text-[length:var(--vf-text-xl)] font-semibold tracking-tight text-white">{t(locale, activeTab)}</p>
          <p class="mt-0.5 hidden max-w-2xl truncate text-[length:var(--vf-text-xs)] text-neutral-500 sm:block">{TAB_HINTS[activeTab]}</p>
        </div>
        <div class="flex flex-wrap items-center justify-end gap-1.5">
          <GpuStatusPill onopen={openGpuSetup} />
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
        {#if activeTab === "curation"}
          <CurationBoard />
        {:else if activeTab === "jobs"}
          <JobsPanel
            onreview={() => (inboxOpen = true)}
            onopen={() => void refreshHilt()}
          />
        {:else}
          {#key setupNonce}
            <SetupPanel />
          {/key}
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
