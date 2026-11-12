<script lang="ts">
  import HelpTip from "$lib/HelpTip.svelte";
  import ErrorBanner from "$lib/ErrorBanner.svelte";
  import { onMount } from "svelte";
  import {
    deleteProvider,
    errorMessage,
    createVoiceProfile,
    deleteVoiceProfile,
    getCapabilities,
    getVoiceCloneStatus,
    listProviders,
    listVoiceProfiles,
    deleteProviderSecret,
    saveProvider,
    setDefaultProvider,
    setProviderSecret,
    testProvider,
    type Capability,
    type CapabilitiesResponse,
    type ProviderConfig,
    type ProviderTestResult,
    type VoiceCloneStatus,
    type VoiceProfile
  } from "$lib/api";

  let {
    allowExternal = false,
    allowedHosts = "",
    onToggle,
    onHosts
  }: {
    allowExternal: boolean;
    allowedHosts: string;
    onToggle: (value: boolean) => void;
    onHosts: (value: string) => void;
  } = $props();

  let response = $state<CapabilitiesResponse | null>(null);
  let loading = $state(true);
  let error = $state("");
  let query = $state("");
  let statusFilter = $state("");
  let catalogOpen = $state(false);
  let testUrl = $state("http://127.0.0.1:11434/v1");
  let testKeyEnv = $state("VIDEOWFLOW_LLM_API_KEY");
  let testPath = $state("/models");
  let testBusy = $state(false);
  let testResult = $state<ProviderTestResult | null>(null);
  let testError = $state("");
  let draftTestResult = $state<ProviderTestResult | null>(null);
  let draftTestError = $state("");
  let providers = $state<ProviderConfig[]>([]);
  let fallbacks = $state<Record<string, ProviderConfig[]>>({});
  let providerBusy = $state("");
  let secretDrafts = $state<Record<string, string>>({});
  let secretBackend = $state("");
  let providerMessage = $state("");
  let providerError = $state("");
  let draft = $state<ProviderConfig>(blankProvider());
  let editingProviderId = $state("");
  let editorOpen = $state(false);
  let secretDraft = $state("");
  let testMode = $state<"chat" | "models">("chat");
  let providerTests = $state<Record<string, ProviderTestResult>>({});
  const SECRET_NAME = /^[A-Za-z_][A-Za-z0-9_]*$/;

  function secretSourceLabel(source?: string): string {
    if (source === "request") return "from this form (not saved)";
    if (source === "environment") return "environment";
    if (source === "stored") return "stored";
    if (source === "missing") return "not found";
    return "";
  }

  function secretNameError(): string {
    const value = draft.api_key_env.trim();
    return value && !SECRET_NAME.test(value)
      ? "Secret env must be a variable name like DEEPSEEK_API_KEY, not the API key."
      : "";
  }
  let voiceStatus = $state<VoiceCloneStatus | null>(null);
  let voiceProfiles = $state<VoiceProfile[]>([]);
  let voiceName = $state("");
  let voiceConsent = $state("");
  let voiceSamples = $state(0);
  let voiceSamplePaths = $state("");
  let voiceError = $state("");
  let voiceBusy = $state(false);

  async function refreshVoiceClone() {
    try {
      voiceStatus = await getVoiceCloneStatus();
      voiceProfiles = await listVoiceProfiles();
    } catch (reason) {
      voiceError = errorMessage(reason);
    }
  }

  async function addVoiceProfile() {
    voiceBusy = true;
    voiceError = "";
    try {
      await createVoiceProfile({
        name: voiceName.trim(),
        consent_ref: voiceConsent.trim(),
        sample_count: voiceSamples,
        sample_paths: voiceSamplePaths
          .split(",")
          .map((item) => item.trim())
          .filter(Boolean)
      });
      voiceName = "";
      voiceConsent = "";
      voiceSamples = 0;
      voiceSamplePaths = "";
      await refreshVoiceClone();
    } catch (reason) {
      voiceError = errorMessage(reason);
    } finally {
      voiceBusy = false;
    }
  }

  async function removeVoiceProfile(profile: VoiceProfile) {
    voiceBusy = true;
    try {
      await deleteVoiceProfile(profile.id);
      await refreshVoiceClone();
    } catch (reason) {
      voiceError = errorMessage(reason);
    } finally {
      voiceBusy = false;
    }
  }

  const capabilities = ["llm", "asr", "tts", "vision", "stock", "translation", "diarization", "publishing"];

  function blankProvider(): ProviderConfig {
    return {
      id: "",
      name: "",
      capability: "llm",
      base_url: "http://127.0.0.1:11434/v1",
      api_key_env: "VIDEOWFLOW_LLM_API_KEY",
      model: "",
      enabled: true,
      is_default: false,
      fallback: [],
      notes: ""
    };
  }

  function editProvider(provider: ProviderConfig) {
    draft = { ...provider, fallback: [...provider.fallback] };
    editingProviderId = provider.id;
    editorOpen = true;
    secretDraft = "";
    providerMessage = "";
    providerError = "";
    draftTestResult = null;
    draftTestError = "";
    requestAnimationFrame(() => {
      document.getElementById("provider-editor")?.scrollIntoView({ block: "start" });
    });
  }

  function newProvider() {
    draft = blankProvider();
    editingProviderId = "";
    editorOpen = true;
    secretDraft = "";
    draftTestResult = null;
    draftTestError = "";
    providerMessage = "";
    providerError = "";
    requestAnimationFrame(() => {
      document.getElementById("provider-editor")?.scrollIntoView({ block: "start" });
    });
  }

  function applyPreset(preset: Partial<ProviderConfig>) {
    draft = { ...draft, ...preset, fallback: [...(draft.fallback ?? [])] };
  }

  async function testSavedProvider(provider: ProviderConfig) {
    providerBusy = provider.id;
    providerError = "";
    try {
      const result = await testProvider({
        provider_id: provider.id,
        mode: "chat",
        path: "/models"
      });
      providerTests = { ...providerTests, [provider.id]: result };
    } catch (reason) {
      providerError = errorMessage(reason);
    } finally {
      providerBusy = "";
    }
  }

  async function refreshProviders() {
    try {
      const payload = await listProviders();
      providers = payload.providers;
      fallbacks = payload.fallbacks;
      secretBackend = payload.secret_backend ?? "";
    } catch (reason) {
      providerError = errorMessage(reason);
    }
  }

  async function saveDraft() {
    if (!draft.id.trim() || !draft.name.trim()) {
      providerError = "Provider id and name are required.";
      return;
    }
    const secretError = secretNameError();
    if (secretError) {
      providerError = secretError;
      return;
    }
    draft.api_key_env = draft.api_key_env.trim();
    providerBusy = "save";
    providerError = "";
    providerMessage = "";
    try {
      const payload = { ...draft, id: draft.id.trim().toLowerCase() };
      delete (payload as { secret_present?: boolean }).secret_present;
      delete (payload as { configured?: boolean }).configured;
      delete (payload as { missing?: string[] }).missing;
      const saved = await saveProvider(payload);
      if (secretDraft.trim()) {
        await setProviderSecret(saved.id, secretDraft.trim());
        secretDraft = "";
      }
      providerMessage = `${saved.name} saved.`;
      draft = blankProvider();
      editingProviderId = "";
      editorOpen = false;
      await refreshProviders();
    } catch (reason) {
      providerError = errorMessage(reason);
    } finally {
      providerBusy = "";
    }
  }

  async function removeProvider(providerId: string) {
    providerBusy = providerId;
    providerError = "";
    try {
      await deleteProvider(providerId);
      providerMessage = `${providerId} removed.`;
      await refreshProviders();
    } catch (reason) {
      providerError = errorMessage(reason);
    } finally {
      providerBusy = "";
    }
  }

  async function saveSecret(providerId: string) {
    const value = (secretDrafts[providerId] ?? "").trim();
    if (!value) return;
    providerBusy = providerId;
    providerError = "";
    try {
      await setProviderSecret(providerId, value);
      secretDrafts = { ...secretDrafts, [providerId]: "" };
      providerMessage = `Secret stored for ${providerId}.`;
      await refreshProviders();
    } catch (reason) {
      providerError = errorMessage(reason);
    } finally {
      providerBusy = "";
    }
  }

  async function clearSecret(providerId: string) {
    providerBusy = providerId;
    try {
      await deleteProviderSecret(providerId);
      providerMessage = `Secret cleared for ${providerId}.`;
      await refreshProviders();
    } catch (reason) {
      providerError = errorMessage(reason);
    } finally {
      providerBusy = "";
    }
  }

  async function makeDefault(providerId: string) {
    providerBusy = providerId;
    try {
      await setDefaultProvider(providerId);
      providerMessage = `${providerId} is now the default.`;
      await refreshProviders();
    } catch (reason) {
      providerError = errorMessage(reason);
    } finally {
      providerBusy = "";
    }
  }

  async function testDraft() {
    draftTestError = "";
    draftTestResult = null;
    const base = draft.base_url.trim();
    if (!/^https?:\/\//i.test(base)) {
      draftTestError = "Base URL must start with http:// or https://.";
      return;
    }
    const secretError = secretNameError();
    if (secretError) {
      draftTestError = secretError;
      return;
    }
    const envName = draft.api_key_env.trim();
    const pasted = secretDraft.trim();
    if (pasted && !envName) {
      draftTestError =
        "Enter the Secret env name (for example DEEPSEEK_API_KEY) to use the pasted key.";
      return;
    }
    if (testMode === "chat" && !draft.model.trim()) {
      draftTestError =
        "Chat test requires a model. Enter the model name, for example deepseek-chat.";
      return;
    }
    testBusy = true;
    try {
      draftTestResult = await testProvider({
        base_url: base,
        api_key_env: envName,
        secret_value: pasted,
        model: draft.model.trim(),
        path: testPath,
        mode: testMode
      });
    } catch (reason) {
      draftTestError = errorMessage(reason);
    } finally {
      testBusy = false;
    }
  }

  const categories = ["ingest", "speech", "shorts", "export", "providers", "curation", "editing", "audio"];

  const grouped = $derived(
    categories
      .map((category) => ({
        category,
        items: (response?.capabilities ?? []).filter((item) => {
          if (statusFilter && item.status !== statusFilter) return false;
          const needle = query.trim().toLocaleLowerCase();
          return !needle ||
            item.name.toLocaleLowerCase().includes(needle) ||
            item.description.toLocaleLowerCase().includes(needle) ||
            category.toLocaleLowerCase().includes(needle);
        })
      }))
      .filter((group) => group.items.length > 0)
  );

  const counts = $derived(
    (response?.capabilities ?? []).reduce<Record<string, number>>((totals, item) => {
      totals[item.status] = (totals[item.status] ?? 0) + 1;
      return totals;
    }, {})
  );

  const statusStyles: Record<string, string> = {
    available: "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20",
    blocked: "bg-rose-400/10 text-rose-300 ring-rose-400/20",
    partial: "bg-amber-400/10 text-amber-300 ring-amber-400/20",
    planned: "bg-neutral-800 text-neutral-400 ring-neutral-700"
  };

  async function runProviderTest() {
    testError = "";
    testResult = null;
    const base = testUrl.trim();
    if (!/^https?:\/\//i.test(base)) {
      testError = "Base URL must start with http:// or https://.";
      return;
    }
    const envName = testKeyEnv.trim();
    if (envName && !SECRET_NAME.test(envName)) {
      testError =
        "Secret env must be a variable name like DEEPSEEK_API_KEY, not the API key.";
      return;
    }
    testBusy = true;
    try {
      testResult = await testProvider({
        base_url: base,
        api_key_env: envName,
        path: testPath
      });
    } catch (reason) {
      testError = errorMessage(reason);
    } finally {
      testBusy = false;
    }
  }

  async function refresh(value = allowExternal) {
    loading = true;
    error = "";
    try {
      response = await getCapabilities(value);
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      loading = false;
    }
  }

  function toggle(value: boolean) {
    onToggle(value);
    void refresh(value);
  }

  onMount(() => {
    void refresh();
    void refreshProviders();
    void refreshVoiceClone();
  });
