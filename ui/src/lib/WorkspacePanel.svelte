<script lang="ts">
  import { onMount } from "svelte";
  import Modal from "$lib/ui/Modal.svelte";
  import {
    bootstrapOpenCode,
    chooseFolder,
    cleanupGlobalMcp,
    getMcpHealth,
    getSystem,
    listFolders,
    type FolderListing,
    type McpHealth,
    type OpenCodeBootstrapResult,
    type SystemInfo
  } from "$lib/api";

  let system = $state<SystemInfo | null>(null);
  let targetDir = $state("");
  let profile = $state<"opencode" | "core" | "decupagem" | "broll" | "audio" | "vision" | "full">("opencode");
  let includeSample = $state(false);
  let prompts = $state(false);
  let overwrite = $state(false);
  let busy = $state(false);
  let error = $state("");
  let result = $state<OpenCodeBootstrapResult | null>(null);
  let mcpHealth = $state<McpHealth | null>(null);
  let cleanupNotice = $state("");
  let browserOpen = $state(false);
  let browserBusy = $state(false);
  let browsePath = $state("");
  let listing = $state<FolderListing | null>(null);

  async function refreshHealth() {
    try {
      mcpHealth = await getMcpHealth();
    } catch {
      mcpHealth = null;
    }
  }

  onMount(() => {
    void getSystem().then((value) => {
      system = value;
      if (!targetDir && value.allowed_roots?.length) targetDir = value.allowed_roots[0];
    }).catch(() => null);
    void refreshHealth();
  });

  async function cleanupGlobal() {
    busy = true;
    try {
      const response = await cleanupGlobalMcp();
      cleanupNotice = response.removed.length
        ? `Removed from global config: ${response.removed.join(", ")}.`
        : "No VideoFlow servers in the global config.";
      void refreshHealth();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    } finally {
      busy = false;
    }
  }

  async function browse() {
    error = "";
    browserOpen = true;
    await openBrowser(targetDir.trim());
  }

  async function openBrowser(path: string) {
    browserBusy = true;
    try {
      listing = await listFolders(path);
      browsePath = listing.path;
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    } finally {
      browserBusy = false;
    }
  }

  function useBrowsedFolder() {
    if (listing?.path) targetDir = listing.path;
    browserOpen = false;
  }

  async function systemFolderDialog() {
    try {
      const picked = await chooseFolder(targetDir);
      if (picked.ok && picked.path) {
        targetDir = picked.path;
        browserOpen = false;
      }
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    }
  }

  function browseUp() {
    if (listing?.parent) void openBrowser(listing.parent);
  }

  async function install() {
    busy = true;
    error = "";
    result = null;
    try {
      result = await bootstrapOpenCode({
        target_dir: targetDir,
        mcp_profile: profile,
        register_global_opencode: false,
        cleanup_global_opencode: false,
        include_sample_project: includeSample,
        prompts,
        overwrite,
        register_root: true
      });
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    } finally {
      busy = false;
    }
  }
</script>

