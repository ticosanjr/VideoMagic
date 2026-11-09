<script lang="ts">
  import { onMount } from "svelte";
  import Icon from "$lib/ui/Icon.svelte";
  import type { IconName } from "$lib/ui/icons";

  let {
    onnavigate,
    force = false,
    ondismiss
  }: {
    onnavigate: (tab: string) => void;
    force?: boolean;
    ondismiss?: () => void;
  } = $props();
  let visible = $state(false);

  onMount(() => {
    visible = force || localStorage.getItem("videoflow.onboarded") !== "1";
  });

  function dismiss() {
    localStorage.setItem("videoflow.onboarded", "1");
    visible = false;
    ondismiss?.();
  }

  const steps: {
    title: string;
    body: string;
    tab: string;
    action: string;
    icon: IconName;
  }[] = [
    {
      title: "1. Check paths and FFmpeg",
      body: "Allowed roots gate file access. Confirm FFmpeg/FFprobe and your media folders.",
      tab: "settings",
      action: "Open Settings",
      icon: "folder"
    },
    {
      title: "2. Configure AI (optional)",
      body: "Add an OpenAI-compatible provider or a local service for Assistant, transcription, and dubbing.",
      tab: "providers",
      action: "Open AI providers",
      icon: "plug"
    },
    {
      title: "3. Run your first recipe",
      body: "Pick a template, point at a source file, dry-run, then run. Shorts and exports are optional steps.",
      tab: "recipes",
      action: "Open Recipes",
      icon: "play"
    },
    {
      title: "4. Build with the inspector",
      body: "Select a node to edit every field, wire ports, and apply presets. Edits autosave; Ctrl/Cmd+Z undoes.",
      tab: "recipes",
      action: "Open the builder",
      icon: "workflow"
    }
  ];
</script>

{#if visible}
  <section
    class="relative overflow-hidden rounded-2xl border border-sky-400/20 bg-sky-950/20 p-4"
    data-testid="onboarding-card"
  >
    <div class="pointer-events-none absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-sky-400/60 to-transparent"></div>
    <div class="flex items-start justify-between gap-3">
      <div class="flex items-start gap-3">
        <div class="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border border-sky-400/20 bg-sky-400/10 text-sky-200">
          <Icon name="sparkles" size={18} />
        </div>
        <div>
          <div class="flex flex-wrap items-center gap-2">
            <h2 class="text-sm font-semibold text-white">Welcome to VideoFlow</h2>
            <span class="inline-flex items-center gap-1 rounded-full border border-emerald-400/20 bg-emerald-400/[0.06] px-2 py-0.5 text-[9px] font-medium uppercase tracking-wide text-emerald-200/80">
              <Icon name="check" size={10} /> local only
            </span>
          </div>
          <p class="mt-1 text-xs text-sky-100/70">Four steps to a first cut. Everything stays on this machine.</p>
        </div>
      </div>
      <button type="button" onclick={dismiss} class="rounded-lg border border-white/10 px-2 py-1 text-[10px] text-sky-200">Dismiss</button>
    </div>

    <div class="mt-4 h-1 overflow-hidden rounded-full bg-sky-400/10">
      <div class="h-full w-1/4 rounded-full bg-gradient-to-r from-sky-400 to-indigo-400"></div>
    </div>

    <div class="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
      {#each steps as step}
        <article class="rounded-xl border border-sky-400/15 bg-black/20 p-3 transition hover:border-sky-400/30 hover:bg-sky-400/[0.04]">
          <div class="flex items-center gap-2">
            <span class="flex h-7 w-7 items-center justify-center rounded-lg border border-sky-400/15 bg-sky-400/10 text-sky-200">
              <Icon name={step.icon} size={14} />
            </span>
            <p class="text-[11px] font-medium text-sky-100">{step.title}</p>
          </div>
          <p class="mt-2 text-[10px] leading-relaxed text-sky-100/60">{step.body}</p>
          <button
            type="button"
            class="mt-2 inline-flex items-center gap-1 rounded-lg border border-sky-400/25 px-2 py-1 text-[10px] text-sky-200 transition hover:border-sky-300/50 hover:text-white"
            onclick={() => onnavigate(step.tab)}
          >{step.action}<Icon name="chevron-right" size={11} /></button>
        </article>
      {/each}
    </div>

    <div class="mt-3 flex flex-wrap items-center justify-between gap-2 text-[10px] text-sky-200/50">
      <span>Tip: press <kbd class="rounded border border-white/10 px-1 py-0.5 font-mono text-[9px]">Ctrl/Cmd + K</kbd> for the command palette.</span>
      <button type="button" onclick={dismiss} class="underline-offset-2 transition hover:text-sky-100 hover:underline">Skip for now</button>
    </div>
  </section>
{/if}
