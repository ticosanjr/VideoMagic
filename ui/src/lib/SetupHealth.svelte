<script lang="ts">
  import { onMount } from "svelte";
  import Icon from "$lib/ui/Icon.svelte";
  import {
    getSystem,
    listLocalModels,
    listProviders,
    listServices,
    type LocalModel,
    type ProviderConfig,
    type ServicesResponse,
    type SystemInfo
  } from "$lib/api";

  let system = $state<SystemInfo | null>(null);
  let providers = $state<ProviderConfig[]>([]);
  let models = $state<LocalModel[]>([]);
  let services = $state<ServicesResponse | null>(null);

  const readyProviders = $derived(
    providers.filter((item) => item.enabled && Boolean(item.base_url)).length
  );
  const readyModels = $derived(models.filter((item) => item.installed).length);
  const runningServices = $derived(
    services?.services?.filter((item) => item.current || item.pid > 0).length ?? 0
  );

  onMount(() => {
    void Promise.all([
      getSystem().then((value) => (system = value)).catch(() => null),
      listProviders().then((value) => (providers = value?.providers ?? [])).catch(() => []),
      listLocalModels().then((value) => (models = value ?? [])).catch(() => []),
      listServices().then((value) => (services = value)).catch(() => null)
    ]);
  });

  function go(tab: string) {
    window.location.hash = `#${tab}`;
  }
</script>

<section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4" data-testid="setup-health">
  <div class="flex flex-wrap items-start justify-between gap-3">
    <div>
      <p class="vf-label text-sky-300/80">Setup</p>
      <h2 class="mt-1 text-[length:var(--vf-text-lg)] font-semibold text-white">Setup health</h2>
      <p class="mt-1 text-[length:var(--vf-text-xs)] text-neutral-500">The four checks that block a first recipe run.</p>
    </div>
    <button type="button" onclick={() => void Promise.all([getSystem(), listProviders(), listLocalModels(), listServices()]).then(([s, p, m, sv]) => { system = s; providers = p?.providers ?? []; models = m ?? []; services = sv; }).catch(() => {})} class="rounded-lg border border-neutral-700 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-neutral-300">Refresh</button>
  </div>

  <div class="mt-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
    <button type="button" onclick={() => go("settings")} class="rounded-xl border border-white/10 bg-white/[0.03] p-3 text-left transition-colors hover:border-sky-500/40">
      <div class="flex items-center justify-between gap-2">
        <p class="vf-label">FFmpeg</p>
        <Icon name={system?.ffmpeg ? "check" : "close"} size={14} class={system?.ffmpeg ? "text-emerald-300" : "text-rose-300"} />
      </div>
      <p class="mt-1 text-[length:var(--vf-text-xs)] text-neutral-300">{system?.ffmpeg ? "Ready" : "Missing"}</p>
    </button>
    <button type="button" onclick={() => go("providers")} class="rounded-xl border border-white/10 bg-white/[0.03] p-3 text-left transition-colors hover:border-sky-500/40">
      <div class="flex items-center justify-between gap-2">
        <p class="vf-label">Providers</p>
        <Icon name={readyProviders ? "check" : "warning"} size={14} class={readyProviders ? "text-emerald-300" : "text-amber-300"} />
      </div>
      <p class="mt-1 text-[length:var(--vf-text-xs)] text-neutral-300">{readyProviders} ready · {providers.length} configured</p>
    </button>
    <button type="button" onclick={() => go("models")} class="rounded-xl border border-white/10 bg-white/[0.03] p-3 text-left transition-colors hover:border-sky-500/40">
      <div class="flex items-center justify-between gap-2">
        <p class="vf-label">Models</p>
        <Icon name={readyModels ? "check" : "cpu"} size={14} class={readyModels ? "text-emerald-300" : "text-neutral-400"} />
      </div>
      <p class="mt-1 text-[length:var(--vf-text-xs)] text-neutral-300">{readyModels} installed</p>
    </button>
    <button type="button" onclick={() => go("services")} class="rounded-xl border border-white/10 bg-white/[0.03] p-3 text-left transition-colors hover:border-sky-500/40">
      <div class="flex items-center justify-between gap-2">
        <p class="vf-label">Services</p>
        <Icon name={runningServices ? "check" : "server"} size={14} class={runningServices ? "text-emerald-300" : "text-neutral-400"} />
      </div>
      <p class="mt-1 text-[length:var(--vf-text-xs)] text-neutral-300">{runningServices} running</p>
    </button>
  </div>
</section>
