<script lang="ts">
  import { Handle, Position } from "@xyflow/svelte";
  import {
    fieldGroups,
    validateField,
    type RecipeField
  } from "$lib/recipeFields";
  import HelpTip from "$lib/HelpTip.svelte";
  import type { NodeOptions, NodePreset, StepPort } from "$lib/api";

  let {
    data,
    selected = false
  }: {
    data: {
      title: string;
      type: string;
      description?: string;
      params: Record<string, unknown>;
      schema?: Record<string, unknown>;
      status?: "idle" | "queued" | "running" | "cached" | "executed" | "failed" | "skipped";
      implementation?: "available" | "partial" | "planned";
      icon?: string;
      color?: string;
      progress?: number;
      expanded?: boolean;
      pinned?: boolean;
      width?: number;
      inputs?: Record<string, string>;
      inputPorts?: StepPort[];
      outputPorts?: StepPort[];
      mediaOverride?: string;
      outputMode?: "pipeline" | "folder";
      outputDir?: string;
      onStepPatch?: (
        key: "media_override" | "output_mode" | "output_dir",
        value: unknown
      ) => void;
      onPickStepPath?: (key: "media_override" | "output_dir") => void;
      presets?: NodePreset[];
      options?: NodeOptions | null;
      onApplyPreset?: (preset: NodePreset) => void;
      onSavePreset?: (name: string) => void;
      onUpdatePreset?: (presetId: string) => void;
      onDeletePreset?: (presetId: string) => void;
      onFavoritePreset?: (presetId: string, favorite: boolean) => void;
      errors?: Record<string, string>;
      onSelect?: () => void;
      onToggle?: () => void;
      onPin?: () => void;
      onWidth?: () => void;
      onResize?: (width: number) => void;
      onPatch?: (path: string[], value: unknown) => void;
      onPatchMany?: (patch: Record<string, unknown>) => void;
      onPickPath?: (path: string[]) => void;
      onRun?: () => void;
      onDuplicate?: () => void;
      onRemove?: () => void;
      onOpenJson?: () => void;
      onLogs?: () => void;
    };
    selected?: boolean;
  } = $props();

  const groups = $derived(
    fieldGroups(data.schema ?? {}, data.params ?? {}, data.type)
  );
  const presets = $derived<NodePreset[]>(data.presets ?? []);
  let activePreset = $state<NodePreset | null>(null);
  let presetName = $state("");
  let savePreset = $state(false);

  function applyPreset(preset: NodePreset) {
    activePreset = preset;
    data.onApplyPreset?.(preset);
  }
  const isMediaNode = $derived(
    data.type === "ingest" ||
      (data.inputPorts ?? []).some((port) => port.id === "media")
  );
  const hasFileOutputs = $derived(
    (data.outputPorts ?? []).some(
      (port) => port.type === "artifact_map" || port.type === "nle_artifacts"
    )
  );
  const mediaValue = $derived(
    data.type === "ingest"
      ? String((data.params ?? {}).source ?? "")
      : data.mediaOverride ?? ""
  );
  const wiredMedia = $derived(Object.keys(data.inputs ?? {}).includes("media"));

  function patchMedia(value: string) {
    if (data.type === "ingest") data.onPatch?.(["source"], value);
    else data.onStepPatch?.("media_override", value);
  }

  function pickMedia() {
    if (data.type === "ingest") data.onPickPath?.(["source"]);
    else data.onPickStepPath?.("media_override");
  }
  let jsonDrafts = $state<Record<string, string>>({});
  let jsonErrors = $state<Record<string, string>>({});
  const status = $derived(data.status ?? "idle");
  const progress = $derived(Math.max(0, Math.min(100, Math.round(data.progress ?? 0))));
  const implementation = $derived(data.implementation ?? "available");
  const iconColor = $derived(data.color ?? "#38bdf8");
  const width = $derived(data.expanded ? Math.max(360, data.width ?? 420) : 230);

  function fieldError(field: RecipeField): string | null {
    return data.errors?.[field.id] ?? validateField(field);
  }

  function change(field: RecipeField, raw: string | boolean | string[]) {
    let value: unknown = raw;
    if (field.kind === "number") {
      value = raw === "" ? undefined : Number(raw);
    }
    data.onPatch?.(field.path, value);
  }

  function dynamicOptions(field: RecipeField): Array<{ value: string; label: string }> {
    if (!field.optionsSource || !data.options) return [];
    const [kind, capability] = field.optionsSource.split(":");
    if (kind === "providers") {
      return (data.options.providers[capability] ?? []).map((provider) => ({
        value: provider.id,
        label: `${provider.name}${provider.is_default ? " · default" : ""}`
      }));
    }
    if (kind === "services") {
      return data.options.services.map((service) => ({
        value: service.id,
        label: service.name
      }));
    }
    return [];
  }

  function displayValue(field: RecipeField): string {
    if (field.value === undefined || field.value === null) {
      return field.control === "json" || field.control === "chips" ? "[]" : "";
    }
    if (field.control === "json" || field.control === "chips") {
      return jsonDrafts[field.id] ?? JSON.stringify(field.value);
    }
    return String(field.value);
  }

  function values(field: RecipeField): string[] {
    return Array.isArray(field.value) ? field.value.map((item) => String(item)) : [];
  }

  function toggleChip(field: RecipeField, option: string) {
    const current = values(field);
    const next = current.includes(option)
      ? current.filter((item) => item !== option)
      : [...current, option];
    data.onPatch?.(field.path, next);
  }

  function resetField(field: RecipeField) {
    data.onPatch?.(field.path, field.defaultValue);
  }

  function changed(field: RecipeField): boolean {
    return JSON.stringify(field.value) !== JSON.stringify(field.defaultValue);
  }

  function changeJson(field: RecipeField, raw: string) {
    jsonDrafts = { ...jsonDrafts, [field.id]: raw };
    try {
      const parsed = JSON.parse(raw);
      jsonErrors = { ...jsonErrors, [field.id]: "" };
      data.onPatch?.(field.path, parsed);
    } catch {
      jsonErrors = { ...jsonErrors, [field.id]: "Invalid JSON" };
    }
  }

