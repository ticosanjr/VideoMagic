<script lang="ts">
  import { onDestroy } from "svelte";
  import HelpTip from "$lib/HelpTip.svelte";
  import NodeConfigForm from "$lib/nodes/NodeConfigForm.svelte";
  import NodeMediaField from "$lib/nodes/NodeMediaField.svelte";
  import NodeOutputs from "$lib/nodes/NodeOutputs.svelte";
  import { validateParams } from "$lib/recipeFields";
  import type { NodeOptions, NodePreset, StepPort } from "$lib/api";

  type WiringOption = { value: string; label: string; compatible: boolean };

  let {
    node,
    busy = false,
    paramText = "",
    paramError = "",
    wiringOptions,
    oninput,
    onpatch,
    onpickpath,
    onsteppatch,
    onpicksteppath,
    onapplypreset,
    onsavepreset,
    onupdatepreset,
    ondeletepreset,
    onfavoritepreset,
    onparaminput,
    onexpandjson,
    onrun,
    onduplicate,
    onremove,
    onlogs,
    onclose
  }: {
    node: {
      id: string;
      title: string;
      type: string;
      description?: string;
      icon?: string;
      color?: string;
      params: Record<string, unknown>;
      schema?: Record<string, unknown>;
      inputs?: Record<string, string>;
      inputPorts?: StepPort[];
      outputPorts?: StepPort[];
      mediaOverride?: string;
      outputMode?: "pipeline" | "folder";
      outputDir?: string;
      options?: NodeOptions | null;
      presets?: NodePreset[];
      errors?: Record<string, string>;
    };
    busy?: boolean;
    paramText?: string;
    paramError?: string;
    wiringOptions?: (portId: string) => WiringOption[];
    oninput?: (portId: string, reference: string) => void;
    onpatch?: (path: string[], value: unknown) => void;
    onpickpath?: (path: string[]) => void;
    onsteppatch?: (key: "media_override" | "output_mode" | "output_dir", value: unknown) => void;
    onpicksteppath?: (key: "media_override" | "output_dir") => void;
    onapplypreset?: (preset: NodePreset) => void;
    onsavepreset?: (name: string) => void;
    onupdatepreset?: (presetId: string) => void;
    ondeletepreset?: (presetId: string) => void;
    onfavoritepreset?: (presetId: string, favorite: boolean) => void;
    onparaminput?: (value: string) => void;
    onexpandjson?: () => void;
    onrun?: () => void;
    onduplicate?: () => void;
    onremove?: () => void;
    onlogs?: () => void;
    onclose?: () => void;
  } = $props();

  let removeArmed = $state(false);
  let removeTimer: ReturnType<typeof setTimeout> | undefined;

  function requestRemove() {
    if (removeArmed) {
      removeArmed = false;
      onremove?.();
      return;
    }
    removeArmed = true;
    clearTimeout(removeTimer);
    removeTimer = setTimeout(() => (removeArmed = false), 3000);
  }

  onDestroy(() => clearTimeout(removeTimer));

  const isMediaNode = $derived(
    node.type === "ingest" ||
      (node.inputPorts ?? []).some((port) => port.id === "media")
  );
  const fieldErrors = $derived({
    ...((node.errors ?? {}) as Record<string, string>),
    ...validateParams(node.schema ?? {}, node.params, node.type)
  });
  const errorCount = $derived(Object.keys(fieldErrors).length);
</script>

