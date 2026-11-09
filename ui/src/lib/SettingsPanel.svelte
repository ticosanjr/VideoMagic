<script lang="ts">
  import { onMount } from "svelte";
  import ErrorBanner from "$lib/ErrorBanner.svelte";
  import FieldHint from "$lib/FieldHint.svelte";
  import HelpTip from "$lib/HelpTip.svelte";
  import {
    errorMessage,
    getSettings,
    resetSettings,
    saveSettings,
    type AppSettings
  } from "$lib/api";

  let settings = $state<AppSettings | null>(null);
  let env = $state<Record<string, string>>({});
  let restartRequired = $state<string[]>([]);
  let rootsText = $state("");
  let error = $state("");
  let status = $state("");
  let busy = $state(false);
  let query = $state("");

  function filterSections(value: string) {
    const needle = value.trim().toLowerCase();
    document.querySelectorAll<HTMLElement>("[data-settings-section]").forEach((section) => {
      section.hidden = Boolean(needle) && !(section.textContent ?? "").toLowerCase().includes(needle);
    });
  }

  async function load() {
    try {
      const payload = await getSettings();
      settings = payload.settings;
      env = payload.env;
      restartRequired = payload.restart_required;
      rootsText = (settings.paths?.allowed_roots ?? []).join(", ");
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  function setDefault(capability: string, value: string) {
    if (!settings) return;
    settings.models.defaults[capability] = value;
  }

  function addCapability(capability: string) {
    if (!settings || !capability.trim()) return;
    if (!(capability in settings.models.defaults)) {
      settings.models.defaults[capability] = "";
    }
  }

  async function save() {
    if (!settings) return;
    busy = true;
    error = "";
    status = "";
    try {
      settings.paths.allowed_roots = rootsText
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      settings = await saveSettings(settings);
      status = "Settings saved. Restart the service for marked changes.";
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  function exportSettings() {
    if (!settings) return;
    const blob = new Blob([JSON.stringify(settings, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "videoflow-settings.json";
    anchor.click();
    URL.revokeObjectURL(url);
  }

  async function importSettings(file: File | undefined) {
    if (!file) return;
    try {
      const parsed = JSON.parse(await file.text()) as AppSettings;
      settings = await saveSettings(parsed);
      rootsText = (settings.paths?.allowed_roots ?? []).join(", ");
      status = "Settings imported.";
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function reset() {
    if (!confirm("Reset every local setting to the defaults?")) return;
    busy = true;
    try {
      settings = await resetSettings();
      rootsText = (settings.paths?.allowed_roots ?? []).join(", ");
      status = "Settings reset to defaults.";
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  onMount(() => {
    void load();
  });
</script>

<div class="space-y-4" data-testid="settings-panel">
  <ErrorBanner message={error} onDismiss={() => (error = "")} testId="settings-error" />

  <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div>
        <h2 class="text-sm font-semibold text-white">Local settings</h2>
        <p class="mt-1 text-xs text-neutral-500">
          Persisted in <span class="font-mono">settings.json</span>. Environment variables marked below win over the file where applicable.
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <input
          type="search"
          bind:value={query}
          oninput={(event) => filterSections(event.currentTarget.value)}
          placeholder="Search settings…"
          aria-label="Search settings"
          class="w-44 rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-200"
        />
        <button type="button" onclick={() => void load()} disabled={busy} class="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300 disabled:opacity-40">Discard changes</button>
        <button type="button" onclick={exportSettings} class="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300">Export</button>
        <label class="cursor-pointer rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300">
          Import
          <input type="file" accept="application/json" class="hidden" onchange={(event) => void importSettings(event.currentTarget.files?.[0])} />
        </label>
        <button type="button" onclick={() => void reset()} disabled={busy} class="rounded-lg border border-rose-500/30 px-3 py-1.5 text-xs text-rose-300 disabled:opacity-40">Reset</button>
        <button type="button" onclick={() => void save()} disabled={busy || !settings} class="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-xs text-sky-200 disabled:opacity-40">{busy ? "Saving…" : "Save settings"}</button>
      </div>
    </div>
    {#if status}<p class="mt-2 text-[11px] text-emerald-300" role="status">{status}</p>{/if}
    {#if Object.keys(env).length}
      <details class="mt-3 rounded-xl border border-neutral-800 bg-neutral-950/50 p-3">
        <summary class="cursor-pointer text-[10px] uppercase tracking-wide text-neutral-500">Environment overrides ({Object.keys(env).length})</summary>
        <div class="mt-2 grid gap-1 sm:grid-cols-2">
          {#each Object.entries(env) as [key, value]}
            <p class="break-all font-mono text-[9px] text-neutral-500"><span class="text-neutral-400">{key}</span> = {value}</p>
          {/each}
        </div>
      </details>
    {/if}
  </section>

  {#if settings}
    <div class="grid gap-4 lg:grid-cols-2">
      <section class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4">
        <h3 class="text-xs font-semibold text-neutral-100">Runtime</h3>
        <div class="mt-3 grid gap-2 sm:grid-cols-2">
          <label class="text-[10px] text-neutral-500">Host<input bind:value={settings.runtime.host} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Port<input type="number" min="1" max="65535" bind:value={settings.runtime.port} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Log level
            <select bind:value={settings.runtime.log_level} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100">
              {#each ["debug", "info", "warning", "error"] as level}<option value={level}>{level}</option>{/each}
            </select>
          </label>
          <label class="text-[10px] text-neutral-500">Locale<input bind:value={settings.runtime.locale} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Max jobs<input type="number" min="1" max="16" bind:value={settings.runtime.max_jobs} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">History<input type="number" min="5" max="500" bind:value={settings.runtime.history} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="flex items-center gap-2 text-[10px] text-neutral-400"><input type="checkbox" bind:checked={settings.runtime.open_browser} class="h-3.5 w-3.5" />open browser</label>
        </div>
      </section>

      <section class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4">
        <h3 class="text-xs font-semibold text-neutral-100">Paths</h3>
        <div class="mt-3 grid gap-2">
          <label class="text-[10px] text-neutral-500">Allowed roots (comma-separated)<textarea rows="2" value={rootsText} oninput={(event) => (rootsText = event.currentTarget.value)} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100"></textarea></label>
          <div class="grid gap-2 sm:grid-cols-2">
            <label class="text-[10px] text-neutral-500">FFmpeg<input bind:value={settings.paths.ffmpeg} placeholder="auto" class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
            <label class="text-[10px] text-neutral-500">FFprobe<input bind:value={settings.paths.ffprobe} placeholder="auto" class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
            <label class="text-[10px] text-neutral-500">Cache dir<input bind:value={settings.paths.cache_dir} placeholder="default" class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
            <label class="text-[10px] text-neutral-500">Models dir<input bind:value={settings.paths.models_dir} placeholder="default" class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
            <label class="text-[10px] text-neutral-500">Output root<input bind:value={settings.paths.output_root} placeholder="default" class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
            <label class="text-[10px] text-neutral-500">Temp dir<input bind:value={settings.paths.temp_dir} placeholder="default" class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
          </div>
        </div>
      </section>

      <section class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4">
        <h3 class="text-xs font-semibold text-neutral-100">Models</h3>
        <div class="mt-3 grid gap-2 sm:grid-cols-2">
          <label class="text-[10px] text-neutral-500">Device
            <select bind:value={settings.models.device} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100">
              {#each ["cpu", "cuda", "auto"] as device}<option value={device}>{device}</option>{/each}
            </select>
          </label>
          <label class="text-[10px] text-neutral-500">Compute type<input bind:value={settings.models.compute_type} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Threads<input type="number" min="0" max="128" bind:value={settings.models.threads} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">HF token env<input bind:value={settings.models.hf_token_env} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
        </div>
        <p class="mt-2 text-[9px] text-neutral-600">Default model per capability:</p>
        <div class="mt-1 grid gap-1 sm:grid-cols-2">
          {#each Object.entries(settings.models.defaults) as [capability, model]}
            <div class="flex items-center gap-1 text-[9px] text-neutral-400">
              <span class="w-16 truncate">{capability}</span>
              <input value={model} oninput={(event) => setDefault(capability, event.currentTarget.value)} class="min-w-0 flex-1 rounded border border-neutral-800 bg-neutral-950 px-1 py-0.5 font-mono text-[9px] text-neutral-200" />
            </div>
          {/each}
          <div class="flex items-center gap-1 text-[9px] text-neutral-400">
            <input placeholder="capability" onchange={(event) => addCapability(event.currentTarget.value)} class="w-16 rounded border border-neutral-800 bg-neutral-950 px-1 py-0.5 text-[9px]" />
            <span class="text-neutral-600">add capability key</span>
          </div>
        </div>
      </section>

      <section class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4">
        <h3 class="text-xs font-semibold text-neutral-100">Automation and quality</h3>
        <div class="mt-3 grid gap-2 sm:grid-cols-2">
          <label class="text-[10px] text-neutral-500">Scheduler interval (s)<input type="number" min="5" bind:value={settings.automation.scheduler_interval_seconds} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Max retries<input type="number" min="0" max="20" bind:value={settings.automation.max_retries} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Backoff (s)<input type="number" min="5" bind:value={settings.automation.retry_backoff_seconds} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="flex items-end gap-2 pb-1 text-[10px] text-neutral-400"><input type="checkbox" bind:checked={settings.automation.enabled} class="h-3.5 w-3.5" />scheduler enabled</label>
          <label class="text-[10px] text-neutral-500">Target LUFS (integrated)<input type="number" step="0.5" bind:value={settings.quality.target_lufs} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">True peak (dBTP)<input type="number" step="0.5" bind:value={settings.quality.true_peak_db} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">VMAF threshold (0–100)<input type="number" min="0" max="100" bind:value={settings.quality.vmaf_threshold} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Proxy height (px)<input type="number" min="144" max="1080" bind:value={settings.quality.proxy_height} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
        </div>
      </section>

      <section class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4">
        <h3 class="text-xs font-semibold text-neutral-100">LLM and speech</h3>
        <div class="mt-3 grid gap-2 sm:grid-cols-2">
          <label class="text-[10px] text-neutral-500">Temperature<input type="number" min="0" max="2" step="0.1" bind:value={settings.llm.temperature} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Timeout (s)<input type="number" min="5" bind:value={settings.llm.timeout_seconds} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Max tokens<input type="number" min="0" bind:value={settings.llm.max_tokens} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Retries<input type="number" min="0" max="10" bind:value={settings.llm.retries} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="flex items-end gap-2 pb-1 text-[10px] text-neutral-400"><input type="checkbox" bind:checked={settings.llm.json_mode} class="h-3.5 w-3.5" />JSON mode</label>
          <label class="text-[10px] text-neutral-500">ASR engine
            <select bind:value={settings.speech.engine} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100">
              {#each ["auto", "faster-whisper", "whisper-cli"] as engine}<option value={engine}>{engine}</option>{/each}
            </select>
          </label>
          <label class="text-[10px] text-neutral-500">ASR language<input bind:value={settings.speech.language} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">ASR device
            <select bind:value={settings.speech.device} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100">
              {#each ["cpu", "cuda", "auto"] as device}<option value={device}>{device}</option>{/each}
            </select>
          </label>
          <label class="text-[10px] text-neutral-500">ASR compute<input bind:value={settings.speech.compute_type} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Diarization model<input bind:value={settings.speech.diarization_model} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="flex items-end gap-2 pb-1 text-[10px] text-neutral-400"><input type="checkbox" bind:checked={settings.speech.vad_filter} class="h-3.5 w-3.5" />ASR VAD filter</label>
        </div>
      </section>

      <section class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4">
        <h3 class="text-xs font-semibold text-neutral-100">TTS, stock, translation, UI</h3>
        <div class="mt-3 grid gap-2 sm:grid-cols-2">
          <label class="text-[10px] text-neutral-500">TTS provider
            <select bind:value={settings.tts.provider} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100">
              <option value="openai_compatible">openai_compatible</option>
              <option value="piper">piper</option>
            </select>
          </label>
          <label class="text-[10px] text-neutral-500">TTS voice<input bind:value={settings.tts.voice} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">TTS model<input bind:value={settings.tts.model} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">TTS format
            <select bind:value={settings.tts.format} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100">
              <option value="mp3">mp3</option><option value="wav">wav</option>
            </select>
          </label>
          <label class="text-[10px] text-neutral-500">Stock provider
            <select bind:value={settings.stock.provider} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100">
              <option value="local">local</option><option value="pexels">pexels</option>
            </select>
          </label>
          <label class="text-[10px] text-neutral-500">Pexels key env<input bind:value={settings.stock.pexels_key_env} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Stock asset dir<input bind:value={settings.stock.asset_dir} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Translation target<input bind:value={settings.translation.target_language} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Translation source<input bind:value={settings.translation.source_language} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Theme
            <select bind:value={settings.ui.theme} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100">
              {#each ["dark", "light", "system", "high-contrast"] as theme}<option value={theme}>{theme}</option>{/each}
            </select>
          </label>
          <label class="text-[10px] text-neutral-500">Density
            <select bind:value={settings.ui.density} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100">
              <option value="comfortable">comfortable</option><option value="compact">compact</option>
            </select>
          </label>
          <label class="flex items-end gap-2 pb-1 text-[10px] text-neutral-400"><input type="checkbox" bind:checked={settings.ui.timeline_snap} class="h-3.5 w-3.5" />timeline snap</label>
        </div>
      </section>
    </div>
  {/if}
</div>
