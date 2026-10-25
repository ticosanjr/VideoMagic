<script lang="ts">
  let {
    label,
    body,
    doc = "",
    placement = "top"
  }: {
    label: string;
    body: string;
    doc?: string;
    placement?: "top" | "bottom";
  } = $props();

  let open = $state(false);
  let trigger = $state<HTMLButtonElement | null>(null);
  const id = `help-${Math.random().toString(36).slice(2, 9)}`;

  function show() {
    open = true;
  }
  function hide() {
    open = false;
  }
</script>

<span class="relative inline-flex align-middle">
  <button
    bind:this={trigger}
    type="button"
    class="inline-flex h-4 w-4 items-center justify-center rounded-full border border-neutral-600 text-[9px] font-semibold text-neutral-400 transition hover:border-sky-400/60 hover:text-sky-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400"
    aria-label={`Help: ${label}`}
    aria-describedby={open ? id : undefined}
    aria-expanded={open}
    onmouseenter={show}
    onmouseleave={hide}
    onfocus={show}
    onblur={hide}
    onkeydown={(event) => {
      if (event.key === "Escape") {
        hide();
        trigger?.blur();
      }
    }}
  >?</button>
  {#if open}
    <span
      {id}
      role="tooltip"
      class={`absolute z-[80] w-64 rounded-xl border border-neutral-700 bg-neutral-950 px-3 py-2 text-left text-[11px] leading-relaxed text-neutral-300 shadow-2xl shadow-black/60 ${placement === "bottom" ? "left-0 top-6" : "bottom-6 left-0"}`}
    >
      <span class="block font-medium text-neutral-100">{label}</span>
      <span class="mt-1 block">{body}</span>
      {#if doc}
        <span class="mt-1 block font-mono text-[10px] text-sky-300">{doc}</span>
      {/if}
    </span>
  {/if}
</span>
