<script lang="ts">
  import { onMount } from "svelte";

  let { onnavigate }: { onnavigate: (tab: string) => void } = $props();
  let visible = $state(false);

  onMount(() => {
    visible = localStorage.getItem("videoflow.onboarded") !== "1";
  });

  function dismiss() {
    localStorage.setItem("videoflow.onboarded", "1");
    visible = false;
  }

  const steps = [
    {
      title: "1. Check paths and FFmpeg",
      body: "Allowed roots gate file access. Confirm FFmpeg/FFprobe and your media folders.",
      tab: "settings",
      action: "Open Settings"
    },
    {
      title: "2. Configure AI (optional)",
      body: "Add an OpenAI-compatible provider or a local service for Assistant, transcription, and dubbing.",
      tab: "providers",
      action: "Open AI providers"
    },
    {
      title: "3. Run your first recipe",
      body: "Pick a template, point at a source file, dry-run, then run. Shorts and exports are optional steps.",
      tab: "recipes",
      action: "Open Recipes"
    },
    {
      title: "4. Build with the inspector",
      body: "Select a node to edit every field, wire ports, and apply presets. Edits autosave; Ctrl/Cmd+Z undoes.",
      tab: "recipes",
      action: "Open the builder"
    }
  ];
</script>

{#if visible}
  <section class="rounded-2xl border border-sky-400/20 bg-sky-950/20 p-4" data-testid="onboarding-card">
    <div class="flex items-start justify-between gap-3">
      <div>
        <h2 class="text-sm font-semibold text-white">Welcome to VideoFlow</h2>
        <p class="mt-1 text-xs text-sky-100/70">Three steps to a first cut. Everything stays on this machine.</p>
      </div>
      <button type="button" onclick={dismiss} class="rounded-lg border border-white/10 px-2 py-1 text-[10px] text-sky-200">Dismiss</button>
    </div>
    <div class="mt-3 grid gap-2 md:grid-cols-2 xl:grid-cols-4">
      {#each steps as step}
        <article class="rounded-xl border border-sky-400/15 bg-black/20 p-3">
          <p class="text-[11px] font-medium text-sky-100">{step.title}</p>
          <p class="mt-1 text-[10px] leading-relaxed text-sky-100/60">{step.body}</p>
          <button type="button" class="mt-2 rounded-lg border border-sky-400/25 px-2 py-1 text-[10px] text-sky-200" onclick={() => onnavigate(step.tab)}>{step.action}</button>
        </article>
      {/each}
    </div>
  </section>
{/if}
