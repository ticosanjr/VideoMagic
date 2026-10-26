<script lang="ts">
  import type { NodePreset } from "$lib/api";

  let {
    type,
    presetParams = {},
    presets = [],
    prefix = "",
    onapply,
    onsave,
    onupdate,
    ondelete,
    onfavorite,
    onrename,
    onduplicate
  }: {
    type: string;
    presetParams?: Record<string, unknown>;
    presets?: NodePreset[];
    prefix?: string;
    onapply?: (preset: NodePreset) => void;
    onsave?: (name: string) => void;
    onupdate?: (presetId: string) => void;
    ondelete?: (presetId: string) => void;
    onfavorite?: (presetId: string, favorite: boolean) => void;
    onrename?: (presetId: string, name: string) => void;
    onduplicate?: (presetId: string, name: string) => void;
  } = $props();

  let activePreset = $state<NodePreset | null>(null);
  let presetName = $state("");
  let saveOpen = $state(false);
  let renaming = $state(false);
  let renameValue = $state("");

  const diffKeys = $derived.by(() => {
    const preset = activePreset;
    if (!preset) return [];
    return Object.keys(preset.params).filter(
      (key) =>
        JSON.stringify(presetParams[key]) !== JSON.stringify(preset.params[key])
    );
  });

  const testId = $derived(`${prefix}presets-${type}`);

  function apply(preset: NodePreset) {
    activePreset = preset;
    onapply?.(preset);
  }
</script>

<div class="rounded-lg border border-neutral-800 bg-neutral-950/40 p-2" data-testid={testId}>
  <div class="flex items-center justify-between gap-1">
    <span class="text-[9px] uppercase tracking-wide text-neutral-500">Presets</span>
    <button
      type="button"
      title="Save the current values as a preset"
      onclick={(event) => { event.stopPropagation(); saveOpen = !saveOpen; }}
      class="text-[9px] text-sky-300"
    >+ Save</button>
  </div>
  {#if presets.length}
    <div class="mt-1 flex flex-wrap gap-1">
      {#each presets as preset (preset.id)}
        <span class={`inline-flex items-center rounded border ${activePreset?.id === preset.id ? "border-sky-400/50 bg-sky-500/10" : "border-neutral-700"}`}>
          <button
            type="button"
            title={`Apply ${preset.name}`}
            onclick={(event) => { event.stopPropagation(); apply(preset); }}
            class="px-1.5 py-0.5 text-[9px] text-neutral-300 hover:text-sky-200"
          >{preset.name}</button>
          <button
            type="button"
            aria-label={`Favorite ${preset.name}`}
            title={preset.favorite ? "Remove from favorites" : "Add to favorites"}
            onclick={(event) => { event.stopPropagation(); onfavorite?.(preset.id, !preset.favorite); }}
            class={`px-0.5 text-[9px] ${preset.favorite ? "text-amber-300" : "text-neutral-600"}`}
          >★</button>
          {#if !preset.builtin}
            <button
              type="button"
              aria-label={`Delete ${preset.name}`}
              title="Delete this preset"
              onclick={(event) => { event.stopPropagation(); ondelete?.(preset.id); }}
              class="px-0.5 text-[9px] text-rose-300"
            >×</button>
          {/if}
        </span>
      {/each}
    </div>
    {#if activePreset}
      <div class="mt-1 flex flex-wrap items-center gap-2 text-[9px]">
        {#if !activePreset.builtin}
          <button
            type="button"
            title="Overwrite the preset with the current values"
            onclick={(event) => { event.stopPropagation(); onupdate?.(activePreset!.id); }}
            class="text-emerald-300"
          >Update</button>
          <button
            type="button"
            title="Rename this preset"
            onclick={(event) => { event.stopPropagation(); renaming = !renaming; renameValue = activePreset!.name; }}
            class="text-sky-300"
          >Rename</button>
        {/if}
        <button
          type="button"
          title="Create a copy of this preset"
          onclick={(event) => { event.stopPropagation(); onduplicate?.(activePreset!.id, `${activePreset!.name} copy`); }}
          class="text-neutral-300"
        >Duplicate</button>
        {#if diffKeys.length}
          <span class="text-amber-300" title={diffKeys.join(", ")}>{diffKeys.length} value{diffKeys.length === 1 ? "" : "s"} differ</span>
        {:else}
          <span class="text-neutral-600">matches current values</span>
        {/if}
      </div>
      {#if renaming && !activePreset.builtin}
        <span class="mt-1 flex gap-1">
          <input
            bind:value={renameValue}
            aria-label="Preset name"
            class="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-950 px-1.5 py-0.5 text-[9px] text-neutral-200"
          />
          <button
            type="button"
            onclick={(event) => { event.stopPropagation(); onrename?.(activePreset!.id, renameValue); renaming = false; }}
            class="rounded border border-sky-500/40 px-1.5 text-[9px] text-sky-200"
          >Save</button>
        </span>
      {/if}
    {/if}
  {:else}
    <p class="mt-1 text-[9px] text-neutral-600">No presets for this step yet.</p>
  {/if}
  {#if saveOpen}
    <span class="mt-1 flex gap-1">
      <input
        bind:value={presetName}
        placeholder="Preset name"
        aria-label="Preset name"
        onclick={(event) => event.stopPropagation()}
        class="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-950 px-1.5 py-0.5 text-[9px] text-neutral-200"
      />
      <button
        type="button"
        onclick={(event) => { event.stopPropagation(); onsave?.(presetName); presetName = ""; saveOpen = false; }}
        class="rounded border border-sky-500/40 px-1.5 text-[9px] text-sky-200"
      >Save</button>
    </span>
  {/if}
</div>
