<script lang="ts">
  type VariableSpec = {
    description?: string;
    required?: boolean;
    type?: string;
    options?: unknown[];
  };

  let {
    variables,
    profiles,
    profile = $bindable(""),
    values
  }: {
    variables: Record<string, VariableSpec>;
    profiles: Record<string, unknown>;
    profile?: string;
    values: Record<string, unknown>;
  } = $props();
</script>

{#if Object.keys(variables).length || Object.keys(profiles).length}
  <div class="mb-3 rounded-xl border border-neutral-800 bg-neutral-950/50 p-3">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <p class="text-[10px] uppercase tracking-wide text-neutral-500">Recipe inputs</p>
      {#if Object.keys(profiles).length}
        <select bind:value={profile} class="rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-200">
          <option value="">no profile</option>
          {#each Object.keys(profiles) as profileOption}<option value={profileOption}>{profileOption}</option>{/each}
        </select>
      {/if}
    </div>
    <div class="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
      {#each Object.entries(variables) as [name, spec]}
        <label class="text-[10px] text-neutral-400" title={spec.description ?? ""}>
          {name}{#if spec.required} *{/if}
          {#if spec.type === "boolean"}
            <input type="checkbox" checked={Boolean(values[name])} onchange={(event) => (values[name] = event.currentTarget.checked)} class="mt-1 block h-4 w-4 rounded border-neutral-700 bg-neutral-950" />
          {:else if spec.type === "number"}
            <input type="number" value={values[name] as number} oninput={(event) => (values[name] = Number(event.currentTarget.value))} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" />
          {:else if spec.type === "enum" && spec.options?.length}
            <select bind:value={values[name]} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100">
              {#each spec.options as option}<option value={String(option)}>{String(option)}</option>{/each}
            </select>
          {:else}
            <input bind:value={values[name]} class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" />
          {/if}
        </label>
      {/each}
    </div>
  </div>
{/if}