</script>

<div
  data-testid={`step-${data.type}`}
  class={`relative rounded-2xl border text-left shadow-xl transition ${implementation === "planned" ? "border-dashed" : ""} ${
    selected
      ? "border-sky-400/70 bg-sky-950/80 ring-2 ring-sky-400/20"
      : status === "failed"
        ? "border-rose-500/60 bg-rose-950/70"
        : status === "running"
          ? "border-amber-400/60 bg-amber-950/40"
          : status === "cached"
            ? "border-emerald-500/50 bg-emerald-950/40"
            : status === "executed"
              ? "border-sky-500/50 bg-sky-950/40"
              : "border-neutral-700 bg-neutral-900/95"
  }`}
  style={`width: ${width}px`}
>
  <Handle type="target" position={Position.Left} class="!h-2.5 !w-2.5 !border-neutral-500 !bg-neutral-800" />
  <div class="px-3 py-2.5">
    <div class="flex items-start justify-between gap-2">
      <div class="min-w-0">
        <div class="flex items-center gap-1.5">
          <span class="text-sm" style={`color:${iconColor}`}>{data.icon ?? "●"}</span>
          <p class="truncate text-xs font-semibold text-neutral-100">{data.title}</p>
          {#if data.description}<HelpTip label={data.title} body={data.description} />{/if}
          {#if implementation !== "available"}
            <span class={`rounded px-1 py-0.5 text-[8px] uppercase ${implementation === "partial" ? "bg-amber-500/10 text-amber-300" : "bg-neutral-700/60 text-neutral-400"}`}>{implementation}</span>
          {/if}
        </div>
        <p class="mt-0.5 truncate font-mono text-[10px] text-sky-300/80">{data.type}</p>
      </div>
      <div class="flex shrink-0 items-center gap-1">
        <button type="button" data-testid={`step-width-${data.type}`} title="Cycle width" onclick={(event) => { event.stopPropagation(); data.onWidth?.(); }} class="rounded px-1 text-[11px] text-neutral-500 hover:text-neutral-200">↔</button>
        <button type="button" data-testid={`step-pin-${data.type}`} title={data.pinned ? "Unpin" : "Pin open"} onclick={(event) => { event.stopPropagation(); data.onPin?.(); }} class={`rounded px-1 text-[11px] ${data.pinned ? "text-amber-300" : "text-neutral-500 hover:text-neutral-200"}`}>⌖</button>
        <button type="button" data-testid={`step-toggle-${data.type}`} title={data.expanded ? "Collapse" : "Expand"} onclick={(event) => { event.stopPropagation(); data.onToggle?.(); }} class="rounded px-1 text-[11px] text-neutral-500 hover:text-neutral-200">{data.expanded ? "▴" : "▾"}</button>
      </div>
    </div>

    <div class="mt-2 flex items-center gap-2">
      <span class={`h-1.5 w-1.5 rounded-full ${
        status === "running" ? "animate-pulse bg-amber-400" :
        status === "skipped" ? "bg-neutral-500" :
        status === "cached" ? "bg-emerald-400" :
        status === "executed" ? "bg-sky-400" :
        status === "failed" ? "bg-rose-400" : "bg-neutral-600"
      }`}></span>
      <span class="text-[9px] uppercase tracking-wide text-neutral-500">{status}</span>
      <span class="ml-auto font-mono text-[9px] text-neutral-400">{progress}%</span>
    </div>
    <div class="mt-1 h-1 overflow-hidden rounded-full bg-neutral-800">
      <div class={`h-full transition-all ${status === "failed" ? "bg-rose-400" : status === "cached" ? "bg-emerald-400" : "bg-sky-400"}`} style={`width: ${progress}%`}></div>
    </div>

    {#if data.expanded}
      <div class="mt-3 space-y-2 border-t border-white/5 pt-2">
        {#if implementation === "planned"}
          <p class="rounded border border-dashed border-neutral-700 bg-neutral-950/60 p-2 text-[10px] text-neutral-400">Not implemented in this build. The recipe runner will bypass this node.</p>
        {/if}
        {#if (data.inputPorts?.length || isMediaNode)}
          <div class="rounded-lg border border-sky-500/15 bg-sky-950/10 p-2" data-testid={`inputs-${data.type}`}>
            <p class="text-[9px] uppercase tracking-wide text-sky-300/80">Inputs</p>
            {#if data.inputPorts?.length}
              <div class="mt-1 flex flex-wrap gap-1">
                {#each data.inputPorts as port}
                  {@const wired = Object.entries(data.inputs ?? {}).find(([key]) => key === port.id)?.[1]}
                  <span class={`rounded border px-1.5 py-0.5 text-[9px] ${wired ? "border-emerald-400/30 text-emerald-200" : "border-neutral-700 text-neutral-500"}`} title={wired ? `from ${wired}` : "Not wired"}>
                    {port.label}{port.required ? " *" : ""}
                  </span>
                {/each}
              </div>
            {/if}
            {#if isMediaNode}
              <div class="mt-2">
                <p class="text-[9px] text-neutral-500">
                  {wiredMedia ? "Media comes from the wired input" : "Choose the media for this node"}
                </p>
                <span class="mt-1 flex gap-1">
                  <input
                    type="text"
                    value={mediaValue}
                    placeholder="/media/source.mp4"
                    oninput={(event) => patchMedia(event.currentTarget.value)}
                    class="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[10px] text-neutral-100"
                  />
                  <button type="button" onclick={(event) => { event.preventDefault(); pickMedia(); }} class="rounded border border-neutral-700 px-1.5 text-[10px] text-neutral-300 hover:border-sky-500">…</button>
                </span>
              </div>
            {/if}
          </div>
        {/if}
        {#if presets.length || groups.length}
          <p class="text-[9px] uppercase tracking-wide text-neutral-500">Config</p>
        {/if}
        <div class="rounded-lg border border-neutral-800 bg-neutral-950/40 p-2" data-testid={`presets-${data.type}`}>
          <div class="flex items-center justify-between gap-1">
            <span class="text-[9px] uppercase tracking-wide text-neutral-500">Presets</span>
            <button type="button" onclick={(event) => { event.stopPropagation(); savePreset = !savePreset; }} class="text-[9px] text-sky-300">+ Save</button>
          </div>
          <div class="mt-1 flex flex-wrap gap-1">
            {#each presets as preset (preset.id)}
              <span class={`inline-flex items-center rounded border ${activePreset?.id === preset.id ? "border-sky-400/50 bg-sky-500/10" : "border-neutral-700"}`}>
                <button type="button" onclick={(event) => { event.stopPropagation(); applyPreset(preset); }} class="px-1.5 py-0.5 text-[9px] text-neutral-300 hover:text-sky-200">{preset.name}</button>
                <button type="button" aria-label={`Favorite ${preset.name}`} onclick={(event) => { event.stopPropagation(); data.onFavoritePreset?.(preset.id, !preset.favorite); }} class={`px-0.5 text-[9px] ${preset.favorite ? "text-amber-300" : "text-neutral-600"}`}>★</button>
                {#if !preset.builtin}
                  <button type="button" aria-label={`Delete ${preset.name}`} onclick={(event) => { event.stopPropagation(); data.onDeletePreset?.(preset.id); }} class="px-0.5 text-[9px] text-rose-300">×</button>
                {/if}
              </span>
            {/each}
          </div>
          {#if activePreset && !activePreset.builtin}
            <button type="button" onclick={(event) => { event.stopPropagation(); data.onUpdatePreset?.(activePreset!.id); }} class="mt-1 text-[9px] text-emerald-300">Update “{activePreset.name}” from current values</button>
          {/if}
          {#if savePreset}
            <span class="mt-1 flex gap-1">
              <input bind:value={presetName} placeholder="Preset name" onclick={(event) => event.stopPropagation()} class="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-950 px-1.5 py-0.5 text-[9px] text-neutral-200" />
              <button type="button" onclick={(event) => { event.stopPropagation(); data.onSavePreset?.(presetName); presetName = ""; savePreset = false; }} class="rounded border border-sky-500/40 px-1.5 text-[9px] text-sky-200">Save</button>
            </span>
          {/if}
        </div>
        {#if groups.length === 0}
          <p class="text-[10px] text-neutral-500">No simple fields. Use JSON.</p>
        {/if}
        {#each groups as group}
          <div class={group.path.length ? "rounded-lg border border-neutral-800/80 p-2" : ""}>
            {#if group.path.length}
              <p class="mb-1 text-[9px] uppercase tracking-wide text-neutral-500">{group.label}</p>
            {/if}
            <div class="space-y-1.5">
              {#each group.fields as field}
                {@const error = jsonErrors[field.id] || fieldError(field)}
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
                      data-testid={`field-${field.id}`}
                      onclick={(event) => { event.preventDefault(); change(field, !(field.value === true)); }}
                      class={`mt-1 inline-flex h-5 w-9 items-center rounded-full border transition ${field.value === true ? "border-sky-400 bg-sky-500/40" : "border-neutral-700 bg-neutral-900"}`}
                    >
                      <span class={`h-3.5 w-3.5 rounded-full bg-white transition ${field.value === true ? "translate-x-4" : "translate-x-0.5"}`}></span>
                    </button>
                  {:else if field.control === "segmented"}
                    <span class="mt-1 flex flex-wrap gap-1" data-testid={`field-${field.id}`}>
                      {#each field.options as option}
                        <button
                          type="button"
                          onclick={(event) => { event.preventDefault(); change(field, option); }}
                          class={String(field.value) === option ? "rounded-md bg-sky-500/20 px-2 py-1 text-[10px] text-sky-200 ring-1 ring-inset ring-sky-400/30" : "rounded-md border border-neutral-700 px-2 py-1 text-[10px] text-neutral-400 hover:text-neutral-200"}
                        >{option}</button>
                      {/each}
                    </span>
                  {:else if field.control === "select"}
                    <select
                      data-testid={`field-${field.id}`}
                      value={displayValue(field)}
                      onchange={(event) => change(field, event.currentTarget.value)}
                      class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100"
                    >
                      {#if !field.required}<option value="">—</option>{/if}
                      {#if field.optionsSource}
                        {#each dynamicOptions(field) as option}
                          <option value={option.value}>{option.label}</option>
                        {/each}
                      {:else}
                        {#each field.options as option}<option value={option}>{option}</option>{/each}
                      {/if}
                    </select>
                  {:else if field.control === "slider"}
                    <span class="mt-1 flex items-center gap-2">
                      <input
                        data-testid={`field-${field.id}`}
                        type="range"
                        min={field.minimum}
                        max={field.maximum}
                        step={field.step ?? 1}
                        value={displayValue(field)}
                        oninput={(event) => change(field, event.currentTarget.value)}
                        class="min-w-0 flex-1 accent-sky-500"
                      />
                      <input
                        type="number"
                        min={field.minimum}
                        max={field.maximum}
                        step={field.step ?? 1}
                        value={displayValue(field)}
                        oninput={(event) => change(field, event.currentTarget.value)}
                        class="w-16 rounded border border-neutral-700 bg-neutral-950 px-1.5 py-1 text-right font-mono text-[10px] text-neutral-100"
                      />
                      {#if field.unit}<span class="text-[9px] text-neutral-500">{field.unit}</span>{/if}
                    </span>
                  {:else if field.control === "chips"}
                    <span class="mt-1 flex flex-wrap gap-1" data-testid={`field-${field.id}`}>
                      {#if field.itemOptions.length}
                        {#each field.itemOptions as option}
                          <button
                            type="button"
                            onclick={(event) => { event.preventDefault(); toggleChip(field, option); }}
                            class={values(field).includes(option) ? "rounded-full bg-emerald-500/15 px-2 py-1 text-[10px] text-emerald-200 ring-1 ring-inset ring-emerald-400/30" : "rounded-full border border-neutral-700 px-2 py-1 text-[10px] text-neutral-400 hover:text-neutral-200"}
                          >{option}</button>
                        {/each}
                      {:else}
                        <input
                          type="text"
                          value={values(field).join(", ")}
                          placeholder={field.placeholder}
                          oninput={(event) => change(field, event.currentTarget.value.split(",").map((item) => item.trim()).filter(Boolean))}
                          class="w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100"
                        />
                      {/if}
                    </span>
                  {:else if field.control === "number"}
                    <input
                      data-testid={`field-${field.id}`}
                      type="number"
                      min={field.minimum}
                      max={field.maximum}
                      step={field.step}
                      value={displayValue(field)}
                      oninput={(event) => change(field, event.currentTarget.value)}
                      class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100"
                    />
                  {:else if field.control === "json"}
                    <textarea
                      data-testid={`field-${field.id}`}
                      rows="3"
                      value={displayValue(field)}
                      oninput={(event) => changeJson(field, event.currentTarget.value)}
                      class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 p-2 font-mono text-[10px] text-neutral-100"
                    ></textarea>
                  {:else if field.control === "path"}
                    <span class="mt-1 flex gap-1">
                      <input
                        data-testid={`field-${field.id}`}
                        type="text"
                        value={displayValue(field)}
                        placeholder={field.placeholder}
                        oninput={(event) => change(field, event.currentTarget.value)}
                        class="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[10px] text-neutral-100"
                      />
                      <button type="button" onclick={(event) => { event.preventDefault(); data.onPickPath?.(field.path); }} class="rounded border border-neutral-700 px-1.5 text-[10px] text-neutral-300 hover:border-sky-500">…</button>
                    </span>
                  {:else if field.control === "color"}
                    <span class="mt-1 flex gap-1">
                      <input
                        data-testid={`field-${field.id}`}
                        type="color"
                        value={displayValue(field) || "#FFFFFF"}
                        oninput={(event) => change(field, event.currentTarget.value.toUpperCase())}
                        class="h-7 w-9 rounded border border-neutral-700 bg-neutral-950"
                      />
                      <input
                        type="text"
                        value={displayValue(field)}
                        oninput={(event) => change(field, event.currentTarget.value)}
                        class="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[10px] text-neutral-100"
                      />
                    </span>
                  {:else}
                    <input
                      data-testid={`field-${field.id}`}
                      type="text"
                      value={displayValue(field)}
                      placeholder={field.placeholder}
                      oninput={(event) => change(field, event.currentTarget.value)}
                      class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100"
                    />
                  {/if}
                  {#if changed(field)}
                    <button type="button" onclick={(event) => { event.preventDefault(); resetField(field); }} class="mt-0.5 text-[9px] text-neutral-500 hover:text-sky-300">Reset to default</button>
                  {/if}
                  {#if error}<span class="mt-0.5 block text-[9px] text-rose-300">{error}</span>{/if}
                </label>
              {/each}
            </div>
          </div>
        {/each}

        {#if data.outputPorts?.length || hasFileOutputs}
          <div class="rounded-lg border border-emerald-500/15 bg-emerald-950/10 p-2" data-testid={`outputs-${data.type}`}>
            <p class="text-[9px] uppercase tracking-wide text-emerald-300/80">Outputs</p>
            {#if data.outputPorts?.length}
              <div class="mt-1 flex flex-wrap gap-1">
                {#each data.outputPorts as port}
                  <span class="rounded border border-emerald-400/25 px-1.5 py-0.5 text-[9px] text-emerald-200" title={port.type}>{port.label}</span>
                {/each}
              </div>
            {/if}
            {#if hasFileOutputs}
              <div class="mt-2">
                <p class="text-[9px] text-neutral-500">Destination</p>
                <select
                  aria-label="Destination"
                  data-testid="output-mode"
                  value={data.outputMode ?? "pipeline"}
                  onchange={(event) => data.onStepPatch?.("output_mode", event.currentTarget.value)}
                  class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100"
                >
                  <option value="pipeline">Pass to the next node</option>
                  <option value="folder">Save a copy to a folder</option>
                </select>
                {#if data.outputMode === "folder"}
                  <span class="mt-1 flex gap-1">
                    <input
                      type="text"
                      data-testid="output-dir"
                      value={data.outputDir ?? ""}
                      placeholder="/media/final"
                      oninput={(event) => data.onStepPatch?.("output_dir", event.currentTarget.value)}
                      class="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[10px] text-neutral-100"
                    />
                    <button type="button" onclick={(event) => { event.preventDefault(); data.onPickStepPath?.("output_dir"); }} class="rounded border border-neutral-700 px-1.5 text-[10px] text-neutral-300 hover:border-emerald-500">…</button>
                  </span>
                {/if}
              </div>
            {/if}
          </div>
        {/if}
        <div class="flex flex-wrap gap-1 pt-1">
          <button type="button" onclick={(event) => { event.stopPropagation(); data.onRun?.(); }} class="rounded border border-sky-500/40 px-1.5 py-0.5 text-[9px] text-sky-300 hover:bg-sky-500/10">Run to here</button>
          <button type="button" onclick={(event) => { event.stopPropagation(); data.onOpenJson?.(); }} class="rounded border border-neutral-700 px-1.5 py-0.5 text-[9px] text-neutral-300 hover:border-sky-500">JSON</button>
          <button type="button" onclick={(event) => { event.stopPropagation(); data.onLogs?.(); }} class="rounded border border-neutral-700 px-1.5 py-0.5 text-[9px] text-neutral-300 hover:border-sky-500">Logs</button>
          <button type="button" onclick={(event) => { event.stopPropagation(); data.onDuplicate?.(); }} class="rounded border border-neutral-700 px-1.5 py-0.5 text-[9px] text-neutral-300 hover:border-sky-500">Duplicate</button>
          <button type="button" onclick={(event) => { event.stopPropagation(); data.onRemove?.(); }} class="rounded border border-rose-500/30 px-1.5 py-0.5 text-[9px] text-rose-300 hover:bg-rose-500/10">Remove</button>
        </div>
      </div>
    {/if}
  </div>
  <Handle type="source" position={Position.Right} class="!h-2.5 !w-2.5 !border-neutral-500 !bg-sky-500" />
</div>
