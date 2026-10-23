<script lang="ts">
  import { onMount } from "svelte";
  import AssetsPanel from "$lib/AssetsPanel.svelte";
  import CapabilitiesPanel from "$lib/CapabilitiesPanel.svelte";
  import ErrorBanner from "$lib/ErrorBanner.svelte";
  import ModelsPanel from "$lib/ModelsPanel.svelte";
  import RecipesPanel from "$lib/RecipesPanel.svelte";
  import ServicesPanel from "$lib/ServicesPanel.svelte";
  import TimelinePanel from "$lib/TimelinePanel.svelte";
  import { errorMessage, getSystem, restartService, stopService, type SystemInfo } from "$lib/api";
  import { UI_VERSION } from "$lib/version";
  import "../app.css";

  type Tab = "recipes" | "assets" | "timeline" | "models" | "services" | "providers";

  const TABS: { id: Tab; label: string; hint: string }[] = [
    { id: "recipes", label: "Recipes", hint: "Visual recipe builder and runner" },
    { id: "assets", label: "Assets", hint: "Local media, audio, images, fonts, tags, and licenses" },
    { id: "timeline", label: "Timeline", hint: "Canvas timeline with preview, trim, split, and undo" },
    { id: "models", label: "Models", hint: "Optional on-demand speech and vision models" },
    { id: "services", label: "Services", hint: "Inspect, stop, and restart local VideoFlow processes" },
    { id: "providers", label: "Providers", hint: "Persistent provider configuration and fallbacks" }
  ];

  let system = $state<SystemInfo | null>(null);
  let activeTab = $state<Tab>("recipes");
  let connecting = $state(true);
  let systemError = $state("");
  let serviceStopped = $state(false);
  let serviceBusy = $state<"" | "restart" | "stop">("");
  let serviceError = $state("");
  let toast = $state<{ kind: "success" | "error"; message: string } | null>(null);
  let toastTimer: ReturnType<typeof setTimeout> | undefined;
  let allowExternal = $state(false);
  let allowedHosts = $state("");

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

  function notify(kind: "success" | "error", message: string) {
    clearTimeout(toastTimer);
    toast = { kind, message };
    toastTimer = setTimeout(() => (toast = null), 3200);
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

  onMount(() => {
    const hash = window.location.hash.replace("#", "") as Tab;
    if (TABS.some((tab) => tab.id === hash)) activeTab = hash;
    void connectToService();
    return () => {
      clearTimeout(toastTimer);
    };
  });
</script>

<svelte:head>
  <title>VideoFlow — Recipe studio</title>
  <meta name="description" content="Local, non-destructive video pre-edit pipeline." />
</svelte:head>

<div class="min-h-screen bg-neutral-950">
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
          <p class="mt-0.5 text-xs text-neutral-500">Editable rough cuts and repeatable content recipes</p>
        </div>
      </div>
      <div class="flex flex-wrap items-center gap-2 text-xs">
        <span class="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 font-mono text-[11px] text-neutral-400" title="Server version">server {system?.version ?? (connecting ? "connecting…" : "offline")}</span>
        <span class="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 font-mono text-[11px] text-neutral-500" title="UI bundle version">ui {UI_VERSION}</span>
        <span class="rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-[11px] text-neutral-500">FFmpeg {system?.ffmpeg ? "ready" : connecting ? "checking…" : "missing"}</span>
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

    <nav class="sticky top-0 z-30 -mx-1 overflow-x-auto rounded-2xl border border-neutral-800 bg-neutral-950/95 p-1 shadow-lg shadow-black/30 backdrop-blur" aria-label="Workspace areas">
      <div class="flex min-w-max gap-1" role="tablist" aria-label="Workspace areas">
        {#each TABS as tab}
          <button
            type="button"
            role="tab"
            aria-selected={activeTab === tab.id}
            title={tab.hint}
            onclick={() => selectTab(tab.id)}
            class={`rounded-xl px-3 py-2 text-xs font-medium transition ${activeTab === tab.id ? "bg-sky-500/15 text-sky-200 ring-1 ring-inset ring-sky-400/20" : "text-neutral-400 hover:bg-white/[0.04] hover:text-neutral-200"}`}
          >
            {tab.label}
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

    {#if toast}
      <div class={`fixed right-4 top-4 z-[60] flex max-w-sm items-start gap-2 rounded-2xl border px-4 py-3 text-sm shadow-2xl ${toast.kind === "error" ? "border-rose-500/30 bg-rose-950 text-rose-200" : "border-emerald-500/30 bg-emerald-950 text-emerald-200"}`} role="status" aria-live="polite">
        <span class={`mt-0.5 h-2 w-2 shrink-0 rounded-full ${toast.kind === "error" ? "bg-rose-400" : "bg-emerald-400"}`}></span>
        <span>{toast.message}</span>
      </div>
    {/if}

    <div id="workspace-content" class="scroll-mt-24">
      {#if activeTab === "recipes"}
        <RecipesPanel />
      {:else if activeTab === "assets"}
        <AssetsPanel />
      {:else if activeTab === "timeline"}
        <TimelinePanel />
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
      {/if}
    </div>

    <footer class="pb-4 text-xs text-neutral-500">
      <p>Local only. The server binds to 127.0.0.1. JSON project state is the single source of truth.</p>
    </footer>
  </div>
</div>
