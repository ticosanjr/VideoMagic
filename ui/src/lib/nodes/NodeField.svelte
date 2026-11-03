<script lang="ts">
  import HelpTip from "$lib/HelpTip.svelte";
  import {
    validateField,
    type RecipeField
  } from "$lib/recipeFields";
  import type { NodeOptions } from "$lib/api";

  let {
    field,
    error = "",
    options = null,
    prefix = "",
    onchange,
    onpick
  }: {
    field: RecipeField;
    error?: string;
    options?: NodeOptions | null;
    prefix?: string;
    onchange: (value: unknown) => void;
    onpick?: (path: string[]) => void;
  } = $props();

  let jsonDraft = $state("");
  let jsonError = $state("");
  let jsonFocused = $state(false);

  const testId = $derived(`${prefix}field-${field.id}`);
  const displayError = $derived(error || jsonError || validateField(field));

  $effect(() => {
    if (jsonFocused) return;
    if (field.control === "json") {
      jsonDraft = field.value === undefined || field.value === null
        ? ""
        : JSON.stringify(field.value, null, 2);
    }
  });

  function displayValue(): string {
    if (field.value === undefined || field.value === null) return "";
    return String(field.value);
  }

  function values(): string[] {
    return Array.isArray(field.value)
      ? field.value.map((item) => String(item))
      : [];
  }

  function change(raw: string | boolean) {
    let value: unknown = raw;
    if (field.kind === "number") {
      value = raw === "" ? undefined : Number(raw);
    }
    onchange(value);
  }

  function changeJson(raw: string) {
    jsonDraft = raw;
    try {
      const parsed = JSON.parse(raw);
      jsonError = "";
      onchange(parsed);
    } catch {
      jsonError = "Invalid JSON";
    }
  }

  function toggleChip(option: string) {
    const current = values();
    onchange(
      current.includes(option)
        ? current.filter((item) => item !== option)
        : [...current, option]
    );
  }

  function resetField() {
    onchange(field.defaultValue);
  }

  function changed(): boolean {
    return JSON.stringify(field.value) !== JSON.stringify(field.defaultValue);
  }

  function dynamicOptions(): Array<{ value: string; label: string }> {
    if (!field.optionsSource || !options) return [];
    const [kind, capability] = field.optionsSource.split(":");
    if (kind === "providers") {
      return (options.providers[capability] ?? [])
        .filter(
          (provider) =>
            provider.enabled !== false && provider.configured !== false
        )
        .map((provider) => ({
          value: provider.id,
          label: `${provider.name}${provider.is_default ? " · default" : ""}`
        }));
    }
    if (kind === "services") {
      return options.services.map((service) => ({
        value: service.id,
        label: service.name
      }));
    }
    return [];
  }
</script>

