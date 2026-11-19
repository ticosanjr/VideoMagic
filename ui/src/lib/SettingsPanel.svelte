<script lang="ts">
  import { onMount } from "svelte";
  import ErrorBanner from "$lib/ErrorBanner.svelte";
  import FieldHint from "$lib/FieldHint.svelte";
  import HelpTip from "$lib/HelpTip.svelte";
  import SetupHealth from "$lib/SetupHealth.svelte";
  import {
    errorMessage,
    getIntelligenceModels,
    getIntelligenceStatus,
    getSettings,
    listHiltChannels,
    resetSettings,
    saveHiltSecret,
    saveSettings,
    testHiltChannel,
    type AppSettings,
    type HiltChannelStatus,
    type IntelligenceStatus
  } from "$lib/api";

  let settings = $state<AppSettings | null>(null);
  let env = $state<Record<string, string>>({});
  let restartRequired = $state<string[]>([]);
  let rootsText = $state("");
  let error = $state("");
  let status = $state("");
  let busy = $state(false);
  let query = $state("");
  let hiltChannels = $state<HiltChannelStatus[]>([]);
  let hiltStatus = $state("");
  let secretValues = $state<Record<string, string>>({});
  let secretNames = $state<string[]>([]);
  let intelligence = $state<IntelligenceStatus | null>(null);
  let intelligenceBusy = $state(false);
  let intelligenceModels = $state<string[]>([]);

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
      const hilt = await listHiltChannels();
      hiltChannels = hilt.channels;
      try {
        intelligence = await getIntelligenceStatus();
      } catch {
        intelligence = null;
      }
      secretNames = [
        settings.notifications.email.smtp_password_secret,
        settings.notifications.email.imap_password_secret,
        settings.notifications.slack.webhook_secret,
        settings.notifications.slack.bot_token_secret,
        settings.notifications.slack.signing_secret,
        settings.notifications.signal.password_secret
      ].filter((value, index, all) => value && all.indexOf(value) === index);
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  function setDefault(capability: string, value: string) {
    if (!settings) return;
    settings.models.defaults[capability] = value;
  }

  async function refreshIntelligence() {
    intelligenceBusy = true;
    try {
      intelligence = await getIntelligenceStatus();
      const models = await getIntelligenceModels("opencode_v2");
      intelligenceModels = models.models.map((item) => String(item.modelID ?? item.id ?? ""));
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      intelligenceBusy = false;
    }
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

  async function testChannel(channel: string) {
    hiltStatus = "";
    try {
      const result = await testHiltChannel(channel);
      hiltStatus = `${channel}: ${result.ok ? "ok" : "failed"} — ${result.message}`;
    } catch (reason) {
      hiltStatus = errorMessage(reason);
    }
  }

  async function saveSecret(name: string) {
    const value = secretValues[name] ?? "";
    if (!value.trim()) return;
    hiltStatus = "";
    try {
      await saveHiltSecret(name, value);
      secretValues = { ...secretValues, [name]: "" };
      hiltStatus = `${name} saved.`;
    } catch (reason) {
      hiltStatus = errorMessage(reason);
    }
  }

  function splitList(value: string): string[] {
    return value
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }

  onMount(() => {
    void load();
  });
</script>

<div class="space-y-4" data-testid="settings-panel">
  <SetupHealth />
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

      <section class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4" data-settings-section>
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h3 class="text-xs font-semibold text-neutral-100">Notifications</h3>
          <span class="text-[10px] text-neutral-500">off by default</span>
        </div>
        <div class="mt-3 grid gap-2 sm:grid-cols-3">
          <label class="flex items-end gap-2 pb-1 text-[10px] text-neutral-300">
            <input type="checkbox" bind:checked={settings.notifications.enabled} class="h-3.5 w-3.5" />
            Enabled (master)
          </label>
          <label class="text-[10px] text-neutral-500">In-app level
            <select bind:value={settings.notifications.ui_level} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100">
              {#each ["off", "required", "important", "all"] as level}<option value={level}>{level}</option>{/each}
            </select>
          </label>
          <label class="text-[10px] text-neutral-500">Desktop level
            <select bind:value={settings.notifications.desktop_level} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100">
              {#each ["off", "required", "important", "all"] as level}<option value={level}>{level}</option>{/each}
            </select>
          </label>
        </div>
        <p class="mt-2 text-[10px] leading-4 text-neutral-500">
          off = nothing, required = only human interaction, important = interaction plus failures,
          all = every event. The master switch overrides both levels.
        </p>
        <div class="mt-3 grid gap-2 sm:grid-cols-2">
          <label class="flex items-center gap-2 text-[10px] text-neutral-300"><input type="checkbox" bind:checked={settings.notifications.notify_hitl} class="h-3.5 w-3.5" />Human interaction (approval, question, files)</label>
          <label class="flex items-center gap-2 text-[10px] text-neutral-300"><input type="checkbox" bind:checked={settings.notifications.notify_job_failed} class="h-3.5 w-3.5" />Job failures</label>
          <label class="flex items-center gap-2 text-[10px] text-neutral-300"><input type="checkbox" bind:checked={settings.notifications.notify_warnings} class="h-3.5 w-3.5" />Warnings</label>
          <label class="flex items-center gap-2 text-[10px] text-neutral-300"><input type="checkbox" bind:checked={settings.notifications.notify_job_finished} class="h-3.5 w-3.5" />Jobs finished</label>
          <label class="flex items-center gap-2 text-[10px] text-neutral-300"><input type="checkbox" bind:checked={settings.notifications.notify_job_cancelled} class="h-3.5 w-3.5" />Jobs cancelled</label>
          <label class="flex items-center gap-2 text-[10px] text-neutral-300"><input type="checkbox" bind:checked={settings.notifications.notify_system} class="h-3.5 w-3.5" />System diagnostics</label>
        </div>
        <div class="mt-3 flex flex-wrap items-center gap-3 text-[10px] text-neutral-400">
          <label class="flex items-center gap-1"><input type="checkbox" bind:checked={settings.notifications.local.enabled} class="h-3.5 w-3.5" />local log</label>
          <label class="flex items-center gap-1"><input type="checkbox" bind:checked={settings.notifications.local.desktop} class="h-3.5 w-3.5" />desktop notification</label>
          <button type="button" onclick={() => void testChannel("local")} class="rounded border border-neutral-700 px-2 py-0.5 text-[10px] text-neutral-300">Send test notification</button>
        </div>
      </section>

      <section class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4" data-settings-section>
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h3 class="text-xs font-semibold text-neutral-100">Human-in-the-loop channels</h3>
          <span class="text-[10px] text-neutral-500">external delivery for pending requests</span>
        </div>
        <div class="mt-3 grid gap-2">
          <label class="text-[10px] text-neutral-500">Default channels (comma-separated)
            <input
              value={(settings?.notifications.default_channels ?? []).join(", ")}
              oninput={(event) => { if (settings) settings.notifications.default_channels = splitList(event.currentTarget.value); }}
              class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100"
            />
          </label>
          <label class="text-[10px] text-neutral-500">Public base URL for reply links
            <input bind:value={settings.notifications.base_url} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" />
          </label>
        </div>

        <div class="mt-4 rounded-xl border border-neutral-800 bg-neutral-950/40 p-3">
          <div class="flex items-center justify-between gap-2">
            <label class="flex items-center gap-1 text-[11px] text-neutral-200"><input type="checkbox" bind:checked={settings.notifications.email.enabled} class="h-3.5 w-3.5" />E-mail</label>
            <button type="button" onclick={() => void testChannel("email")} class="rounded border border-neutral-700 px-2 py-0.5 text-[10px] text-neutral-300">Test</button>
          </div>
          <div class="mt-2 grid gap-2 sm:grid-cols-2">
            <label class="text-[10px] text-neutral-500">SMTP host<input bind:value={settings.notifications.email.smtp_host} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100" /></label>
            <label class="text-[10px] text-neutral-500">SMTP port<input type="number" bind:value={settings.notifications.email.smtp_port} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100" /></label>
            <label class="text-[10px] text-neutral-500">SMTP user<input bind:value={settings.notifications.email.smtp_user} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100" /></label>
            <label class="text-[10px] text-neutral-500">From<input bind:value={settings.notifications.email.from_address} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100" /></label>
            <label class="text-[10px] text-neutral-500">To (comma)<input value={(settings?.notifications.email.to_addresses ?? []).join(", ")} oninput={(event) => { if (settings) settings.notifications.email.to_addresses = splitList(event.currentTarget.value); }} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100" /></label>
            <label class="text-[10px] text-neutral-500">IMAP host<input bind:value={settings.notifications.email.imap_host} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100" /></label>
            <label class="text-[10px] text-neutral-500">IMAP port<input type="number" bind:value={settings.notifications.email.imap_port} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100" /></label>
            <label class="text-[10px] text-neutral-500">IMAP user<input bind:value={settings.notifications.email.imap_user} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100" /></label>
            <label class="text-[10px] text-neutral-500">Allowed senders (comma)<input value={(settings?.notifications.email.allowed_senders ?? []).join(", ")} oninput={(event) => { if (settings) settings.notifications.email.allowed_senders = splitList(event.currentTarget.value); }} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100" /></label>
            <label class="text-[10px] text-neutral-500">SMTP/IMAP secret names<input bind:value={settings.notifications.email.smtp_password_secret} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[10px] text-neutral-100" /></label>
          </div>
        </div>

        <div class="mt-3 rounded-xl border border-neutral-800 bg-neutral-950/40 p-3">
          <div class="flex items-center justify-between gap-2">
            <label class="flex items-center gap-1 text-[11px] text-neutral-200"><input type="checkbox" bind:checked={settings.notifications.slack.enabled} class="h-3.5 w-3.5" />Slack</label>
            <button type="button" onclick={() => void testChannel("slack")} class="rounded border border-neutral-700 px-2 py-0.5 text-[10px] text-neutral-300">Test</button>
          </div>
          <div class="mt-2 grid gap-2 sm:grid-cols-2">
            <label class="text-[10px] text-neutral-500">Mode
              <select bind:value={settings.notifications.slack.mode} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100">
                <option value="webhook">webhook</option>
                <option value="bot">bot</option>
              </select>
            </label>
            <label class="text-[10px] text-neutral-500">Channel<input bind:value={settings.notifications.slack.channel} placeholder="#videoflow" class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100" /></label>
            <label class="text-[10px] text-neutral-500">Allowed users (comma)<input value={(settings?.notifications.slack.allowed_users ?? []).join(", ")} oninput={(event) => { if (settings) settings.notifications.slack.allowed_users = splitList(event.currentTarget.value); }} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100" /></label>
            <label class="text-[10px] text-neutral-500">Webhook secret name<input bind:value={settings.notifications.slack.webhook_secret} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[10px] text-neutral-100" /></label>
            <label class="text-[10px] text-neutral-500">Bot token secret name<input bind:value={settings.notifications.slack.bot_token_secret} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[10px] text-neutral-100" /></label>
            <label class="text-[10px] text-neutral-500">Signing secret name<input bind:value={settings.notifications.slack.signing_secret} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[10px] text-neutral-100" /></label>
          </div>
        </div>

        <div class="mt-3 rounded-xl border border-neutral-800 bg-neutral-950/40 p-3">
          <div class="flex items-center justify-between gap-2">
            <label class="flex items-center gap-1 text-[11px] text-neutral-200"><input type="checkbox" bind:checked={settings.notifications.signal.enabled} class="h-3.5 w-3.5" />Signal</label>
            <button type="button" onclick={() => void testChannel("signal")} class="rounded border border-neutral-700 px-2 py-0.5 text-[10px] text-neutral-300">Test</button>
          </div>
          <div class="mt-2 grid gap-2 sm:grid-cols-2">
            <label class="text-[10px] text-neutral-500">signal-cli REST URL<input bind:value={settings.notifications.signal.api_url} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100" /></label>
            <label class="text-[10px] text-neutral-500">Number<input bind:value={settings.notifications.signal.number} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100" /></label>
            <label class="text-[10px] text-neutral-500">Recipients (comma)<input value={(settings?.notifications.signal.recipients ?? []).join(", ")} oninput={(event) => { if (settings) settings.notifications.signal.recipients = splitList(event.currentTarget.value); }} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100" /></label>
            <label class="text-[10px] text-neutral-500">Allowed senders (comma)<input value={(settings?.notifications.signal.allowed_senders ?? []).join(", ")} oninput={(event) => { if (settings) settings.notifications.signal.allowed_senders = splitList(event.currentTarget.value); }} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100" /></label>
          </div>
        </div>

        <div class="mt-3 rounded-xl border border-neutral-800 bg-neutral-950/40 p-3">
          <p class="text-[10px] uppercase tracking-wide text-neutral-500">Secrets</p>
          <div class="mt-2 grid gap-2">
            {#each secretNames as name}
              <div class="flex items-end gap-2">
                <label class="min-w-0 flex-1 text-[10px] text-neutral-500">{name}
                  <input
                    type="password"
                    value={secretValues[name] ?? ""}
                    oninput={(event) => (secretValues = { ...secretValues, [name]: event.currentTarget.value })}
                    class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[10px] text-neutral-100"
                  />
                </label>
                <button type="button" onclick={() => void saveSecret(name)} class="rounded border border-neutral-700 px-2 py-1 text-[10px] text-neutral-300">Save</button>
              </div>
            {/each}
            <p class="text-[9px] text-neutral-600">Secrets use the OS keyring when available; the file fallback is 0600. Values are never returned.</p>
          </div>
        </div>
        {#if hiltStatus}<p class="mt-2 text-[10px] text-emerald-300" role="status">{hiltStatus}</p>{/if}
        {#if hiltChannels.length}
          <div class="mt-2 flex flex-wrap gap-1">
            {#each hiltChannels as channel}
              <span class="rounded-full border border-neutral-700 px-2 py-0.5 text-[9px] text-neutral-400">{channel.id}: {channel.available ? "ready" : "not configured"}</span>
            {/each}
          </div>
        {/if}
      </section>

      <section class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4" data-settings-section>
        <h3 class="text-xs font-semibold text-neutral-100">Research providers</h3>
        <p class="mt-1 text-[10px] text-neutral-500">Local, free, and self-hosted sources. External fetches require the explicit allow flag or a configured local host.</p>
        <div class="mt-3 grid gap-2 sm:grid-cols-2">
          <label class="text-[10px] text-neutral-500">Providers (comma)<input value={(settings?.search.providers ?? []).join(", ")} oninput={(event) => { if (settings) settings.search.providers = splitList(event.currentTarget.value); }} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">SearXNG URL<input bind:value={settings.search.searxng_url} placeholder="http://127.0.0.1:8080" class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Local corpus paths (comma)<input value={(settings?.search.local_paths ?? []).join(", ")} oninput={(event) => { if (settings) settings.search.local_paths = splitList(event.currentTarget.value); }} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Crawl seed URLs (comma)<input value={(settings?.search.seed_urls ?? []).join(", ")} oninput={(event) => { if (settings) settings.search.seed_urls = splitList(event.currentTarget.value); }} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Wikipedia language<input bind:value={settings.search.wikipedia_language} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Max results<input type="number" bind:value={settings.search.max_results} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Pages per scope<input type="number" bind:value={settings.search.fetch_pages} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Cache TTL hours<input type="number" bind:value={settings.search.cache_ttl_hours} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100" /></label>
          <label class="flex items-center gap-1 text-[10px] text-neutral-400"><input type="checkbox" bind:checked={settings.search.enabled} class="h-3.5 w-3.5" />enabled</label>
          <label class="flex items-center gap-1 text-[10px] text-neutral-400"><input type="checkbox" bind:checked={settings.search.allow_network} class="h-3.5 w-3.5" />allow network by default</label>
        </div>
      </section>

      <section class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4">
        <h3 class="text-xs font-semibold text-neutral-100">Asset licensing</h3>
        <p class="mt-1 text-[10px] text-neutral-500">Stock providers and fair-use limits. Every harvested asset is written to the license ledger.</p>
        <div class="mt-3 grid gap-2 sm:grid-cols-2">
          <label class="text-[10px] text-neutral-500">Pexels key env<input bind:value={settings.stock.pexels_key_env} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Pixabay key env<input bind:value={settings.stock.pixabay_key_env} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Openverse token env<input bind:value={settings.stock.openverse_token_env} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">YouTube clip seconds<input type="number" min="1" max="120" bind:value={settings.stock.youtube_fair_use_seconds} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">YouTube clips per video<input type="number" min="1" max="10" bind:value={settings.stock.youtube_max_per_video} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100" /></label>
          <label class="flex items-center gap-1 text-[10px] text-neutral-400"><input type="checkbox" bind:checked={settings.stock.allow_fair_use} class="h-3.5 w-3.5" />allow fair-use excerpts</label>
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
        <h3 class="text-xs font-semibold text-neutral-100">Quality</h3>
        <div class="mt-3 grid gap-2 sm:grid-cols-2">
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
          <label class="text-[10px] text-neutral-500">ASR profile
            <select bind:value={settings.speech.quality_profile} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100">
              {#each ["auto", "custom", "fast", "balanced", "quality", "vulkan", "remote"] as profile}<option value={profile}>{profile}</option>{/each}
            </select>
          </label>
          <label class="text-[10px] text-neutral-500">ASR language<input bind:value={settings.speech.language} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Beam size<input type="number" min="1" max="10" bind:value={settings.speech.beam_size} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">CPU threads (0 = auto)<input type="number" min="0" max="128" bind:value={settings.speech.cpu_threads} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Word timestamps
            <select bind:value={settings.speech.word_timestamps} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100">
              {#each ["auto", "always", "off"] as mode}<option value={mode}>{mode}</option>{/each}
            </select>
          </label>
          <label class="text-[10px] text-neutral-500">Remote ASR URL<input bind:value={settings.speech.remote_base_url} placeholder="http://100.x.x.x:8000/v1" class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Remote ASR model<input bind:value={settings.speech.remote_model} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Remote ASR key env<input bind:value={settings.speech.remote_api_key_env} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">ASR device
            <select bind:value={settings.speech.device} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100">
              {#each ["cpu", "cuda", "auto"] as device}<option value={device}>{device}</option>{/each}
            </select>
          </label>
          <label class="text-[10px] text-neutral-500">ASR compute<input bind:value={settings.speech.compute_type} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Diarization model<input bind:value={settings.speech.diarization_model} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="flex items-end gap-2 pb-1 text-[10px] text-neutral-400"><input type="checkbox" bind:checked={settings.speech.vad_filter} class="h-3.5 w-3.5" />ASR VAD filter</label>
          <label class="flex items-end gap-2 pb-1 text-[10px] text-neutral-400"><input type="checkbox" bind:checked={settings.speech.condition_on_previous_text} class="h-3.5 w-3.5" />Condition on previous text</label>
        </div>
      </section>

      <section class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4" data-settings-section>
        <div class="flex flex-wrap items-center justify-between gap-2">
          <h3 class="text-xs font-semibold text-neutral-100">Intelligence</h3>
          <button type="button" onclick={() => void refreshIntelligence()} disabled={intelligenceBusy} class="rounded-lg border border-sky-500/30 px-2.5 py-1 text-[10px] text-sky-200 disabled:opacity-40">
            {intelligenceBusy ? "Checking…" : "Test providers"}
          </button>
        </div>
        <p class="mt-1 text-[10px] text-neutral-500">OpenCode V2 first, then DeepSeek, then any OpenAI-compatible provider. Local-first; remote providers need network access.</p>
        <div class="mt-3 grid gap-2 sm:grid-cols-2">
          <label class="flex items-end gap-2 pb-1 text-[10px] text-neutral-400"><input type="checkbox" bind:checked={settings.intelligence.enabled} class="h-3.5 w-3.5" />Enabled</label>
          <label class="flex items-end gap-2 pb-1 text-[10px] text-neutral-400"><input type="checkbox" bind:checked={settings.intelligence.allow_network} class="h-3.5 w-3.5" />Allow remote providers</label>
          <label class="text-[10px] text-neutral-500">Provider order (comma)<input value={(settings.intelligence.provider_order ?? []).join(", ")} oninput={(event) => { if (settings) settings.intelligence.provider_order = splitList(event.currentTarget.value); }} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Budget (USD, 0 = off)<input type="number" min="0" step="0.01" bind:value={settings.intelligence.budget_usd} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">OpenCode base URL<input bind:value={settings.intelligence.opencode_base_url} placeholder="http://127.0.0.1:4096" class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">OpenCode model
            <select bind:value={settings.intelligence.opencode_model} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100">
              <option value="">auto</option>
              {#each intelligenceModels as model}<option value={model}>{model}</option>{/each}
            </select>
          </label>
          <label class="text-[10px] text-neutral-500">OpenCode token env<input bind:value={settings.intelligence.opencode_token_env} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">DeepSeek model<input bind:value={settings.intelligence.deepseek_model} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">DeepSeek base URL<input bind:value={settings.intelligence.deepseek_base_url} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">DeepSeek key env<input bind:value={settings.intelligence.deepseek_api_key_env} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
        </div>
        {#if intelligence}
          <div class="mt-3 space-y-1">
            {#each intelligence.providers as provider}
              <div class="flex items-center justify-between rounded-lg border border-neutral-800 bg-neutral-950/60 px-2.5 py-1.5 text-[10px]">
                <span class="font-mono text-neutral-300">{provider.provider} · {provider.kind}</span>
                <span class={provider.ready ? "text-emerald-300" : "text-amber-300"}>{provider.ready ? "ready" : provider.detail || "not ready"}</span>
              </div>
            {/each}
            <p class="text-[10px] text-neutral-500">Calls: {String((intelligence.telemetry as { calls?: number }).calls ?? 0)} · cost: ${String((intelligence.telemetry as { estimated_cost_usd?: number }).estimated_cost_usd ?? 0)}</p>
          </div>
        {/if}
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
        </div>
      </section>
    </div>
  {/if}
</div>
