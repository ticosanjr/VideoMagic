<script lang="ts">
  import { onMount } from "svelte";
  import EmptyState from "$lib/EmptyState.svelte";
  import ErrorBanner from "$lib/ErrorBanner.svelte";
  import HelpTip from "$lib/HelpTip.svelte";
  import {
    createProject,
    deleteProject,
    errorMessage,
    getProjects,
    type Project
  } from "$lib/api";

  let projects = $state<Project[]>([]);
  let error = $state("");
  let busy = $state(false);
  let name = $state("");
  let source = $state("");
  let output = $state("");

  async function load() {
    try {
      projects = await getProjects();
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function create() {
    if (!name.trim()) {
      error = "Give the project a name.";
      return;
    }
    busy = true;
    error = "";
    try {
      await createProject({ name: name.trim(), source: source.trim(), output: output.trim() });
      name = "";
      source = "";
      output = "";
      await load();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  async function remove(project: Project) {
    if (!confirm(`Delete project "${project.name}"? The media is not deleted.`)) return;
    try {
      await deleteProject(project.id);
      await load();
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  onMount(() => void load());
</script>

<section class="space-y-4" data-testid="projects-panel">
  <header>
    <h2 class="flex items-center gap-1.5 text-lg font-semibold text-white">Projects <HelpTip label="Projects" body="A project is a local bookmark for a source file and an output folder. Deleting a project never deletes media." doc="docs/api.md" /></h2>
    <p class="mt-1 text-xs text-neutral-500">Saved source and output pairs for interviews, series, and batches.</p>
  </header>

  <ErrorBanner message={error} title="Project error" onDismiss={() => (error = "")} testId="projects-error" />

  <form class="grid gap-2 rounded-2xl border border-neutral-800 bg-neutral-900/40 p-3 md:grid-cols-[1fr_1fr_1fr_auto]" onsubmit={(event) => { event.preventDefault(); void create(); }}>
    <label class="text-[10px] text-neutral-500">Name<input bind:value={name} placeholder="Interview series" class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100" /></label>
    <label class="text-[10px] text-neutral-500">Source<input bind:value={source} placeholder="/media/source.mp4" class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-200" /></label>
    <label class="text-[10px] text-neutral-500">Output<input bind:value={output} placeholder="/media/output" class="mt-1 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-200" /></label>
    <button type="submit" disabled={busy} class="mt-4 h-8 rounded-lg bg-sky-500/15 px-3 text-xs text-sky-200 ring-1 ring-inset ring-sky-400/25 disabled:opacity-40">Create</button>
  </form>

  {#if !projects.length}
    <EmptyState title="No projects yet" description="Create one to keep a source and output folder together." />
  {:else}
    <ul class="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
      {#each projects as project (project.id)}
        <li class="rounded-2xl border border-neutral-800 bg-white/[0.02] p-4">
          <p class="truncate text-sm font-medium text-neutral-100">{project.name}</p>
          <p class="mt-1 truncate font-mono text-[10px] text-neutral-500" title={project.source}>{project.source || "no source"}</p>
          <p class="truncate font-mono text-[10px] text-neutral-500" title={project.output}>{project.output || "no output"}</p>
          <p class="mt-1 text-[10px] text-neutral-600">saved {project.updated_at}</p>
          <div class="mt-3 flex flex-wrap gap-1.5">
            <button type="button" onclick={() => void remove(project)} class="rounded-lg border border-rose-500/20 px-2.5 py-1 text-[11px] text-rose-300">Delete</button>
          </div>
        </li>
      {/each}
    </ul>
  {/if}
</section>
