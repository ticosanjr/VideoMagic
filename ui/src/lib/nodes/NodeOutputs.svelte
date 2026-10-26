<script lang="ts">
  import type { StepPort } from "$lib/api";

  let {
    type,
    outputPorts = [],
    outputMode = "pipeline",
    outputDir = "",
    prefix = "",
    onsteppatch,
    onpicksteppath
  }: {
    type: string;
    outputPorts?: StepPort[];
    outputMode?: "pipeline" | "folder";
    outputDir?: string;
    prefix?: string;
    onsteppatch?: (
      key: "output_mode" | "output_dir",
      value: unknown
    ) => void;
    onpicksteppath?: (key: "output_dir") => void;
  } = $props();

  const hasFileOutputs = $derived(
    outputPorts.some(
      (port) => port.type === "artifact_map" || port.type === "nle_artifacts"
    )
  );
</script>

{#if outputPorts.length || hasFileOutputs}
  <div
    class="rounded-lg border border-emerald-500/15 bg-emerald-950/10 p-2"
    data-testid={`${prefix}outputs-${type}`}
  >
    <p class="text-[9px] uppercase tracking-wide text-emerald-300/80">Outputs</p>
    {#if outputPorts.length}
      <div class="mt-1 flex flex-wrap gap-1">
        {#each outputPorts as port}
          <span
            class="rounded border border-emerald-400/25 px-1.5 py-0.5 text-[9px] text-emerald-200"
            title={`${port.type}${port.required ? " · required" : ""}`}
          >{port.label}</span>
        {/each}
      </div>
    {/if}
    {#if hasFileOutputs}
      <div class="mt-2">
        <p class="text-[9px] text-neutral-500">Destination</p>
        <select
          aria-label="Destination"
          data-testid={`${prefix}output-mode`}
          value={outputMode}
          onchange={(event) => onsteppatch?.("output_mode", event.currentTarget.value)}
          class="mt-1 w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[10px] text-neutral-100"
        >
          <option value="pipeline">Pass to the next node</option>
          <option value="folder">Save a copy to a folder</option>
        </select>
        {#if outputMode === "folder"}
          <span class="mt-1 flex gap-1">
            <input
              type="text"
              data-testid={`${prefix}output-dir`}
              value={outputDir}
              placeholder="/media/final"
              aria-label="Output folder"
              oninput={(event) => onsteppatch?.("output_dir", event.currentTarget.value)}
              class="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[10px] text-neutral-100"
            />
            <button
              type="button"
              title="Choose an output folder"
              aria-label="Choose output folder"
              onclick={(event) => { event.preventDefault(); onpicksteppath?.("output_dir"); }}
              class="rounded border border-neutral-700 px-1.5 text-[10px] text-neutral-300 hover:border-emerald-500"
            >…</button>
          </span>
        {/if}
      </div>
    {/if}
  </div>
{/if}