</script>

<div class="space-y-4">
  {#snippet providerTestFeedback(result: ProviderTestResult | null, error: string)}
    {#if error}
      <p class="mt-2 rounded-lg border border-rose-500/30 bg-rose-950/20 p-2 text-[10px] text-rose-300" role="alert">{error}</p>
    {/if}
    {#if result}
      <div class={`mt-2 rounded-lg border p-2 text-[10px] ${result.ok ? "border-emerald-500/30 bg-emerald-950/20 text-emerald-300" : "border-rose-500/30 bg-rose-950/20 text-rose-300"}`} role="status" aria-live="polite">
        <p class="font-medium">
          {result.ok ? "Connection OK" : "Connection failed"}{#if result.status_code !== null && result.status_code !== undefined} · HTTP {result.status_code}{/if}{#if result.latency_ms !== undefined} · {result.latency_ms} ms{/if}
        </p>
        {#if result.message}<p class="mt-1 break-words text-neutral-300">{result.message}</p>{/if}
        {#if result.hint}<p class="mt-1 break-words text-[9px] text-neutral-400">{result.hint}</p>{/if}
        {#if result.secret_source}
          <p class="mt-1 text-[9px] text-neutral-500">API key: {secretSourceLabel(result.secret_source)}</p>
        {/if}
        {#if result.provider_message}
          <details class="mt-1">
            <summary class="cursor-pointer text-[9px] text-neutral-500">Provider response</summary>
            <pre class="mt-1 max-h-32 overflow-auto whitespace-pre-wrap break-all font-mono text-[9px] text-neutral-500">{result.provider_message}</pre>
          </details>
        {/if}
      </div>
    {/if}
  {/snippet}

  <ErrorBanner message={error} onDismiss={() => (error = "")} />
  <ErrorBanner message={providerError} title="Provider configuration failed" onDismiss={() => (providerError = "")} testId="provider-error" />
  <div class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h2 class="text-sm font-semibold">AI providers</h2>
        <p class="mt-1 max-w-2xl text-xs leading-5 text-neutral-400">
          Local features work offline. External services are opt-in per run and can be
          blocked globally with <code class="rounded bg-neutral-800 px-1 py-0.5 text-[10px]">VIDEOWFLOW_ALLOW_EXTERNAL=0</code>.
          API keys stay in the environment; project state stores only the secret name.
        </p>
      </div>
      <span
        class="rounded-full px-3 py-1 text-[11px] font-medium ring-1 {response?.external_services_allowed
          ? 'bg-emerald-400/10 text-emerald-300 ring-emerald-400/20'
          : 'bg-neutral-800 text-neutral-400 ring-neutral-700'}"
      >
        {response?.external_services_allowed ? "External services allowed" : "Offline policy"}
      </span>
    </div>

    <label class="mt-4 flex items-center gap-3 rounded-xl border border-neutral-800 bg-neutral-950/60 p-3 text-xs text-neutral-300">
      <input
        type="checkbox"
        checked={allowExternal}
        onchange={(event) => toggle(event.currentTarget.checked)}
        class="h-4 w-4 rounded border-neutral-700 bg-neutral-800"
      />
      <span>
        Allow external providers for the next run
        <span class="block text-[10px] text-neutral-500">
          Local providers (localhost) are always allowed. This flag covers remote LLM/ASR and future providers.
        </span>
      </span>
    </label>

    <label class="mt-2 block rounded-xl border border-neutral-800 bg-neutral-950/60 p-3 text-xs text-neutral-300">
      <span class="text-[10px] uppercase tracking-wide text-neutral-500">Allowed external hosts</span>
      <input
        type="text"
        value={allowedHosts}
        oninput={(event) => onHosts(event.currentTarget.value)}
        placeholder="api.openai.com, api.elevenlabs.io"
        class="mt-1.5 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[11px] text-neutral-100 placeholder:text-neutral-600"
      />
      <span class="mt-1 block text-[10px] text-neutral-500">
        Comma-separated allowlist. Empty means any remote host while external access is on.
      </span>
    </label>
  </div>

  <div class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
    <h3 class="text-xs font-semibold text-neutral-100">Connection test</h3>
    <p class="mt-1 text-[10px] text-neutral-500">Test an OpenAI-compatible or other HTTP provider. Secrets are read from the environment and never displayed.</p>
    <div class="mt-3 grid gap-2 lg:grid-cols-[1fr_1fr_120px_auto]">
      <input bind:value={testUrl} placeholder="http://127.0.0.1:11434/v1" class="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" />
      <input bind:value={testKeyEnv} placeholder="VIDEOWFLOW_LLM_API_KEY" class="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" />
      <input bind:value={testPath} placeholder="/models" class="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" />
      <button type="button" onclick={() => void runProviderTest()} disabled={testBusy} class="rounded-lg border border-sky-500/40 px-3 py-1.5 text-[10px] text-sky-200 disabled:opacity-40">{testBusy ? "Testing…" : "Test"}</button>
    </div>
    {@render providerTestFeedback(testResult, testError)}
  </div>

  <div class="rounded-2xl border border-amber-400/20 bg-amber-950/10 p-4" data-testid="voice-clone-shell">
    <div class="flex flex-wrap items-start justify-between gap-2">
      <div>
        <h3 class="text-xs font-semibold text-neutral-100">Voice clone</h3>
        <p class="mt-1 max-w-2xl text-[10px] leading-5 text-neutral-400">
          Optional ElevenLabs cloning. Store a consent reference and server-local reference samples; synthesis runs only when the provider and secret are configured.
        </p>
      </div>
      <span class="rounded-full px-2 py-0.5 text-[10px] {voiceStatus?.available ? "bg-emerald-500/10 text-emerald-300" : "bg-amber-500/10 text-amber-300"}">
        {voiceStatus?.available ? "available" : "not available"}
      </span>
    </div>
    {#if voiceStatus}
      <p class="mt-2 text-[10px] text-amber-200/80">{voiceStatus.reason}</p>
    {/if}
    <div class="mt-3 grid gap-2 lg:grid-cols-[1fr_1fr_100px_auto]">
      <input bind:value={voiceName} placeholder="Profile name" class="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" />
      <input bind:value={voiceConsent} placeholder="Consent reference" class="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" />
      <input bind:value={voiceSamples} type="number" min="0" max="100" placeholder="Samples" class="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" />
      <button type="button" onclick={() => void addVoiceProfile()} disabled={voiceBusy || !voiceName.trim() || !voiceConsent.trim()} class="rounded-lg border border-amber-400/30 px-3 py-1.5 text-[10px] text-amber-200 disabled:opacity-40">Create profile</button>
    </div>
    <input bind:value={voiceSamplePaths} placeholder="Reference sample paths (comma-separated, server-local)" class="mt-2 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" />
    {#if voiceError}<p class="mt-2 text-[10px] text-rose-300">{voiceError}</p>{/if}
    {#if voiceProfiles.length}
      <ul class="mt-2 space-y-1">
        {#each voiceProfiles as profile (profile.id)}
          <li class="flex items-center justify-between gap-2 rounded-lg border border-white/5 bg-black/20 px-2 py-1 text-[10px] text-neutral-400">
            <span class="truncate">{profile.name} · {profile.sample_count} sample(s) · consent {profile.consent_ref}{#if profile.provider_voice_id} · clone {profile.provider_voice_id}{/if}</span>
            <button type="button" onclick={() => void removeVoiceProfile(profile)} class="text-rose-300">Delete</button>
          </li>
        {/each}
      </ul>
    {/if}
  </div>

  {#if loading}
    <div class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4 text-xs text-neutral-500">Reading capabilities…</div>
  {:else if response}
    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 class="text-xs font-semibold text-neutral-100">Configured providers</h3>
          <p class="mt-1 text-[10px] text-neutral-500">Saved in providers.json. The default provider is tried first; fallbacks are tried in order. Secrets: {secretBackend || "environment or keyring"}.</p>
        </div>
        <div class="flex items-center gap-2">
          {#if providerMessage}<span class="text-[10px] text-emerald-300">{providerMessage}</span>{/if}
          <button type="button" onclick={newProvider} class="rounded-lg border border-sky-500/40 px-3 py-1 text-[10px] text-sky-200">Add provider</button>
        </div>
      </div>

      <div class="mt-3 grid gap-3 lg:grid-cols-2">
        {#each capabilities as capability}
          <div class="rounded-xl border border-neutral-800 bg-neutral-950/40 p-3">
            <div class="flex items-center justify-between gap-2">
              <h4 class="text-[10px] font-semibold uppercase tracking-wide text-neutral-500">{capability}</h4>
              <span class="text-[9px] text-neutral-600">{(fallbacks[capability] ?? []).length} in chain</span>
            </div>
            <div class="mt-2 space-y-1">
              {#each (fallbacks[capability] ?? []) as provider}
                <div class="flex items-center gap-1.5 rounded bg-neutral-900/70 px-2 py-1">
                  <span class="min-w-0 flex-1 truncate text-[10px] text-neutral-300">{provider.name}</span>
                  <span class="rounded bg-emerald-500/10 px-1.5 py-0.5 text-[8px] uppercase text-emerald-300">{provider.is_default ? "default" : "fallback"}</span>
                  <button type="button" onclick={() => editProvider(provider)} class="rounded px-1 text-[9px] text-sky-300">edit</button>
                </div>
              {/each}
              {#if !(fallbacks[capability] ?? []).length}<p class="text-[10px] text-neutral-600">No enabled provider.</p>{/if}
            </div>
          </div>
        {/each}
      </div>

      {#if providers.length}
        <div class="mt-3 space-y-1">
          {#each providers as provider}
            <div class="flex flex-wrap items-center gap-2 rounded-lg border border-neutral-800 bg-neutral-950/50 px-2 py-1.5 text-[10px]">
              <span class="font-mono text-neutral-400">{provider.id}</span>
              <span class="text-neutral-300">{provider.name}</span>
              <span class="rounded bg-neutral-800 px-1.5 py-0.5 text-[8px] uppercase text-neutral-400">{provider.capability}</span>
              {#if !provider.enabled}<span class="text-[8px] uppercase text-neutral-600">disabled</span>{/if}
              {#if provider.configured === false}
                <span class="text-[8px] uppercase text-amber-300">missing {provider.missing?.join(", ") || "config"}</span>
              {:else}
                <span class="text-[8px] uppercase text-emerald-300">ready</span>
              {/if}
              {#if provider.api_key_env}
                <span class={`text-[8px] uppercase ${provider.secret_present ? "text-emerald-300" : "text-amber-300"}`}>{provider.secret_present ? "secret present" : "secret missing"}</span>
              {/if}
              <span class="ml-auto flex gap-1">
                {#if !provider.is_default}
                  <button type="button" onclick={() => void makeDefault(provider.id)} disabled={Boolean(providerBusy)} class="rounded border border-neutral-700 px-1.5 py-0.5 text-[9px] text-neutral-300 disabled:opacity-40">default</button>
                {/if}
                <button type="button" onclick={() => void testSavedProvider(provider)} disabled={Boolean(providerBusy)} class="rounded border border-emerald-500/30 px-1.5 py-0.5 text-[9px] text-emerald-300 disabled:opacity-40">test</button>
                <button type="button" onclick={() => editProvider(provider)} class="rounded border border-neutral-700 px-1.5 py-0.5 text-[9px] text-sky-300">edit</button>
                <button type="button" onclick={() => void removeProvider(provider.id)} disabled={Boolean(providerBusy)} class="rounded border border-rose-500/30 px-1.5 py-0.5 text-[9px] text-rose-300 disabled:opacity-40">remove</button>
              </span>
              {#if providerTests[provider.id]}
                <span class={`w-full text-[9px] ${providerTests[provider.id].ok ? "text-emerald-300" : "text-rose-300"}`}>
                  {providerTests[provider.id].ok ? "chat OK" : "test failed"} · HTTP {providerTests[provider.id].status_code ?? "—"} · {providerTests[provider.id].latency_ms ?? "—"} ms · {providerTests[provider.id].message}
                </span>
                {#if providerTests[provider.id].hint}
                  <span class="w-full text-[9px] text-neutral-500">{providerTests[provider.id].hint}</span>
                {/if}
              {/if}
              {#if provider.api_key_env}
                <div class="mt-1 flex w-full items-center gap-1">
                  <input
                    type="password"
                    value={secretDrafts[provider.id] ?? ""}
                    oninput={(event) => (secretDrafts = { ...secretDrafts, [provider.id]: event.currentTarget.value })}
                    placeholder={`Set ${provider.api_key_env}`}
                    class="min-w-0 flex-1 rounded border border-neutral-800 bg-neutral-950 px-1.5 py-0.5 font-mono text-[9px] text-neutral-200"
                  />
                  <button type="button" onclick={() => void saveSecret(provider.id)} disabled={Boolean(providerBusy)} class="rounded border border-emerald-500/30 px-1.5 py-0.5 text-[9px] text-emerald-300 disabled:opacity-40">Save secret</button>
                  {#if provider.secret_present}
                    <button type="button" onclick={() => void clearSecret(provider.id)} disabled={Boolean(providerBusy)} class="rounded border border-rose-500/30 px-1.5 py-0.5 text-[9px] text-rose-300 disabled:opacity-40">Clear</button>
                  {/if}
                </div>
              {/if}
            </div>
          {/each}
        </div>
      {/if}

      <details id="provider-editor" class="mt-3 rounded-xl border border-neutral-800 bg-neutral-950/40 p-3" open={editorOpen || !providers.length}>
        <summary class="cursor-pointer text-[11px] font-medium text-neutral-300">{editingProviderId ? `Edit ${editingProviderId}` : "Add a provider"}</summary>
        <div class="mt-2 flex flex-wrap gap-1">
          {#each [
            { label: "DeepSeek", patch: { name: "DeepSeek", capability: "llm" as const, base_url: "https://api.deepseek.com/v1", model: "deepseek-chat", api_key_env: "DEEPSEEK_API_KEY" } },
            { label: "OpenAI", patch: { name: "OpenAI", capability: "llm" as const, base_url: "https://api.openai.com/v1", model: "gpt-4o-mini", api_key_env: "OPENAI_API_KEY" } },
            { label: "Ollama", patch: { name: "Ollama", capability: "llm" as const, base_url: "http://127.0.0.1:11434/v1", model: "qwen2.5:7b-instruct", api_key_env: "VIDEOWFLOW_LLM_API_KEY" } },
            { label: "OpenRouter", patch: { name: "OpenRouter", capability: "llm" as const, base_url: "https://openrouter.ai/api/v1", model: "openai/gpt-4o-mini", api_key_env: "OPENROUTER_API_KEY" } }
          ] as preset}
            <button type="button" onclick={() => applyPreset(preset.patch)} class="rounded border border-neutral-700 px-2 py-1 text-[9px] text-neutral-300 hover:border-sky-500">{preset.label}</button>
          {/each}
        </div>
        <div class="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          <label class="text-[10px] text-neutral-500">ID<input bind:value={draft.id} disabled={Boolean(editingProviderId)} placeholder="ollama-local" class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100 disabled:opacity-60" /></label>
          <label class="text-[10px] text-neutral-500">Name<input bind:value={draft.name} placeholder="Local Ollama" class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Capability
            <select bind:value={draft.capability} class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[10px] text-neutral-100">
              {#each capabilities as capability}<option value={capability}>{capability}</option>{/each}
            </select>
          </label>
          <label class="text-[10px] text-neutral-500 sm:col-span-2">Base URL<input bind:value={draft.base_url} placeholder="http://127.0.0.1:11434/v1" class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Secret env<input bind:value={draft.api_key_env} placeholder="VIDEOWFLOW_LLM_API_KEY" class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
          <p class="text-[9px] text-neutral-500 sm:col-span-2">Name only, for example DEEPSEEK_API_KEY. Paste the key in Secret value.</p>
          <label class="text-[10px] text-neutral-500">Model<input bind:value={draft.model} placeholder="qwen2.5:7b-instruct" class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
          {#if draft.api_key_env}
            <label class="text-[10px] text-neutral-500">Secret value<input type="password" bind:value={secretDraft} placeholder={editingProviderId && draft.secret_present ? "leave blank to keep current" : "paste API key"} class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
          {/if}
          <label class="text-[10px] text-neutral-500">Fallback IDs (comma-separated)<input value={draft.fallback.join(", ")} oninput={(event) => (draft.fallback = event.currentTarget.value.split(",").map((item) => item.trim()).filter(Boolean))} class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
          <div class="flex items-end gap-3 pb-1 text-[10px] text-neutral-400">
            <label class="flex items-center gap-1.5"><input type="checkbox" bind:checked={draft.enabled} class="h-3.5 w-3.5 rounded border-neutral-700 bg-neutral-800" />enabled</label>
            <label class="flex items-center gap-1.5"><input type="checkbox" bind:checked={draft.is_default} class="h-3.5 w-3.5 rounded border-neutral-700 bg-neutral-800" />default</label>
          </div>
        </div>
        <div class="mt-2 flex flex-wrap items-center gap-2">
          <button type="button" onclick={() => void saveDraft()} disabled={providerBusy === "save"} class="rounded-lg border border-sky-500/40 px-3 py-1.5 text-[10px] text-sky-200 disabled:opacity-40">{providerBusy === "save" ? "Saving…" : "Save provider"}</button>
          <select bind:value={testMode} aria-label="Test mode" class="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[10px] text-neutral-300">
            <option value="chat">Test chat</option>
            <option value="models">List models</option>
          </select>
          <button type="button" onclick={() => void testDraft()} disabled={testBusy || !draft.base_url} class="rounded-lg border border-neutral-700 px-3 py-1.5 text-[10px] text-neutral-300 disabled:opacity-40">{testBusy ? "Testing…" : "Test connection"}</button>
          <button type="button" onclick={() => { draft = blankProvider(); editingProviderId = ""; editorOpen = false; secretDraft = ""; }} class="rounded-lg border border-neutral-800 px-3 py-1.5 text-[10px] text-neutral-500">Cancel</button>
        </div>
        {@render providerTestFeedback(draftTestResult, draftTestError)}
      </details>
    </section>

    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 class="text-xs font-semibold text-neutral-100">Implemented surface</h3>
          <p class="mt-1 text-[10px] text-neutral-500">A compact health view. The full API/MCP matrix is developer detail.</p>
        </div>
        <div class="flex flex-wrap gap-1.5 text-[9px] uppercase">
          {#each ["available", "partial", "planned", "blocked"] as status}
            <span class={`rounded-full px-2 py-1 ring-1 ${statusStyles[status]}`}>{status} {counts[status] ?? 0}</span>
          {/each}
        </div>
      </div>
      <button type="button" onclick={() => (catalogOpen = !catalogOpen)} class="mt-3 rounded-lg border border-neutral-700 px-3 py-1.5 text-[10px] text-neutral-300 hover:border-sky-500">
        {catalogOpen ? "Hide capability catalog" : "Show capability catalog"}
      </button>
    </section>

    {#if catalogOpen}
      <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
        <div class="flex flex-wrap gap-2">
          <input bind:value={query} placeholder="Search capabilities…" class="min-w-[200px] flex-1 rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-1.5 text-xs text-neutral-200" />
          <select bind:value={statusFilter} class="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-200">
            <option value="">All statuses</option>
            <option value="available">Available</option>
            <option value="partial">Partial</option>
            <option value="planned">Planned</option>
            <option value="blocked">Blocked</option>
          </select>
        </div>
        <div class="mt-3 grid gap-3 lg:grid-cols-2">
          {#each grouped as group}
            <div class="rounded-xl border border-neutral-800 bg-neutral-950/40 p-3">
              <h3 class="text-[10px] font-semibold uppercase tracking-wide text-neutral-500">{group.category}</h3>
              <div class="mt-2 space-y-2">
                {#each group.items as item}
                  <article class="rounded-lg border border-neutral-800 bg-neutral-900/60 p-2">
                    <div class="flex flex-wrap items-start justify-between gap-2">
                      <p class="text-[11px] font-medium text-neutral-200">{item.name}</p>
                      <span class={`rounded-full px-2 py-0.5 text-[8px] uppercase ring-1 ${statusStyles[item.status] ?? statusStyles.planned}`}>{item.status}</span>
                    </div>
                    <p class="mt-1 text-[10px] leading-4 text-neutral-500">{item.description}</p>
                    {#if item.reason}<p class="mt-1 text-[9px] text-rose-300/80">{item.reason}</p>{/if}
                    <details class="mt-1">
                      <summary class="cursor-pointer text-[9px] text-neutral-600">API / MCP</summary>
                      <p class="mt-1 break-all font-mono text-[9px] text-neutral-600">API {item.api}</p>
                      <p class="break-all font-mono text-[9px] text-neutral-600">MCP {item.mcp}</p>
                    </details>
                  </article>
                {/each}
              </div>
            </div>
          {/each}
        </div>
      </section>
    {/if}
  {/if}
</div>