<aside class="flex h-[clamp(560px,72vh,920px)] w-full shrink-0 flex-col overflow-hidden rounded-2xl border border-neutral-700 bg-neutral-950/98 shadow-2xl backdrop-blur xl:w-[420px]">
  <div class="flex items-start justify-between gap-2 border-b border-neutral-800 px-3 py-2">
    <div class="min-w-0">
      <p class="text-[10px] uppercase tracking-wide text-neutral-500">Step inspector</p>
      <div class="mt-0.5 flex items-center gap-1.5">
        <span class="text-sm" style={`color:${node.color ?? "#38bdf8"}`}>{node.icon ?? "●"}</span>
        <p class="truncate text-[12px] font-semibold text-neutral-100">{node.title}</p>
        {#if node.description}
          <HelpTip label={node.title} body={node.description} />
        {/if}
      </div>
      <p class="truncate font-mono text-[10px] text-sky-300">{node.id} · {node.type}</p>
      {#if errorCount}
        <p class="mt-1 text-[9px] text-rose-300">{errorCount} field error{errorCount === 1 ? "" : "s"}</p>
      {/if}
    </div>
    <button
      type="button"
      onclick={onclose}
      class="rounded px-1.5 text-neutral-500 hover:text-neutral-200"
      aria-label="Close inspector"
      title="Close inspector"
    >×</button>
  </div>

  <div class="flex flex-wrap items-center gap-1 border-b border-neutral-800 px-3 py-1.5">
    <button
      type="button"
      onclick={onrun}
      disabled={busy}
      title="Run every step up to and including this node"
      class="rounded border border-sky-500/40 px-2 py-0.5 text-[10px] text-sky-300 disabled:opacity-40"
    >Run to here</button>
    <button
      type="button"
      onclick={onduplicate}
      title="Duplicate this node"
      class="rounded border border-neutral-700 px-2 py-0.5 text-[10px] text-neutral-300 hover:border-sky-500"
    >Duplicate</button>
    <button
      type="button"
      onclick={onlogs}
      title="Show this node's logs"
      class="rounded border border-neutral-700 px-2 py-0.5 text-[10px] text-neutral-300 hover:border-sky-500"
    >Logs</button>
    <button
      type="button"
      data-testid="inspector-remove"
      onclick={requestRemove}
      title={removeArmed ? "Click again to remove this node" : "Remove this node"}
      class={`rounded border px-2 py-0.5 text-[10px] ${removeArmed ? "border-rose-400 bg-rose-500/15 text-rose-100" : "border-rose-500/30 text-rose-300 hover:bg-rose-500/10"}`}
    >{removeArmed ? "Confirm remove" : "Remove"}</button>
  </div>

  <div class="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
    {#if (node.inputPorts?.length ?? 0) > 0 || isMediaNode}
      <section class="rounded-lg border border-sky-500/20 bg-sky-950/10 p-2" data-testid="inspector-inputs">
        <p class="text-[10px] uppercase tracking-wide text-sky-300/80">Inputs</p>
        {#if node.inputPorts?.length}
          <div class="mt-2 space-y-2">
            {#each node.inputPorts as port}
              <label class="block text-[10px] text-neutral-400">
                <span class="flex items-center gap-1">
                  {port.label}
                  {#if port.required}<span class="text-rose-300">*</span>{/if}
                  <span class="rounded bg-neutral-800 px-1 py-0.5 font-mono text-[8px] text-neutral-400">{port.type}</span>
                </span>
                <select
                  value={node.inputs?.[port.id] ?? ""}
                  onchange={(event) => oninput?.(port.id, event.currentTarget.value)}
                  class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100"
                >
                  <option value="">Not wired</option>
                  {#each wiringOptions?.(port.id) ?? [] as option}
                    <option
                      value={option.value}
                      disabled={!option.compatible}
                      title={option.compatible ? option.label : `${option.label} — incompatible type`}
                    >{option.label}{option.compatible ? "" : " (incompatible)"}</option>
                  {/each}
                </select>
              </label>
            {/each}
          </div>
        {/if}
        {#if isMediaNode}
          <NodeMediaField
            type={node.type}
            params={node.params}
            mediaOverride={node.mediaOverride}
            inputs={node.inputs}
            prefix="inspector-"
            onpatch={onpatch}
            onsteppatch={onsteppatch}
            onpickpath={onpickpath}
            onpicksteppath={onpicksteppath}
          />
        {/if}
      </section>
    {/if}

    <section class="rounded-lg border border-neutral-800 bg-neutral-900/60 p-2">
      <p class="text-[10px] uppercase tracking-wide text-neutral-500">Config</p>
      <div class="mt-2 space-y-2">
        <NodeConfigForm
          type={node.type}
          params={node.params}
          schema={node.schema ?? {}}
          options={node.options ?? null}
          presets={node.presets ?? []}
          errors={fieldErrors}
          prefix="inspector-"
          onpatch={onpatch}
          onpickpath={onpickpath}
          onapplypreset={onapplypreset}
          onsavepreset={onsavepreset}
          onupdatepreset={onupdatepreset}
          ondeletepreset={ondeletepreset}
          onfavoritepreset={onfavoritepreset}
        />
      </div>
    </section>

    <NodeOutputs
      type={node.type}
      outputPorts={node.outputPorts}
      outputMode={node.outputMode}
      outputDir={node.outputDir}
      prefix="inspector-"
      onsteppatch={onsteppatch}
      onpicksteppath={onpicksteppath}
    />

    <section class="rounded-lg border border-neutral-800 bg-neutral-900/60 p-2">
      <div class="flex items-center justify-between gap-2">
        <p class="text-[10px] uppercase tracking-wide text-neutral-500">Parameters (JSON)</p>
        <button
          type="button"
          onclick={onexpandjson}
          title="Open a larger JSON editor"
          class="rounded border border-neutral-700 px-2 py-0.5 text-[10px] text-neutral-300 hover:border-sky-500"
        >Expand</button>
      </div>
      <textarea
        data-testid="step-params-json"
        value={paramText}
        oninput={(event) => onparaminput?.(event.currentTarget.value)}
        rows="12"
        spellcheck="false"
        aria-label="Step parameters JSON"
        class="mt-1 w-full resize-y rounded-lg border border-neutral-700 bg-neutral-950 p-2 font-mono text-[10px] text-neutral-200"
      ></textarea>
      {#if paramError}<p class="mt-1 text-[10px] text-rose-300">{paramError}</p>{/if}
      <p class="mt-2 text-[9px] leading-4 text-neutral-600">
        JSON is applied to the node while it is valid. Use Expand for a large editor.
      </p>
    </section>
  </div>
</aside>
