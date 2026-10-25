<script lang="ts">
  import { tick } from "svelte";

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
  let tooltip = $state<HTMLElement | null>(null);
  let position = $state("position: fixed; left: 0; top: 0;");
  const id = `help-${Math.random().toString(36).slice(2, 9)}`;

  function place() {
    if (!trigger || !tooltip) return;
    const rect = trigger.getBoundingClientRect();
    const margin = 8;
    const width = Math.min(256, window.innerWidth - margin * 2);
    const height = tooltip.offsetHeight;
    let top =
      placement === "bottom" ? rect.bottom + margin : rect.top - height - margin;
    if (top < margin) top = rect.bottom + margin;
    if (top + height > window.innerHeight - margin) {
      top = Math.max(margin, window.innerHeight - height - margin);
    }
    const left = Math.max(
      margin,
      Math.min(rect.left, window.innerWidth - width - margin)
    );
    position = `position: fixed; left: ${left}px; top: ${top}px; width: ${width}px;`;
  }

  async function show() {
    open = true;
    await tick();
    place();
  }

  function hide() {
    open = false;
  }

  function portal(node: HTMLElement) {
    document.body.appendChild(node);
    return {
      destroy() {
        node.remove();
      }
    };
  }

  $effect(() => {
    if (!open) return;
    const reposition = () => place();
    window.addEventListener("scroll", reposition, true);
    window.addEventListener("resize", reposition);
    return () => {
      window.removeEventListener("scroll", reposition, true);
      window.removeEventListener("resize", reposition);
    };
  });
</script>

<span class="inline-flex align-middle">
  <button
    bind:this={trigger}
    type="button"
    class="inline-flex h-4 w-4 items-center justify-center rounded-full border border-neutral-600 text-[9px] font-semibold text-neutral-400 transition hover:border-sky-400/60 hover:text-sky-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-sky-400"
    aria-label={`Help: ${label}`}
    aria-describedby={open ? id : undefined}
    aria-expanded={open}
    onmouseenter={() => void show()}
    onmouseleave={hide}
    onfocus={() => void show()}
    onblur={hide}
    onkeydown={(event) => {
      if (event.key === "Escape") {
        hide();
        trigger?.blur();
      }
    }}
  >?</button>
</span>

{#if open}
  <span
    use:portal
    bind:this={tooltip}
    {id}
    role="tooltip"
    data-testid="help-tooltip"
    style={position}
    class="z-[9999] rounded-xl border border-neutral-700 bg-neutral-950 px-3 py-2 text-left text-[11px] leading-relaxed text-neutral-300 shadow-2xl shadow-black/60"
  >
    <span class="block font-medium text-neutral-100">{label}</span>
    <span class="mt-1 block">{body}</span>
    {#if doc}
      <span class="mt-1 block font-mono text-[10px] text-sky-300">{doc}</span>
    {/if}
  </span>
{/if}
