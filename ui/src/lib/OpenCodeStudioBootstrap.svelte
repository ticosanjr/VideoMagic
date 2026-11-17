<script lang="ts">
  import { onMount } from "svelte";
  import {
    bootstrapOpenCode,
    errorMessage,
    listStyles,
    type OpenCodeBootstrapResult,
    type StyleSummary
  } from "$lib/api";
  import {
    bootstrapHighlights,
    bootstrapPayload,
    canBootstrap,
    defaultStudioForm,
    MCP_PROFILES
  } from "$lib/opencodeStudio";
  import PathPicker from "$lib/PathPicker.svelte";
  import HelpTip from "$lib/HelpTip.svelte";

  let form = $state(defaultStudioForm());
  let styles = $state<StyleSummary[]>([]);
  let stylesError = $state("");
  let picker = $state(false);
  let busy = $state(false);
  let error = $state("");
  let result = $state<OpenCodeBootstrapResult | null>(null);
  let copied = $state("");

  onMount(() => {
    void loadStyles();
  });

  async function loadStyles() {
    try {
      styles = await listStyles();
      stylesError = "";
    } catch (reason) {
      stylesError = errorMessage(reason);
    }
  }

  async function bootstrap() {
    busy = true;
    error = "";
    result = null;
    try {
      result = await bootstrapOpenCode(bootstrapPayload(form));
      await loadStyles();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  async function copyCommand() {
    if (!result?.launch_command) return;
    try {
      await navigator.clipboard.writeText(result.launch_command);
      copied = "Copied";
      setTimeout(() => (copied = ""), 1500);
    } catch {
      copied = "Copy failed";
    }
  }
</script>

<section
  class="space-y-3 rounded-2xl border border-emerald-500/25 bg-emerald-500/5 p-4"
  data-testid="opencode-studio-card"
>
  <header>
    <div class="flex items-center gap-1.5">
      <h3 class="text-sm font-semibold text-emerald-100">OpenCode Studio Bootstrap</h3>
      <HelpTip
        label="OpenCode Studio"
        body="Create an OpenCode workspace with VideoFlow MCP servers, AGENTS.md, skills, slash commands, and the current style catalog."
        doc="docs/opencode.md"
      />
    </div>
    <p class="mt-1 text-[11px] leading-relaxed text-neutral-300">
      One click prepares the folder, installs the MCP profile, copies every
      <span class="font-mono">presets/*.md</span> style, and prints the launch command.
    </p>
  </header>

  <div class="grid gap-3 lg:grid-cols-2">
    <label class="block text-[11px] text-neutral-300">
      <span class="mb-1 block font-medium text-neutral-200">Workspace folder</span>
      <div class="flex gap-2">
        <input
          class="min-w-0 flex-1 rounded-lg border border-neutral-700 bg-black/40 px-2 py-1.5 font-mono text-[11px] text-neutral-100 outline-none focus:border-emerald-400/60"
          bind:value={form.targetDir}
          placeholder="/home/you/Videos/canal-paula"
          data-testid="opencode-target"
        />
        <button
          type="button"
          class="rounded-lg border border-white/10 px-2 py-1 text-[10px] text-neutral-300 hover:text-emerald-200"
          onclick={() => (picker = true)}
        >Browse…</button>
      </div>
    </label>

    <label class="block text-[11px] text-neutral-300">
      <span class="mb-1 block font-medium text-neutral-200">MCP profile</span>
      <select
        class="w-full rounded-lg border border-neutral-700 bg-black/40 px-2 py-1.5 text-[11px] text-neutral-100 outline-none focus:border-emerald-400/60"
        bind:value={form.profile}
        data-testid="opencode-profile"
      >
        {#each MCP_PROFILES as profile (profile.id)}
          <option value={profile.id}>{profile.label}</option>
        {/each}
      </select>
    </label>
  </div>

  <div class="rounded-xl border border-neutral-800 bg-black/20 p-2.5">
    <p class="text-[10px] font-medium uppercase tracking-wide text-neutral-400">
      Styles that will be copied
    </p>
    {#if stylesError}
      <p class="mt-1 text-[10px] text-rose-300">{stylesError}</p>
    {:else if styles.length}
      <div class="mt-1.5 flex flex-wrap gap-1">
        {#each styles.slice(0, 10) as style (style.style_id)}
          <span
            class="rounded-full border border-emerald-500/20 bg-emerald-500/10 px-2 py-0.5 text-[10px] text-emerald-100"
            title={style.summary}
          >{style.style_id}</span>
        {/each}
        {#if styles.length > 10}
          <span class="text-[10px] text-neutral-500">+{styles.length - 10}</span>
        {/if}
      </div>
    {:else}
      <p class="mt-1 text-[10px] text-neutral-500">No styles loaded yet.</p>
    {/if}
  </div>

  <div class="flex flex-wrap gap-x-4 gap-y-2 text-[11px] text-neutral-300">
    <label class="flex items-center gap-1.5">
      <input type="checkbox" bind:checked={form.globalConfig} />
      Register global config
    </label>
    <label class="flex items-center gap-1.5">
      <input type="checkbox" bind:checked={form.overwrite} />
      Overwrite existing files
    </label>
    <label class="flex items-center gap-1.5">
      <input type="checkbox" bind:checked={form.withSample} />
      Include 10s sample project
    </label>
    <label class="flex items-center gap-1.5">
      <input type="checkbox" bind:checked={form.registerRoot} />
      Allow this folder
    </label>
    <label class="flex items-center gap-1.5">
      <input type="checkbox" bind:checked={form.prompts} />
      Register prompts
    </label>
  </div>

  <div class="flex flex-wrap items-center gap-2">
    <button
      type="button"
      class="rounded-lg border border-emerald-400/30 bg-emerald-500/15 px-3 py-1.5 text-[11px] font-medium text-emerald-100 hover:bg-emerald-500/25 disabled:opacity-40"
      disabled={busy || !canBootstrap(form)}
      onclick={() => void bootstrap()}
      data-testid="opencode-bootstrap"
    >{busy ? "Preparing…" : "Prepare folder & install MCP"}</button>
    {#if result}
      <span class="text-[10px] text-emerald-200">{result.status === "ok" ? "Ready" : "Ready with warnings"}</span>
    {/if}
  </div>

  {#if error}
    <p class="rounded-lg border border-rose-500/30 bg-rose-500/10 p-2 text-[11px] text-rose-200" data-testid="opencode-error">
      {error}
    </p>
  {/if}

  {#if result}
    <div class="space-y-2 rounded-xl border border-emerald-500/20 bg-black/30 p-3" data-testid="opencode-result">
      <ul class="space-y-0.5 text-[11px] text-neutral-200">
        {#each bootstrapHighlights(result) as line}
          <li>• {line}</li>
        {/each}
      </ul>
      {#if result.warnings.length}
        <ul class="space-y-0.5 text-[10px] text-amber-200">
          {#each result.warnings as warning}
            <li>! {warning}</li>
          {/each}
        </ul>
      {/if}
      <div class="flex items-center gap-2">
        <code class="min-w-0 flex-1 truncate rounded-lg border border-neutral-800 bg-black/60 px-2 py-1 text-[10px] text-emerald-200" data-testid="opencode-launch">
          {result.launch_command}
        </code>
        <button
          type="button"
          class="rounded-lg border border-white/10 px-2 py-0.5 text-[10px] text-neutral-300 hover:text-emerald-200"
          onclick={() => void copyCommand()}
        >{copied || "Copy command"}</button>
      </div>
      <details class="text-[10px] text-neutral-400">
        <summary class="cursor-pointer">Files created ({result.created_files.length})</summary>
        <ul class="mt-1 max-h-40 space-y-0.5 overflow-auto font-mono">
          {#each result.created_files as file}
            <li>{file}</li>
          {/each}
        </ul>
      </details>
    </div>
  {/if}
</section>

{#if picker}
  <PathPicker
    open={true}
    mode="directory"
    title="Choose the OpenCode workspace folder"
    initialPath={form.targetDir}
    onclose={() => (picker = false)}
    onselect={(path) => {
      form.targetDir = path;
      picker = false;
    }}
  />
{/if}
