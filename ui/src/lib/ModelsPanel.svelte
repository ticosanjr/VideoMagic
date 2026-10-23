<script lang="ts">
  import ErrorBanner from "$lib/ErrorBanner.svelte";
  import {
    cancelModelDownload,
    listLocalModels,
    listModelDownloads,
    removeLocalModel,
    startModelDownload,
    type LocalModel,
    type ModelDownload
  } from "$lib/api";

  let models = $state<LocalModel[]>([]);
  let busy = $state("");
  let message = $state("");
  let error = $state("");
  let downloads = $state<Record<string, ModelDownload>>({});
  let poll: ReturnType<typeof setInterval> | undefined;

  const grouped = $derived(
    Object.entries(
      models.reduce<Record<string, LocalModel[]>>((groups, model) => {
        const key = model.capability || "other";
        (groups[key] ??= []).push(model);
        return groups;
      }, {})
    ).sort(([left], [right]) => left.localeCompare(right))
  );

  const installedSize = $derived(
    models.filter((model) => model.installed).reduce((total, model) => total + model.size_mb, 0)
  );

  async function refresh() {
    try {
      models = await listLocalModels();
      const items = await listModelDownloads();
      downloads = items.reduce<Record<string, ModelDownload>>((result, item) => {
        result[item.model_id] = item;
        return result;
      }, {});
    } catch (reason) {
      error = String(reason instanceof Error ? reason.message : reason);
    }
  }

  function activeDownload(modelId: string): ModelDownload | undefined {
    const item = downloads[modelId];
    return item && (item.status === "queued" || item.status === "downloading") ? item : undefined;
  }

  function schedulePoll() {
    clearInterval(poll);
    poll = setInterval(async () => {
      await refresh();
      const running = Object.values(downloads).some(
        (item) => item.status === "queued" || item.status === "downloading"
      );
      if (!running) clearInterval(poll);
    }, 900);
  }

  async function install(model: LocalModel) {
    busy = model.id;
    error = "";
    message = "";
    try {
      const download = await startModelDownload(model.id);
      downloads = { ...downloads, [model.id]: download };
      message = `Downloading ${model.label}…`;
      schedulePoll();
    } catch (reason) {
      error = String(reason instanceof Error ? reason.message : reason);
    } finally {
      busy = "";
    }
  }

  async function cancel(model: LocalModel) {
    try {
      await cancelModelDownload(model.id);
      message = `Cancelling ${model.label}…`;
    } catch (reason) {
      error = String(reason instanceof Error ? reason.message : reason);
    }
  }

  async function remove(model: LocalModel) {
    busy = model.id;
    error = "";
    message = "";
    try {
      await removeLocalModel(model.id);
      message = `${model.label} removed.`;
      await refresh();
    } catch (reason) {
      error = String(reason instanceof Error ? reason.message : reason);
    } finally {
      busy = "";
    }
  }

  $effect(() => {
    void refresh();
    return () => clearInterval(poll);
  });
</script>

<div class="space-y-4">
  <ErrorBanner message={error} onDismiss={() => (error = "")} />
  <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 class="text-sm font-semibold text-neutral-100">Local models</h2>
        <p class="mt-1 max-w-2xl text-xs leading-5 text-neutral-400">
          Explicit, optional downloads grouped by capability. Model downloads are independent
          from the external-provider policy; weights are stored under the VideoFlow home.
        </p>
      </div>
      <div class="flex gap-2 text-[10px] text-neutral-500">
        <span class="rounded-full bg-white/5 px-2 py-1">{models.filter((m) => m.installed).length} installed</span>
        <span class="rounded-full bg-white/5 px-2 py-1">{installedSize} MB</span>
      </div>
    </div>
    {#if message}<p class="mt-2 text-[10px] text-emerald-300">{message}</p>{/if}
  </section>

  {#each grouped as [capability, items]}
    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4">
      <div class="flex items-center justify-between">
        <h3 class="text-[11px] font-semibold uppercase tracking-wide text-neutral-500">{capability}</h3>
        <span class="text-[10px] text-neutral-600">{items.length} model(s)</span>
      </div>
      <div class="mt-3 space-y-2">
        {#each items as model}
          {@const download = downloads[model.id]}
          <article class="rounded-xl border border-neutral-800 bg-neutral-950/50 p-3">
            <div class="flex flex-wrap items-start justify-between gap-3">
              <div class="min-w-0">
                <div class="flex flex-wrap items-center gap-2">
                  <h4 class="text-xs font-medium text-neutral-100">{model.label}</h4>
                  <span class={`rounded-full px-2 py-0.5 text-[9px] uppercase ${model.installed ? "bg-emerald-500/10 text-emerald-300" : "bg-neutral-800 text-neutral-400"}`}>
                    {model.installed ? "installed" : "not installed"}
                  </span>
                </div>
                <p class="mt-1 text-[10px] text-neutral-500">
                  {model.kind} · {model.size_mb} MB · {model.license || "license unknown"}
                </p>
                <p class="mt-1 text-[10px] text-neutral-600">
                  Used by: <span class="font-mono text-neutral-400">{model.used_by.join(", ") || "—"}</span>
                </p>
                <p class="mt-1 break-all font-mono text-[9px] text-neutral-600" title={model.path}>{model.path}</p>
              </div>
              <div class="flex items-center gap-2">
                {#if activeDownload(model.id)}
                  <button type="button" onclick={() => void cancel(model)} class="rounded-lg border border-rose-500/30 px-2.5 py-1.5 text-[10px] text-rose-200">Cancel</button>
                {:else}
                  <button
                    type="button"
                    onclick={() => void (model.installed ? remove(model) : install(model))}
                    disabled={busy === model.id}
                    class={`rounded-lg border px-3 py-1.5 text-[10px] disabled:opacity-40 ${model.installed ? "border-rose-500/30 bg-rose-500/10 text-rose-200" : "border-sky-500/30 bg-sky-500/10 text-sky-200"}`}
                  >
                    {busy === model.id ? "Starting…" : model.installed ? "Remove" : "Download"}
                  </button>
                {/if}
              </div>
            </div>
            {#if download && download.status !== "installed"}
              <div class="mt-2">
                <div class="flex items-center justify-between text-[9px] text-neutral-500">
                  <span>{download.message || download.status}</span>
                  <span>{download.percent}%</span>
                </div>
                <div class="mt-1 h-1.5 overflow-hidden rounded-full bg-neutral-800">
                  <div class={`h-full rounded-full ${download.status === "failed" ? "bg-rose-400" : download.status === "cancelled" ? "bg-neutral-500" : "bg-sky-400"}`} style={`width:${download.percent}%`}></div>
                </div>
                {#if download.error}<p class="mt-1 break-all text-[9px] text-rose-300">{download.error}</p>{/if}
              </div>
            {/if}
          </article>
        {/each}
      </div>
    </section>
  {/each}
</div>
