<script lang="ts">
  import NodeField from "$lib/nodes/NodeField.svelte";
  import NodePresetBar from "$lib/nodes/NodePresetBar.svelte";
  import { fieldGroups } from "$lib/recipeFields";
  import type { NodeOptions, NodePreset } from "$lib/api";

  let {
    type,
    params,
    schema,
    options = null,
    presets = [],
    errors = {},
    prefix = "",
    showpresets = true,
    query = "",
    onpatch,
    onpickpath,
    onapplypreset,
    onsavepreset,
    onupdatepreset,
    ondeletepreset,
    onfavoritepreset,
    onrenamepreset,
    onduplicatepreset
  }: {
    type: string;
    params: Record<string, unknown>;
    schema: Record<string, unknown>;
    options?: NodeOptions | null;
    presets?: NodePreset[];
    errors?: Record<string, string>;
    prefix?: string;
    showpresets?: boolean;
    query?: string;
    onpatch?: (path: string[], value: unknown) => void;
    onpickpath?: (path: string[]) => void;
    onapplypreset?: (preset: NodePreset) => void;
    onsavepreset?: (name: string) => void;
    onupdatepreset?: (presetId: string) => void;
    ondeletepreset?: (presetId: string) => void;
    onfavoritepreset?: (presetId: string, favorite: boolean) => void;
    onrenamepreset?: (presetId: string, name: string) => void;
    onduplicatepreset?: (presetId: string, name: string) => void;
  } = $props();

  const groups = $derived.by(() => {
    const needle = query.trim().toLowerCase();
    return fieldGroups(schema, params, type)
      .map((group) => ({
        ...group,
        fields: needle
          ? group.fields.filter((field) =>
              `${field.id} ${field.label} ${field.help} ${field.unit}`
                .toLowerCase()
                .includes(needle)
            )
          : group.fields
      }))
      .filter((group) => group.fields.length > 0);
  });
</script>

{#if showpresets}
  <NodePresetBar
    {type}
    presetParams={params}
    {presets}
    {prefix}
    onapply={onapplypreset}
    onsave={onsavepreset}
    onupdate={onupdatepreset}
    ondelete={ondeletepreset}
    onfavorite={onfavoritepreset}
    onrename={onrenamepreset}
    onduplicate={onduplicatepreset}
  />
{/if}

{#if groups.length === 0}
  <p class="text-[10px] text-neutral-500">No simple fields. Use JSON.</p>
{:else}
  {#each groups as group}
    <div class={group.path.length ? "rounded-lg border border-neutral-800/80 p-2" : ""}>
      {#if group.path.length}
        <p class="mb-1 text-[9px] uppercase tracking-wide text-neutral-500">{group.label}</p>
      {/if}
      <div class="space-y-1.5">
        {#each group.fields as field (field.id)}
          <NodeField
            {field}
            {options}
            {prefix}
            error={errors[field.id] ?? ""}
            onchange={(value) => onpatch?.(field.path, value)}
            onpick={onpickpath}
          />
        {/each}
      </div>
    </div>
  {/each}
{/if}