<label class="block text-[10px] text-neutral-400">
  <span class="flex items-center gap-1">
    {field.label}
    {#if field.unit}<span class="text-neutral-600">({field.unit})</span>{/if}
    {#if field.required}<span class="text-rose-300">*</span>{/if}
    {#if field.help}<HelpTip label={field.label} body={field.help} />{/if}
  </span>

  {#if field.control === "switch"}
    <button
      type="button"
      role="switch"
      aria-checked={field.value === true}
      aria-label={field.label}
      data-testid={testId}
      onclick={(event) => { event.preventDefault(); change(!(field.value === true)); }}
      class={`mt-1 inline-flex h-5 w-9 items-center rounded-full border transition ${field.value === true ? "border-sky-400 bg-sky-500/40" : "border-neutral-700 bg-neutral-900"}`}
    >
      <span class={`h-3.5 w-3.5 rounded-full bg-white transition ${field.value === true ? "translate-x-4" : "translate-x-0.5"}`}></span>
    </button>
  {:else if field.control === "segmented"}
    <span class="mt-1 flex flex-wrap gap-1" data-testid={testId}>
      {#each field.options as option}
        <button
          type="button"
          onclick={(event) => { event.preventDefault(); change(option); }}
          class={String(field.value) === option ? "rounded-md bg-sky-500/20 px-2 py-1 text-[10px] text-sky-200 ring-1 ring-inset ring-sky-400/30" : "rounded-md border border-neutral-700 px-2 py-1 text-[10px] text-neutral-400 hover:text-neutral-200"}
        >{option}</button>
      {/each}
    </span>
  {:else if field.control === "select"}
    <select
      data-testid={testId}
      value={displayValue()}
      onchange={(event) => change(event.currentTarget.value)}
      class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100"
    >
      {#if !field.required}<option value="">—</option>{/if}
      {#if field.optionsSource}
        {#if displayValue() && !dynamicOptions().some((option) => option.value === displayValue())}
          <option value={displayValue()}>{displayValue()} · not configured</option>
        {/if}
        {#each dynamicOptions() as option}
          <option value={option.value}>{option.label}</option>
        {/each}
      {:else}
        {#each field.options as option}<option value={option}>{option}</option>{/each}
      {/if}
    </select>
    {#if field.optionsSource && dynamicOptions().length === 0}
      <span class="mt-1 block text-[9px] text-amber-300" data-testid={`${testId}-setup`}>
        No configured {field.optionsSource.split(":")[1].toUpperCase()} provider.
        <a href="#setup/providers" class="underline hover:text-amber-100">Configure in Providers</a>.
      </span>
    {/if}
  {:else if field.control === "slider"}
    <span class="mt-1 flex items-center gap-2">
      <input
        data-testid={testId}
        type="range"
        min={field.minimum}
        max={field.maximum}
        step={field.step ?? 1}
        value={displayValue()}
        oninput={(event) => change(event.currentTarget.value)}
        class="min-w-0 flex-1 accent-sky-500"
      />
      <input
        type="number"
        min={field.minimum}
        max={field.maximum}
        step={field.step ?? 1}
        value={displayValue()}
        oninput={(event) => change(event.currentTarget.value)}
        class="w-16 rounded border border-neutral-700 bg-neutral-950 px-1.5 py-1 text-right font-mono text-[10px] text-neutral-100"
      />
      {#if field.unit}<span class="text-[9px] text-neutral-500">{field.unit}</span>{/if}
    </span>
  {:else if field.control === "multi"}
    <details class="mt-1 rounded border border-neutral-700 bg-neutral-950" data-testid={testId}>
      <summary class="cursor-pointer px-2 py-1 text-[11px] text-neutral-200">
        {values().length ? `${values().length} selected` : "Choose…"}
      </summary>
      <div class="max-h-44 space-y-1 overflow-auto border-t border-neutral-800 p-2">
        <div class="mb-1 flex gap-1">
          <button type="button" onclick={(event) => { event.preventDefault(); onchange([...field.itemOptions]); }} class="rounded border border-emerald-500/30 px-1.5 py-0.5 text-[9px] text-emerald-200">Select all</button>
          <button type="button" onclick={(event) => { event.preventDefault(); onchange([]); }} class="rounded border border-neutral-700 px-1.5 py-0.5 text-[9px] text-neutral-400">Clear</button>
        </div>
        {#each field.itemOptions as option}
          <label class="flex cursor-pointer items-center gap-2 rounded px-1 py-0.5 text-[10px] text-neutral-300 hover:bg-white/5">
            <input
              type="checkbox"
              checked={values().includes(option)}
              onchange={(event) => {
                const current = values();
                onchange(
                  event.currentTarget.checked
                    ? [...current.filter((item) => item !== option), option]
                    : current.filter((item) => item !== option)
                );
              }}
              class="h-3 w-3 rounded border-neutral-700 bg-neutral-900"
            />
            {option}
          </label>
        {/each}
      </div>
    </details>
  {:else if field.control === "chips"}
    <span class="mt-1 flex flex-wrap gap-1" data-testid={testId}>
      {#if field.itemOptions.length}
        {#each field.itemOptions as option}
          <button
            type="button"
            onclick={(event) => { event.preventDefault(); toggleChip(option); }}
            class={values().includes(option) ? "rounded-full bg-emerald-500/15 px-2 py-1 text-[10px] text-emerald-200 ring-1 ring-inset ring-emerald-400/30" : "rounded-full border border-neutral-700 px-2 py-1 text-[10px] text-neutral-400 hover:text-neutral-200"}
          >{option}</button>
        {/each}
      {:else}
        <input
          type="text"
          value={values().join(", ")}
          placeholder={field.placeholder}
          oninput={(event) => onchange(event.currentTarget.value.split(",").map((item) => item.trim()).filter(Boolean))}
          class="w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100"
        />
      {/if}
    </span>
  {:else if field.control === "number"}
    <input
      data-testid={testId}
      type="number"
      min={field.minimum}
      max={field.maximum}
      step={field.step}
      value={displayValue()}
      oninput={(event) => change(event.currentTarget.value)}
      class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100"
    />
  {:else if field.control === "json"}
    <textarea
      data-testid={testId}
      rows="3"
      value={jsonDraft}
      onfocus={() => (jsonFocused = true)}
      onblur={() => { jsonFocused = false; }}
      oninput={(event) => changeJson(event.currentTarget.value)}
      class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 p-2 font-mono text-[10px] text-neutral-100"
    ></textarea>
  {:else if field.control === "path"}
    <span class="mt-1 flex gap-1">
      <input
        data-testid={testId}
        type="text"
        value={displayValue()}
        placeholder={field.placeholder}
        oninput={(event) => change(event.currentTarget.value)}
        class="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[10px] text-neutral-100"
      />
      <button
        type="button"
        aria-label={`Browse ${field.label}`}
        title="Choose a path"
        onclick={(event) => { event.preventDefault(); onpick?.(field.path); }}
        class="rounded border border-neutral-700 px-1.5 text-[10px] text-neutral-300 hover:border-sky-500"
      >…</button>
    </span>
  {:else if field.control === "color"}
    <span class="mt-1 flex gap-1">
      <input
        data-testid={testId}
        type="color"
        value={displayValue() || "#FFFFFF"}
        oninput={(event) => change(event.currentTarget.value.toUpperCase())}
        class="h-7 w-9 rounded border border-neutral-700 bg-neutral-950"
      />
      <input
        type="text"
        value={displayValue()}
        oninput={(event) => change(event.currentTarget.value)}
        class="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[10px] text-neutral-100"
      />
    </span>
  {:else}
    <input
      data-testid={testId}
      type="text"
      value={displayValue()}
      placeholder={field.placeholder}
      oninput={(event) => change(event.currentTarget.value)}
      class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100"
    />
  {/if}

  {#if changed()}
    <button
      type="button"
      onclick={(event) => { event.preventDefault(); resetField(); }}
      class="mt-0.5 text-[9px] text-neutral-500 hover:text-sky-300"
    >Reset to default</button>
  {/if}
  {#if displayError}
    <span class="mt-0.5 block text-[9px] text-rose-300">{displayError}</span>
  {/if}
</label>