<section class="space-y-4" data-testid="workspace-panel">
  <div class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4">
    <p class="vf-label text-sky-300/80">Setup · Workspace</p>
    <h2 class="mt-1 text-[length:var(--vf-text-xl)] font-semibold text-white">Folder and MCP in one step</h2>
    <p class="mt-1 max-w-3xl text-[length:var(--vf-text-xs)] text-neutral-400">
      Choose where VideoFlow keeps projects, copy the styles and workflows, and install the
      VideoFlow MCP server into OpenCode. Existing config is backed up and merged.
    </p>
  </div>

  {#if error}
    <p class="rounded-lg border border-rose-400/20 bg-rose-950/30 px-3 py-2 text-[length:var(--vf-text-xs)] text-rose-200" role="alert">{error}</p>
  {/if}

  <div class="grid gap-4 xl:grid-cols-[1.4fr_1fr]">
    <article class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4">
      <h3 class="text-[length:var(--vf-text-sm)] font-semibold text-neutral-100">Workspace folder</h3>
      <label class="mt-3 block text-[11px] text-neutral-500" for="workspace-folder">Folder</label>
      <div class="mt-1 flex gap-2">
        <input id="workspace-folder" title="Folder that will hold projects, styles, workflows, and the OpenCode config" bind:value={targetDir} placeholder="/home/me/videoflow-workspace" class="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 font-mono text-[length:var(--vf-text-xs)] text-neutral-100" />
        <button type="button" onclick={() => void browse()} class="rounded-lg border border-white/10 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-neutral-200">Browse…</button>
      </div>
      <p class="mt-2 text-[11px] text-neutral-500">Allowed roots: {system?.allowed_roots?.join(", ") || "loading…"}</p>

      <div class="mt-4 grid gap-3 sm:grid-cols-2">
        <label class="text-[11px] text-neutral-500">MCP profile
          <select title="MCP servers installed into OpenCode" bind:value={profile} class="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 text-[length:var(--vf-text-xs)] text-neutral-100">
            <option value="opencode">opencode (core + fetch + audio + vision)</option>
            <option value="core">core only</option>
            <option value="decupagem">decupagem</option>
            <option value="broll">b-roll</option>
            <option value="audio">audio</option>
            <option value="vision">vision</option>
            <option value="full">full</option>
          </select>
        </label>
        <label class="flex items-center gap-2 text-[length:var(--vf-text-xs)] text-neutral-300">
          <input type="checkbox" bind:checked={includeSample} /> Create 10 s sample project
        </label>
        <label class="flex items-center gap-2 text-[length:var(--vf-text-xs)] text-neutral-300">
          <input type="checkbox" bind:checked={prompts} /> Include MCP prompts
        </label>
        <label class="flex items-center gap-2 text-[length:var(--vf-text-xs)] text-neutral-300">
          <input type="checkbox" bind:checked={overwrite} /> Overwrite workspace files
        </label>
      </div>
      <button type="button" title="Create the workspace, copy styles/workflows, and install the MCP server" disabled={busy || !targetDir.trim()} onclick={() => void install()} class="mt-4 rounded-lg border border-emerald-400/25 bg-emerald-500/10 px-4 py-2 text-[length:var(--vf-text-xs)] font-medium text-emerald-100 disabled:opacity-40">
        {busy ? "Preparing workspace…" : "Prepare workspace and install MCP"}
      </button>
      <button type="button" title="Remove only VideoFlow entries from the global OpenCode config" disabled={busy} onclick={() => void cleanupGlobal()} class="ml-2 mt-4 rounded-lg border border-rose-400/20 px-3 py-2 text-[length:var(--vf-text-xs)] text-rose-200 disabled:opacity-40">
        Remove global VideoFlow MCP
      </button>
      {#if cleanupNotice}<p class="mt-2 text-[11px] text-amber-200">{cleanupNotice}</p>{/if}
    </article>

    <article class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4">
      <h3 class="text-[length:var(--vf-text-sm)] font-semibold text-neutral-100">What gets installed</h3>
      <ul class="mt-3 space-y-1.5 text-[length:var(--vf-text-xs)] text-neutral-400">
        <li>OpenCode config with the selected MCP profile</li>
        <li>AGENTS.md with the VideoFlow protocol</li>
        <li>Styles and workflows copied to the workspace</li>
        <li>Allowed-root registration and project folder</li>
        <li>No global OpenCode changes by default</li>
      </ul>
      {#if mcpHealth}
        <div class="mt-3 rounded-lg border border-white/10 bg-black/20 p-3 text-[11px] text-neutral-400">
          <p class="font-medium text-neutral-200">MCP health</p>
          <p class="mt-1">Global config: {mcpHealth.global_path || "not found"}</p>
          <p>Global VideoFlow servers: {mcpHealth.global_videoflow_servers.join(", ") || "none"}</p>
          <p>Launcher: {mcpHealth.launcher_exists ? mcpHealth.launcher : "missing"}</p>
          <p>Worker URL seen by MCP: {mcpHealth.worker_url || "not connected"}</p>
          {#each mcpHealth.warnings as warning}<p class="mt-1 text-amber-200">{warning}</p>{/each}
        </div>
      {/if}
      {#if result}
        <div class="mt-4 rounded-lg border border-emerald-400/20 bg-emerald-950/20 p-3 text-[length:var(--vf-text-xs)] text-emerald-100">
          <p class="font-medium">Workspace ready: {result.target_dir}</p>
          <p class="mt-1 text-emerald-200/80">{result.created_files.length} file(s) created · {result.mcp_servers.length} MCP server(s)</p>
          {#if result.launch_command}
            <pre class="mt-2 overflow-x-auto rounded bg-black/40 p-2 font-mono text-[11px] text-neutral-300">{result.launch_command}</pre>
          {/if}
          {#if result.warnings.length}
            <ul class="mt-2 list-disc pl-4 text-amber-200">
              {#each result.warnings as warning}<li>{warning}</li>{/each}
            </ul>
          {/if}
        </div>
      {/if}
    </article>
  </div>
  <Modal
    open={browserOpen}
    title="Choose workspace folder"
    description="Browse folders, open a drive, or type an absolute path."
    onclose={() => (browserOpen = false)}
    testid="folder-browser"
  >
    <div class="space-y-3">
      <div class="flex gap-2">
        <input
          aria-label="Folder path"
          title="Folder path"
          bind:value={browsePath}
          class="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 font-mono text-[length:var(--vf-text-xs)] text-neutral-100"
          onkeydown={(event) => {
            if (event.key === "Enter") void openBrowser(browsePath);
          }}
        />
        <button
          type="button"
          disabled={browserBusy}
          onclick={() => void openBrowser(browsePath)}
          class="rounded-lg border border-white/10 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-neutral-200 disabled:opacity-40"
        >Go</button>
      </div>
      <div class="flex flex-wrap gap-2">
        <button
          type="button"
          disabled={!listing?.parent || browserBusy}
          onclick={browseUp}
          class="rounded-lg border border-white/10 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-neutral-200 disabled:opacity-40"
        >Up</button>
        {#each listing?.roots ?? [] as root}
          <button
            type="button"
            title={root}
            disabled={browserBusy}
            onclick={() => void openBrowser(root)}
            class="max-w-[18rem] truncate rounded-lg border border-white/10 px-3 py-1.5 font-mono text-[length:var(--vf-text-xs)] text-neutral-300 disabled:opacity-40"
          >{root}</button>
        {/each}
      </div>
      <p class="truncate font-mono text-[11px] text-neutral-400">{browserBusy ? "Loading…" : listing?.path ?? ""}</p>
      {#if listing?.directories?.length}
        <ul class="max-h-[45vh] divide-y divide-white/5 overflow-auto rounded-lg border border-white/10">
          {#each listing.directories as directory}
            <li>
              <button
                type="button"
                title={directory.path}
                onclick={() => void openBrowser(directory.path)}
                class="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-[length:var(--vf-text-xs)] text-neutral-200 hover:bg-white/5"
              >
                <span class="truncate">{directory.name}</span>
                <span class="text-neutral-600">›</span>
              </button>
            </li>
          {/each}
        </ul>
      {:else if !browserBusy}
        <p class="rounded-lg border border-white/10 px-3 py-2 text-[length:var(--vf-text-xs)] text-neutral-500">No subfolders</p>
      {/if}
      {#if listing?.truncated}
        <p class="text-[11px] text-amber-200">Showing the first 1000 folders.</p>
      {/if}
      <div class="flex flex-wrap justify-end gap-2 pt-2">
        <button
          type="button"
          onclick={() => void systemFolderDialog()}
          class="rounded-lg border border-white/10 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-neutral-200"
        >System dialog</button>
        <button
          type="button"
          disabled={!listing?.path}
          onclick={useBrowsedFolder}
          class="rounded-lg border border-emerald-400/25 bg-emerald-500/10 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-emerald-100 disabled:opacity-40"
        >Use this folder</button>
      </div>
    </div>
  </Modal>
</section>
