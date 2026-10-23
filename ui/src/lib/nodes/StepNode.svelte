<script lang="ts">
  import { Handle, Position } from "@xyflow/svelte";
  import { fieldGroups, validateField, type RecipeField } from "$lib/recipeFields";

  let {
    data,
    selected = false
  }: {
    data: {
      title: string;
      type: string;
      params: Record<string, unknown>;
      schema?: Record<string, unknown>;
      status?: "idle" | "queued" | "running" | "cached" | "executed" | "failed" | "skipped";
      progress?: number;
      expanded?: boolean;
      pinned?: boolean;
      width?: number;
      errors?: Record<string, string>;
      onToggle?: () => void;
      onPin?: () => void;
      onWidth?: () => void;
      onResize?: (width: number) => void;
      onPatch?: (path: string[], value: unknown) => void;
      onPickPath?: (path: string[]) => void;
      onRun?: () => void;
      onDuplicate?: () => void;
      onRemove?: () => void;
      onOpenJson?: () => void;
    };
    selected?: boolean;
  } = $props();

  const groups = $derived(fieldGroups(data.schema ?? {}, data.params ?? {}));
  let jsonDrafts = $state<Record<string, string>>({});
  let jsonErrors = $state<Record<string, string>>({});
  const status = $derived(data.status ?? "idle");
  const progress = $derived(Math.max(0, Math.min(100, Math.round(data.progress ?? 0))));
  const width = $derived(data.expanded ? Math.max(360, data.width ?? 420) : 230);

  function fieldError(field: RecipeField): string | null {
    return data.errors?.[field.id] ?? validateField(field);
  }

  function change(field: RecipeField, raw: string | boolean) {
    let value: unknown = raw;
    if (field.kind === "number") {
      value = raw === "" ? undefined : Number(raw);
    }
    data.onPatch?.(field.path, value);
  }

  function displayValue(field: RecipeField): string {
    if (field.value === undefined || field.value === null) return field.kind === "json" ? "[]" : "";
    if (field.kind === "json") return jsonDrafts[field.id] ?? JSON.stringify(field.value);
    return String(field.value);
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
  class={`relative rounded-2xl border text-left shadow-xl transition ${
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
        <p class="truncate text-xs font-semibold text-neutral-100">{data.title}</p>
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
                    {#if field.required}<span class="text-rose-300">*</span>{/if}
                  </span>
                  {#if field.kind === "boolean"}
                    <input
                      data-testid={`field-${field.id}`}
                      type="checkbox"
                      checked={field.value === true}
                      onchange={(event) => change(field, event.currentTarget.checked)}
                      class="mt-1 block"
                    />
                  {:else if field.kind === "enum"}
                    <select
                      data-testid={`field-${field.id}`}
                      value={displayValue(field)}
                      onchange={(event) => change(field, event.currentTarget.value)}
                      class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100"
                    >
                      {#if !field.required}<option value="">—</option>{/if}
                      {#each field.options as option}<option value={option}>{option}</option>{/each}
                    </select>
                  {:else if field.kind === "number"}
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
                  {:else if field.kind === "json"}
                    <textarea
                      data-testid={`field-${field.id}`}
                      rows="3"
                      value={displayValue(field)}
                      oninput={(event) => changeJson(field, event.currentTarget.value)}
                      class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 p-2 font-mono text-[10px] text-neutral-100"
                    ></textarea>
                  {:else if field.kind === "path"}
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
                  {:else if field.kind === "color"}
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
                  {#if error}<span class="mt-0.5 block text-[9px] text-rose-300">{error}</span>{/if}
                </label>
              {/each}
            </div>
          </div>
        {/each}

        <div class="flex flex-wrap gap-1 pt-1">
          <button type="button" onclick={(event) => { event.stopPropagation(); data.onRun?.(); }} class="rounded border border-sky-500/40 px-1.5 py-0.5 text-[9px] text-sky-300 hover:bg-sky-500/10">Run to here</button>
          <button type="button" onclick={(event) => { event.stopPropagation(); data.onOpenJson?.(); }} class="rounded border border-neutral-700 px-1.5 py-0.5 text-[9px] text-neutral-300 hover:border-sky-500">JSON</button>
          <button type="button" onclick={(event) => { event.stopPropagation(); data.onDuplicate?.(); }} class="rounded border border-neutral-700 px-1.5 py-0.5 text-[9px] text-neutral-300 hover:border-sky-500">Duplicate</button>
          <button type="button" onclick={(event) => { event.stopPropagation(); data.onRemove?.(); }} class="rounded border border-rose-500/30 px-1.5 py-0.5 text-[9px] text-rose-300 hover:bg-rose-500/10">Remove</button>
        </div>
      </div>
    {/if}
  </div>
  <Handle type="source" position={Position.Right} class="!h-2.5 !w-2.5 !border-neutral-500 !bg-sky-500" />
</div>
