<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import HelpTip from "$lib/HelpTip.svelte";
  import NodeConfigForm from "$lib/nodes/NodeConfigForm.svelte";
  import NodeMediaField from "$lib/nodes/NodeMediaField.svelte";
  import NodeOutputs from "$lib/nodes/NodeOutputs.svelte";
  import { validateParams } from "$lib/recipeFields";
  import Button from "$lib/ui/Button.svelte";
  import Icon from "$lib/ui/Icon.svelte";
  import IconButton from "$lib/ui/IconButton.svelte";
  import Section from "$lib/ui/Section.svelte";
  import { stepIcon } from "$lib/ui/icons";
  import type { NodeOptions, NodePreset, StepPort } from "$lib/api";

  type WiringOption = { value: string; label: string; compatible: boolean };

  let {
    node,
    busy = false,
    oninspectoutputs = undefined,
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
    onrenamepreset,
    onduplicatepreset,
    onparaminput,
    onexpandjson,
    onrun,
    onwiring,
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
      enabled?: boolean;
      onEnabledChange?: (enabled: boolean) => void;
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
    oninspectoutputs?: () => void;
    onapplypreset?: (preset: NodePreset) => void;
    onsavepreset?: (name: string) => void;
    onupdatepreset?: (presetId: string) => void;
    ondeletepreset?: (presetId: string) => void;
    onfavoritepreset?: (presetId: string, favorite: boolean) => void;
    onrenamepreset?: (presetId: string, name: string) => void;
    onduplicatepreset?: (presetId: string, name: string) => void;
    onparaminput?: (value: string) => void;
    onexpandjson?: () => void;
    onrun?: () => void;
    onwiring?: () => void;
    onduplicate?: () => void;
    onremove?: () => void;
    onlogs?: () => void;
    onclose?: () => void;
  } = $props();

  let removeArmed = $state(false);
  let removeTimer: ReturnType<typeof setTimeout> | undefined;
  let width = $state(420);
  let resizing = $state(false);
  let startX = 0;
  let startWidth = 420;
  let query = $state("");

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

  function startResize(event: PointerEvent) {
    resizing = true;
    startX = event.clientX;
    startWidth = width;
    window.addEventListener("pointermove", onResize);
    window.addEventListener("pointerup", stopResize);
    event.preventDefault();
  }

  function onResize(event: PointerEvent) {
    width = Math.min(820, Math.max(360, startWidth - (event.clientX - startX)));
  }

  function stopResize() {
    resizing = false;
    window.removeEventListener("pointermove", onResize);
    window.removeEventListener("pointerup", stopResize);
    try {
      localStorage.setItem("videoflow.inspectorWidth", String(width));
    } catch {
      /* private mode */
    }
  }

  onMount(() => {
    try {
      const saved = Number(localStorage.getItem("videoflow.inspectorWidth"));
      if (Number.isFinite(saved) && saved >= 360) {
        width = Math.min(820, saved);
      }
    } catch {
      /* private mode */
    }
  });

  onDestroy(() => {
    clearTimeout(removeTimer);
    window.removeEventListener("pointermove", onResize);
    window.removeEventListener("pointerup", stopResize);
  });

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

<button
  type="button"
  class="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm xl:hidden"
  aria-label="Dismiss inspector"
  onclick={() => onclose?.()}
></button>
<aside
  class={`relative flex h-[clamp(560px,72vh,920px)] w-full shrink-0 flex-col overflow-hidden rounded-2xl border border-neutral-700 bg-neutral-950/98 shadow-2xl backdrop-blur max-xl:fixed max-xl:inset-x-0 max-xl:bottom-0 max-xl:z-50 max-xl:h-[85vh] max-xl:rounded-b-none max-xl:border-x-0 max-xl:border-b-0 xl:w-[var(--inspector-width)] ${resizing ? "select-none" : ""}`}
  style={`--inspector-width:${width}px`}
