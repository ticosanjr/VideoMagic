<script lang="ts">
  let {
    type,
    params,
    mediaOverride = "",
    inputs = {},
    prefix = "",
    onpatch,
    onsteppatch,
    onpickpath,
    onpicksteppath
  }: {
    type: string;
    params: Record<string, unknown>;
    mediaOverride?: string;
    inputs?: Record<string, string>;
    prefix?: string;
    onpatch?: (path: string[], value: unknown) => void;
    onsteppatch?: (key: "media_override", value: unknown) => void;
    onpickpath?: (path: string[]) => void;
    onpicksteppath?: (key: "media_override") => void;
  } = $props();

  const value = $derived(
    type === "ingest" ? String(params.source ?? "") : mediaOverride
  );
  const wiredMedia = $derived(Object.keys(inputs).includes("media"));
  const testId = $derived(`${prefix}media-input`);

  function patch(next: string) {
    if (type === "ingest") onpatch?.(["source"], next);
    else onsteppatch?.("media_override", next);
  }

  function pick() {
    if (type === "ingest") onpickpath?.(["source"]);
    else onpicksteppath?.("media_override");
  }
</script>

<div class="mt-2">
  <p class="text-[9px] text-neutral-500">
    {wiredMedia ? "Media comes from the wired input" : "Choose the media for this node"}
  </p>
  <span class="mt-1 flex gap-1">
    <input
      type="text"
      data-testid={testId}
      value={value}
      placeholder="/media/source.mp4"
      aria-label="Media path"
      oninput={(event) => patch(event.currentTarget.value)}
      class="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 font-mono text-[10px] text-neutral-100"
    />
    <button
      type="button"
      title="Choose a media file"
      aria-label="Choose media"
      onclick={(event) => { event.preventDefault(); pick(); }}
      class="rounded border border-neutral-700 px-1.5 text-[10px] text-neutral-300 hover:border-sky-500"
    >…</button>
  </span>
</div>
