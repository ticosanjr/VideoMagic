<script lang="ts">
  import { installLocalModel, listLocalModels, removeLocalModel, type LocalModel } from "$lib/api";

  let { allowExternal = false }: { allowExternal?: boolean } = $props();
  let models = $state<LocalModel[]>([]);
  let busy = $state("");
  let message = $state("");
  let error = $state("");

  async function refresh() {
    try {
      models = await listLocalModels();
    } catch (reason) {
      error = String(reason instanceof Error ? reason.message : reason);
    }
  }

  async function install(model: LocalModel) {
    busy = model.id;
    error = "";
    message = "";
    try {
      await installLocalModel(model.id, allowExternal);
      message = `${model.label} installed. New jobs can use it immediately.`;
      await refresh();
    } catch (reason) {
      error = String(reason instanceof Error ? reason.message : reason);
    } finally {
      busy = "";
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
  });
</script>

<section class="space-y-3">
  <div class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
    <h2 class="text-sm font-semibold text-neutral-100">Optional models</h2>
    <p class="mt-1 text-xs text-neutral-400">
      The downloadable build ships without large speech weights. Models are fetched on demand,
      checksum-verified, and stored under the portable home directory.
    </p>
    {#if !allowExternal}
      <p class="mt-2 text-[10px] text-amber-300">
        Enable external services in Providers before downloading a model.
      </p>
    {/if}
    {#if message}<p class="mt-2 text-[10px] text-emerald-300">{message}</p>{/if}
    {#if error}<p class="mt-2 text-[10px] text-rose-300">{error}</p>{/if}
  </div>

  <div class="grid gap-2 md:grid-cols-2">
    {#each models as model}
      <article class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
        <div class="flex items-start justify-between gap-3">
          <div>
            <h3 class="text-xs font-semibold text-neutral-100">{model.label}</h3>
            <p class="mt-1 text-[10px] uppercase tracking-wide text-neutral-500">{model.kind} · {model.size_mb} MB</p>
          </div>
          <span class={`rounded-full px-2 py-1 text-[10px] ${model.installed ? "bg-emerald-500/10 text-emerald-300" : "bg-neutral-800 text-neutral-400"}`}>
            {model.installed ? "installed" : "not installed"}
          </span>
        </div>
        <p class="mt-2 break-all font-mono text-[10px] text-neutral-600">{model.path}</p>
        <div class="mt-3 flex gap-2">
          {#if model.installed}
            <button type="button" onclick={() => remove(model)} disabled={busy === model.id} class="rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-1.5 text-[10px] text-rose-200 disabled:opacity-40">
              {busy === model.id ? "Removing…" : "Remove"}
            </button>
          {:else}
            <button type="button" onclick={() => install(model)} disabled={busy === model.id || !allowExternal} class="rounded-lg border border-sky-500/30 bg-sky-500/10 px-3 py-1.5 text-[10px] text-sky-200 disabled:opacity-40">
              {busy === model.id ? "Downloading…" : "Download"}
            </button>
          {/if}
        </div>
      </article>
    {/each}
  </div>
</section>
