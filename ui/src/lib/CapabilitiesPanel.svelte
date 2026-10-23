<script lang="ts">
  import ErrorBanner from "$lib/ErrorBanner.svelte";
  import { onMount } from "svelte";
  import {
    deleteProvider,
    errorMessage,
    getCapabilities,
    listProviders,
    saveProvider,
    setDefaultProvider,
    testProvider,
    type Capability,
    type CapabilitiesResponse,
    type ProviderConfig
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
  let testResult = $state<{ ok: boolean; status_code: number | null; message: string; secret_present: boolean } | null>(null);
  let testError = $state("");
  let providers = $state<ProviderConfig[]>([]);
  let fallbacks = $state<Record<string, ProviderConfig[]>>({});
  let providerBusy = $state("");
  let providerMessage = $state("");
  let providerError = $state("");
  let draft = $state<ProviderConfig>(blankProvider());

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
    providerMessage = "";
    providerError = "";
  }

  async function refreshProviders() {
    try {
      const payload = await listProviders();
      providers = payload.providers;
      fallbacks = payload.fallbacks;
    } catch (reason) {
      providerError = errorMessage(reason);
    }
  }

  async function saveDraft() {
    if (!draft.id.trim() || !draft.name.trim()) {
      providerError = "Provider id and name are required.";
      return;
    }
    providerBusy = "save";
    providerError = "";
    providerMessage = "";
    try {
      const saved = await saveProvider({ ...draft, id: draft.id.trim().toLowerCase() });
      providerMessage = `${saved.name} saved.`;
      draft = blankProvider();
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
    testBusy = true;
    testError = "";
    testResult = null;
    try {
      testResult = await testProvider({
        base_url: draft.base_url || testUrl,
        api_key_env: draft.api_key_env || testKeyEnv,
        path: testPath
      });
    } catch (reason) {
      testError = errorMessage(reason);
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
    testBusy = true;
    testError = "";
    testResult = null;
    try {
      testResult = await testProvider({
        base_url: testUrl,
        api_key_env: testKeyEnv,
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
  });
</script>

<div class="space-y-4">
  <ErrorBanner message={error} onDismiss={() => (error = "")} />
  <ErrorBanner message={providerError} title="Provider configuration failed" onDismiss={() => (providerError = "")} testId="provider-error" />
  <div class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h2 class="text-sm font-semibold">Providers and capabilities</h2>
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
    {#if testError}<p class="mt-2 text-[10px] text-rose-300">{testError}</p>{/if}
    {#if testResult}
      <div class={`mt-2 rounded-lg border p-2 text-[10px] ${testResult.ok ? "border-emerald-500/30 bg-emerald-950/20 text-emerald-300" : "border-rose-500/30 bg-rose-950/20 text-rose-300"}`}>
        <p>{testResult.ok ? "Connection OK" : "Connection failed"} · HTTP {testResult.status_code ?? "—"} · secret {testResult.secret_present ? "present" : "missing"}</p>
        {#if testResult.message}<p class="mt-1 break-all font-mono text-[9px] text-neutral-400">{testResult.message}</p>{/if}
      </div>
    {/if}
  </div>

  {#if loading}
    <div class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4 text-xs text-neutral-500">Reading capabilities…</div>
  {:else if response}
    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 class="text-xs font-semibold text-neutral-100">Configured providers</h3>
          <p class="mt-1 text-[10px] text-neutral-500">Saved in providers.json. The default provider is tried first; fallbacks are tried in order.</p>
        </div>
        {#if providerMessage}<span class="text-[10px] text-emerald-300">{providerMessage}</span>{/if}
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
              <span class="ml-auto flex gap-1">
                {#if !provider.is_default}
                  <button type="button" onclick={() => void makeDefault(provider.id)} disabled={Boolean(providerBusy)} class="rounded border border-neutral-700 px-1.5 py-0.5 text-[9px] text-neutral-300 disabled:opacity-40">default</button>
                {/if}
                <button type="button" onclick={() => editProvider(provider)} class="rounded border border-neutral-700 px-1.5 py-0.5 text-[9px] text-sky-300">edit</button>
                <button type="button" onclick={() => void removeProvider(provider.id)} disabled={Boolean(providerBusy)} class="rounded border border-rose-500/30 px-1.5 py-0.5 text-[9px] text-rose-300 disabled:opacity-40">remove</button>
              </span>
            </div>
          {/each}
        </div>
      {/if}

      <details class="mt-3 rounded-xl border border-neutral-800 bg-neutral-950/40 p-3" open={!providers.length}>
        <summary class="cursor-pointer text-[11px] font-medium text-neutral-300">Add or edit a provider</summary>
        <div class="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
          <label class="text-[10px] text-neutral-500">ID<input bind:value={draft.id} placeholder="ollama-local" class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Name<input bind:value={draft.name} placeholder="Local Ollama" class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Capability
            <select bind:value={draft.capability} class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[10px] text-neutral-100">
              {#each capabilities as capability}<option value={capability}>{capability}</option>{/each}
            </select>
          </label>
          <label class="text-[10px] text-neutral-500 sm:col-span-2">Base URL<input bind:value={draft.base_url} placeholder="http://127.0.0.1:11434/v1" class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Secret env<input bind:value={draft.api_key_env} placeholder="VIDEOWFLOW_LLM_API_KEY" class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Model<input bind:value={draft.model} placeholder="qwen2.5:7b-instruct" class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
          <label class="text-[10px] text-neutral-500">Fallback IDs (comma-separated)<input value={draft.fallback.join(", ")} oninput={(event) => (draft.fallback = event.currentTarget.value.split(",").map((item) => item.trim()).filter(Boolean))} class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100" /></label>
          <div class="flex items-end gap-3 pb-1 text-[10px] text-neutral-400">
            <label class="flex items-center gap-1.5"><input type="checkbox" bind:checked={draft.enabled} class="h-3.5 w-3.5 rounded border-neutral-700 bg-neutral-800" />enabled</label>
            <label class="flex items-center gap-1.5"><input type="checkbox" bind:checked={draft.is_default} class="h-3.5 w-3.5 rounded border-neutral-700 bg-neutral-800" />default</label>
          </div>
        </div>
        <div class="mt-2 flex flex-wrap gap-2">
          <button type="button" onclick={() => void saveDraft()} disabled={providerBusy === "save"} class="rounded-lg border border-sky-500/40 px-3 py-1.5 text-[10px] text-sky-200 disabled:opacity-40">{providerBusy === "save" ? "Saving…" : "Save provider"}</button>
          <button type="button" onclick={() => void testDraft()} disabled={testBusy} class="rounded-lg border border-neutral-700 px-3 py-1.5 text-[10px] text-neutral-300 disabled:opacity-40">{testBusy ? "Testing…" : "Test connection"}</button>
          <button type="button" onclick={() => (draft = blankProvider())} class="rounded-lg border border-neutral-800 px-3 py-1.5 text-[10px] text-neutral-500">Clear</button>
        </div>
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