>
  <button
    type="button"
    class="absolute left-0 top-0 z-10 hidden h-full w-1.5 -translate-x-1/2 cursor-col-resize bg-transparent hover:bg-sky-400/30 xl:block"
    aria-label="Resize inspector"
    title="Drag to resize the inspector"
    onpointerdown={startResize}
  ></button>

  <div class="flex items-start justify-between gap-2 border-b border-neutral-800 px-3 py-2">
    <div class="min-w-0">
      <p class="text-[10px] uppercase tracking-wide text-neutral-500">Step inspector</p>
      <div class="mt-0.5 flex items-center gap-1.5">
        <span style={`color:${node.color ?? "#38bdf8"}`}><Icon name={stepIcon(node.type)} size={16} /></span>
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
    <div class="flex items-center gap-1">
      <IconButton
        icon={node.enabled === false ? "play" : "pause"}
        label={node.enabled === false ? "Enable node" : "Disable node"}
        onclick={() => node.onEnabledChange?.(node.enabled === false)}
      />
      <IconButton icon="close" label="Close inspector" onclick={() => onclose?.()} />
    </div>
  </div>

  <div class="flex flex-wrap items-center gap-1 border-b border-neutral-800 px-3 py-1.5">
    {#if (node.inputPorts?.length ?? 0) > 0}
      <Button icon="link" variant="secondary" size="xs" onclick={() => onwiring?.()} title="Open the full port wiring dialog">Wiring</Button>
    {/if}
    <Button icon="play" variant="secondary" size="xs" disabled={busy} onclick={() => onrun?.()} title="Run every step up to and including this node">Run to here</Button>
    <Button icon="duplicate" variant="secondary" size="xs" onclick={() => onduplicate?.()} title="Duplicate this node">Duplicate</Button>
    <Button icon="logs" variant="secondary" size="xs" onclick={() => onlogs?.()} title="Show this node's logs">Logs</Button>
    <Button
      icon="trash"
      variant={removeArmed ? "danger" : "secondary"}
      size="xs"
      testid="inspector-remove"
      onclick={requestRemove}
      title={removeArmed ? "Click again to remove this node" : "Remove this node"}
    >{removeArmed ? "Confirm remove" : "Remove"}</Button>
  </div>

  <div class="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
    {#if (node.inputPorts?.length ?? 0) > 0 || isMediaNode}
      <Section title="Inputs" icon="link" tone="input" testid="inspector-inputs">
        {#if node.inputPorts?.length}
          <div class="space-y-2">
            {#each node.inputPorts as port}
              <label class="block text-[10px] text-neutral-400">
                <span class="flex items-center gap-1">
                  {port.label}
                  {#if port.required}<span class="text-rose-300">*</span>{/if}
                  <span class="rounded bg-neutral-800 px-1 py-0.5 font-mono text-[8px] text-neutral-400">{port.type}</span>
                </span>
                <select
                  value={node.inputs?.[port.id] ?? ""}
                  aria-label={`${port.label} wiring`}
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
      </Section>
    {/if}

    <Section title="Config" icon="sliders" tone="config" testid="inspector-config">
      {#snippet actions()}
        <input
          bind:value={query}
          type="search"
          placeholder="Filter fields"
          aria-label="Filter fields"
          class="w-28 rounded border border-neutral-700 bg-neutral-950 px-1.5 py-0.5 text-[9px] text-neutral-200 placeholder:text-neutral-600"
        />
      {/snippet}
      <NodeConfigForm
        type={node.type}
        params={node.params}
        schema={node.schema ?? {}}
        options={node.options ?? null}
        presets={node.presets ?? []}
        errors={fieldErrors}
        prefix="inspector-"
        query={query}
        onpatch={onpatch}
        onpickpath={onpickpath}
        onapplypreset={onapplypreset}
        onsavepreset={onsavepreset}
        onupdatepreset={onupdatepreset}
        ondeletepreset={ondeletepreset}
        onfavoritepreset={onfavoritepreset}
        onrenamepreset={onrenamepreset}
        onduplicatepreset={onduplicatepreset}
      />
    </Section>

    <NodeOutputs
      type={node.type}
      outputPorts={node.outputPorts}
      outputMode={node.outputMode}
      outputDir={node.outputDir}
      prefix="inspector-"
      onsteppatch={onsteppatch}
      onpicksteppath={onpicksteppath}
      onInspectOutputs={oninspectoutputs}
    />

    <Section title="Parameters (JSON)" icon="code" testid="inspector-json">
      {#snippet actions()}
        <Button icon="code" variant="secondary" size="xs" onclick={() => onexpandjson?.()} title="Open a larger JSON editor">Expand</Button>
      {/snippet}
      <textarea
        data-testid="step-params-json"
        value={paramText}
        oninput={(event) => onparaminput?.(event.currentTarget.value)}
        rows="12"
        spellcheck="false"
        aria-label="Step parameters JSON"
        class="w-full resize-y rounded-lg border border-neutral-700 bg-neutral-950 p-2 font-mono text-[10px] text-neutral-200"
      ></textarea>
      {#if paramError}<p class="mt-1 text-[10px] text-rose-300">{paramError}</p>{/if}
      <p class="mt-2 text-[9px] leading-4 text-neutral-600">
        JSON is applied to the node while it is valid. Use Expand for a large editor.
      </p>
    </Section>
  </div>
</aside>
