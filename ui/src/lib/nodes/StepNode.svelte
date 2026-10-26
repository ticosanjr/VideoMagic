<script lang="ts">
  import { onDestroy } from "svelte";
  import { Handle, Position } from "@xyflow/svelte";
  import HelpTip from "$lib/HelpTip.svelte";
  import NodeConfigForm from "$lib/nodes/NodeConfigForm.svelte";
  import NodeMediaField from "$lib/nodes/NodeMediaField.svelte";
  import NodeOutputs from "$lib/nodes/NodeOutputs.svelte";
  import { validateParams } from "$lib/recipeFields";
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

  let removeArmed = $state(false);
  let removeTimer: ReturnType<typeof setTimeout> | undefined;

  function requestRemove() {
    if (removeArmed) {
      removeArmed = false;
      data.onRemove?.();
      return;
    }
    removeArmed = true;
    clearTimeout(removeTimer);
    removeTimer = setTimeout(() => (removeArmed = false), 3000);
  }

  onDestroy(() => clearTimeout(removeTimer));

  const isMediaNode = $derived(
    data.type === "ingest" ||
      (data.inputPorts ?? []).some((port) => port.id === "media")
  );
  const status = $derived(data.status ?? "idle");
  const progress = $derived(Math.max(0, Math.min(100, Math.round(data.progress ?? 0))));
  const implementation = $derived(data.implementation ?? "available");
  const iconColor = $derived(data.color ?? "#38bdf8");
  const width = $derived(data.expanded ? Math.max(360, data.width ?? 420) : 230);
  const fieldErrors = $derived({
    ...((data.errors ?? {}) as Record<string, string>),
    ...validateParams(data.schema ?? {}, data.params ?? {}, data.type)
  });
  const errorCount = $derived(Object.keys(fieldErrors).length);
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
          {#if errorCount}
            <span
              class="rounded bg-rose-500/15 px-1 py-0.5 text-[8px] font-semibold text-rose-200"
              title={`${errorCount} field error${errorCount === 1 ? "" : "s"}`}
            >⚠ {errorCount}</span>
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
                  <span
                    class={`rounded border px-1.5 py-0.5 text-[9px] ${wired ? "border-emerald-400/30 text-emerald-200" : "border-neutral-700 text-neutral-500"}`}
                    title={`${port.type}${port.required ? " · required" : ""} · ${wired ? `from ${wired}` : "not wired"}`}
                  >
                    {port.label}{port.required ? " *" : ""}
                  </span>
                {/each}
              </div>
            {/if}
            {#if isMediaNode}
              <NodeMediaField
                type={data.type}
                params={data.params}
                mediaOverride={data.mediaOverride}
                inputs={data.inputs}
                onpatch={data.onPatch}
                onsteppatch={data.onStepPatch}
                onpickpath={data.onPickPath}
                onpicksteppath={data.onPickStepPath}
              />
            {/if}
          </div>
        {/if}

        <p class="text-[9px] uppercase tracking-wide text-neutral-500">Config</p>
        <NodeConfigForm
          type={data.type}
          params={data.params}
          schema={data.schema ?? {}}
          options={data.options ?? null}
          presets={data.presets ?? []}
          errors={fieldErrors}
          onpatch={data.onPatch}
          onpickpath={data.onPickPath}
          onapplypreset={data.onApplyPreset}
          onsavepreset={data.onSavePreset}
          onupdatepreset={data.onUpdatePreset}
          ondeletepreset={data.onDeletePreset}
          onfavoritepreset={data.onFavoritePreset}
        />

        <NodeOutputs
          type={data.type}
          outputPorts={data.outputPorts}
          outputMode={data.outputMode}
          outputDir={data.outputDir}
          onsteppatch={data.onStepPatch}
          onpicksteppath={data.onPickStepPath}
        />

        <div class="flex flex-wrap gap-1 pt-1">
          <button type="button" title="Run every step up to this node" onclick={(event) => { event.stopPropagation(); data.onRun?.(); }} class="rounded border border-sky-500/40 px-1.5 py-0.5 text-[9px] text-sky-300 hover:bg-sky-500/10">Run to here</button>
          <button type="button" title="Open the node JSON" onclick={(event) => { event.stopPropagation(); data.onOpenJson?.(); }} class="rounded border border-neutral-700 px-1.5 py-0.5 text-[9px] text-neutral-300 hover:border-sky-500">JSON</button>
          <button type="button" title="Show node logs" onclick={(event) => { event.stopPropagation(); data.onLogs?.(); }} class="rounded border border-neutral-700 px-1.5 py-0.5 text-[9px] text-neutral-300 hover:border-sky-500">Logs</button>
          <button type="button" title="Duplicate this node" onclick={(event) => { event.stopPropagation(); data.onDuplicate?.(); }} class="rounded border border-neutral-700 px-1.5 py-0.5 text-[9px] text-neutral-300 hover:border-sky-500">Duplicate</button>
          <button type="button" title={removeArmed ? "Click again to remove this node" : "Remove this node"} onclick={(event) => { event.stopPropagation(); requestRemove(); }} class={`rounded border px-1.5 py-0.5 text-[9px] ${removeArmed ? "border-rose-400 bg-rose-500/15 text-rose-100" : "border-rose-500/30 text-rose-300 hover:bg-rose-500/10"}`}>{removeArmed ? "Confirm remove" : "Remove"}</button>
        </div>
      </div>
    {/if}
  </div>
  <Handle type="source" position={Position.Right} class="!h-2.5 !w-2.5 !border-neutral-500 !bg-sky-500" />
</div>
