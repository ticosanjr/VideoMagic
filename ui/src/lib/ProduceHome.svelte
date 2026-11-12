<script lang="ts">
  import { onMount } from "svelte";
  import Button from "$lib/ui/Button.svelte";
  import EmptyState from "$lib/EmptyState.svelte";
  import Icon from "$lib/ui/Icon.svelte";
  import Progress from "$lib/ui/Progress.svelte";
  import RunComposer from "$lib/RunComposer.svelte";
  import StatusBadge from "$lib/StatusBadge.svelte";
  import {
    errorMessage,
    getSystem,
    listJobs,
    listPendingInteractions,
    listRecipes,
    setRecipeFavorite,
    type HiltPending,
    type Job,
    type RecipeSummary,
    type SystemInfo
  } from "$lib/api";
  import { jobDisplayName } from "$lib/jobsView";
  import { recipesFor, type RecipeFilter } from "$lib/recipeLibrary";

  let {
    onedit,
    onreview,
    onstarted
  }: {
    onedit: (recipeId: string) => void;
    onreview: (jobId?: string) => void;
    onstarted: (job: Job) => void;
  } = $props();

  let recipes = $state<RecipeSummary[]>([]);
  let jobs = $state<Job[]>([]);
  let pending = $state<HiltPending[]>([]);
  let system = $state<SystemInfo | null>(null);
  let loading = $state(true);
  let error = $state("");
  let query = $state("");
  let filter = $state<RecipeFilter>("all");
  let composerOpen = $state(false);
  let composerRecipe = $state("");

  const favorites = $derived(recipesFor(recipes, "favorites", ""));
  const visible = $derived(recipesFor(recipes, filter, query));
  const active = $derived(
    jobs.filter((job) => ["running", "queued", "waiting_approval", "waiting_input", "paused"].includes(job.status))
  );
  const recent = $derived(jobs.slice(0, 6));

  onMount(() => {
    void load();
  });

  async function load() {
    loading = true;
    error = "";
    try {
      const [loadedRecipes, loadedJobs, loadedPending, loadedSystem] = await Promise.all([
        listRecipes(),
        listJobs(false, { limit: 12 }).catch(() => []),
        listPendingInteractions().catch(() => []),
        getSystem().catch(() => null)
      ]);
      recipes = loadedRecipes;
      jobs = loadedJobs;
      pending = loadedPending;
      system = loadedSystem;
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      loading = false;
    }
  }

  function start(recipeId: string) {
    composerRecipe = recipeId;
    composerOpen = true;
  }

  function started(job: Job) {
    composerOpen = false;
    onstarted(job);
  }

  async function toggleFavorite(recipe: RecipeSummary) {
    try {
      await setRecipeFavorite(recipe.id, !recipe.favorite);
      recipes = recipes.map((item) =>
        item.id === recipe.id ? { ...item, favorite: !item.favorite } : item
      );
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  function recipeName(recipeId: string): string {
    return recipes.find((item) => item.id === recipeId)?.name ?? recipeId;
  }

  function lastUsed(recipe: RecipeSummary): string {
    if (!recipe.last_used_at) return "Never run";
    const date = new Date(recipe.last_used_at);
    return Number.isNaN(date.getTime())
      ? recipe.last_used_at
      : `Last run ${date.toLocaleDateString()}`;
  }
</script>

<div class="space-y-5" data-testid="produce-home">
  <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4 sm:p-6">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div class="max-w-2xl">
        <p class="vf-label text-sky-300/80">Produce</p>
        <h2 class="mt-1 text-[length:var(--vf-text-2xl)] font-semibold tracking-tight text-white">Start from a favorite</h2>
        <p class="mt-2 text-[length:var(--vf-text-sm)] leading-6 text-neutral-400">
          Pick a repeatable pipeline, review what needs you, and inspect the latest output. The graph builder stays one click away.
        </p>
      </div>
      <div class="flex flex-wrap gap-2">
        <Button variant="secondary" icon="folder" onclick={() => document.getElementById("recipe-library")?.scrollIntoView({ behavior: "smooth", block: "start" })}>Browse recipes</Button>
        <Button variant="primary" icon="activity" onclick={() => onreview()}>Open runs</Button>
      </div>
    </div>

    <div class="mt-4 grid gap-3 sm:grid-cols-3">
      <div class="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2">
        <p class="vf-label">Setup</p>
        <p class="mt-1 flex items-center gap-2 text-[length:var(--vf-text-sm)] text-neutral-100">
          <span class={`h-2 w-2 rounded-full ${system?.ffmpeg ? "bg-emerald-400" : "bg-amber-400"}`}></span>
          {system?.ffmpeg ? "FFmpeg ready" : "FFmpeg missing"}
        </p>
      </div>
      <div class="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2">
        <p class="vf-label">Favorites</p>
        <p class="mt-1 text-[length:var(--vf-text-sm)] text-neutral-100">{favorites.length} recipes</p>
      </div>
      <div class="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2">
        <p class="vf-label">Needs you</p>
        <p class="mt-1 text-[length:var(--vf-text-sm)] text-neutral-100">{pending.length} gates · {active.length} active</p>
      </div>
    </div>
  </section>

  {#if error}
    <p class="rounded-xl border border-rose-500/30 bg-rose-950/30 px-3 py-2 text-[length:var(--vf-text-xs)] text-rose-200">{error}</p>
  {/if}

  <div class="grid gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
      <div class="flex items-end justify-between gap-3">
        <div>
          <p class="vf-label">Favorites</p>
          <h3 class="mt-1 text-[length:var(--vf-text-lg)] font-semibold text-neutral-100">Your repeatable pipelines</h3>
        </div>
        <span class="text-[length:var(--vf-text-xs)] text-neutral-500">{favorites.length} pinned</span>
      </div>

      {#if loading}
        <div class="mt-4 flex items-center gap-3"><Progress value={40} label="Loading favorites" /><span class="text-[length:var(--vf-text-xs)] text-neutral-500">Loading recipes…</span></div>
      {:else if !favorites.length}
        <EmptyState
          title="No favorite recipes yet"
          description="Open the recipe library and star the pipelines you run most."
          action="Browse recipes"
          onaction={() => document.getElementById("recipe-library")?.scrollIntoView({ behavior: "smooth", block: "start" })}
        />
      {:else}
        <div class="mt-4 grid gap-3 md:grid-cols-2">
          {#each favorites as recipe (recipe.id)}
            <article class="group flex flex-col rounded-xl border border-neutral-800 bg-neutral-950/50 p-4 transition-colors hover:border-sky-500/40">
              <div class="flex items-start justify-between gap-2">
                <div class="min-w-0">
                  <h4 class="truncate text-[length:var(--vf-text-base)] font-semibold text-neutral-100">{recipe.name}</h4>
                  <p class="mt-1 line-clamp-2 text-[length:var(--vf-text-xs)] leading-5 text-neutral-500">{recipe.description || recipe.id}</p>
                </div>
                <button
                  type="button"
                  onclick={() => void toggleFavorite(recipe)}
                  class="rounded p-1 text-amber-300 hover:bg-white/5"
                  aria-label={`Remove ${recipe.name} from favorites`}
                  title="Remove from favorites"
                ><Icon name="star" size={16} /></button>
              </div>
              <div class="mt-3 flex flex-wrap items-center gap-2 text-[length:var(--vf-text-2xs)] text-neutral-500">
                <span class="rounded-full border border-white/10 px-2 py-0.5">{lastUsed(recipe)}</span>
                {#if recipe.use_count}<span>{recipe.use_count} runs</span>{/if}
              </div>
              <div class="mt-auto flex flex-wrap gap-2 pt-4">
                <Button variant="primary" icon="play" onclick={() => start(recipe.id)}>New run</Button>
                <Button variant="secondary" icon="code" onclick={() => onedit(recipe.id)}>Edit graph</Button>
              </div>
            </article>
          {/each}
        </div>
      {/if}
    </section>

    <div class="space-y-4">
      <section class="rounded-2xl border border-amber-400/20 bg-amber-950/10 p-4">
        <div class="flex items-center justify-between gap-2">
          <div>
            <p class="vf-label text-amber-300/80">Needs you</p>
            <h3 class="mt-1 text-[length:var(--vf-text-base)] font-semibold text-amber-100">Pending gates</h3>
          </div>
          <button type="button" onclick={() => onreview()} class="text-[length:var(--vf-text-xs)] text-amber-200 hover:text-amber-100">Open runs</button>
        </div>
        {#if pending.length}
          <ul class="mt-3 space-y-2">
            {#each pending.slice(0, 5) as item (item.interaction.interaction_id)}
              <li>
                <button type="button" onclick={() => onreview(item.job_id)} class="w-full rounded-lg border border-amber-400/15 bg-black/20 px-3 py-2 text-left transition-colors hover:border-amber-400/35">
                  <span class="block truncate text-[length:var(--vf-text-xs)] text-amber-100">{item.interaction.title}</span>
                  <span class="mt-0.5 block truncate text-[length:var(--vf-text-2xs)] text-amber-200/60">{recipeName(item.interaction.recipe_id)}</span>
                </button>
              </li>
            {/each}
          </ul>
        {:else}
          <p class="mt-3 text-[length:var(--vf-text-xs)] text-amber-100/60">Nothing is waiting. Start a run or continue editing.</p>
        {/if}
      </section>

      <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
        <p class="vf-label">Recent runs</p>
        <h3 class="mt-1 text-[length:var(--vf-text-base)] font-semibold text-neutral-100">Latest activity</h3>
        {#if recent.length}
          <ul class="mt-3 space-y-2">
            {#each recent as job (job.job_id)}
              <li>
                <button type="button" onclick={() => onreview(job.job_id)} class="w-full rounded-lg border border-neutral-800 bg-neutral-950/50 px-3 py-2 text-left transition-colors hover:border-sky-500/40">
                  <span class="flex items-center justify-between gap-2">
                    <span class="truncate text-[length:var(--vf-text-xs)] text-neutral-200">{jobDisplayName(job)}</span>
                    <StatusBadge status={job.status} />
                  </span>
                  <span class="mt-1 flex items-center gap-2 text-[length:var(--vf-text-2xs)] text-neutral-500">
                    <span class="truncate">{job.stage || job.message || job.job_id.slice(0, 8)}</span>
                    <span class="ml-auto font-mono">{job.progress}%</span>
                  </span>
                </button>
              </li>
            {/each}
          </ul>
        {:else}
          <p class="mt-3 text-[length:var(--vf-text-xs)] text-neutral-500">No runs yet.</p>
        {/if}
      </section>
    </div>
  </div>

  <section id="recipe-library" class="scroll-mt-24 rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4" data-testid="recipe-library-home">
    <div class="flex flex-wrap items-end justify-between gap-3">
      <div>
        <p class="vf-label">Library</p>
        <h3 class="mt-1 text-[length:var(--vf-text-lg)] font-semibold text-neutral-100">All recipes</h3>
        <p class="mt-1 text-[length:var(--vf-text-xs)] text-neutral-500">Favorites, recent runs, and every saved workflow.</p>
      </div>
      <input bind:value={query} placeholder="Search recipes…" class="w-full max-w-sm rounded-lg border border-neutral-700 bg-neutral-950 px-3 py-2 text-[length:var(--vf-text-xs)] text-neutral-100" />
    </div>
    <div class="mt-3 flex flex-wrap gap-1.5">
      {#each [["favorites", "Favorites"], ["recent", "Recent"], ["all", "All recipes"]] as [id, label]}
        <button
          type="button"
          onclick={() => (filter = id as RecipeFilter)}
          class={`rounded-lg border px-3 py-1.5 text-[length:var(--vf-text-xs)] transition-colors ${filter === id ? "border-sky-400/30 bg-sky-400/10 text-sky-100" : "border-neutral-800 text-neutral-400 hover:text-neutral-100"}`}
        >{label}</button>
      {/each}
    </div>

    {#if visible.length}
      <div class="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {#each visible as recipe (recipe.id)}
          <article class="flex flex-col rounded-xl border border-neutral-800 bg-neutral-950/50 p-4 transition-colors hover:border-sky-500/40">
            <div class="flex items-start justify-between gap-2">
              <div class="min-w-0">
                <h4 class="truncate text-[length:var(--vf-text-sm)] font-semibold text-neutral-100">{recipe.name}</h4>
                <p class="mt-1 line-clamp-2 text-[length:var(--vf-text-xs)] leading-5 text-neutral-500">{recipe.description || recipe.id}</p>
              </div>
              <button
                type="button"
                onclick={() => void toggleFavorite(recipe)}
                class={`rounded p-1 hover:bg-white/5 ${recipe.favorite ? "text-amber-300" : "text-neutral-600"}`}
                aria-label={recipe.favorite ? `Remove ${recipe.name} from favorites` : `Add ${recipe.name} to favorites`}
                title={recipe.favorite ? "Remove from favorites" : "Add to favorites"}
              ><Icon name="star" size={16} /></button>
            </div>
            <div class="mt-3 flex flex-wrap gap-1.5 text-[length:var(--vf-text-2xs)] text-neutral-500">
              <span class="rounded-full border border-white/10 px-2 py-0.5">{recipe.id}</span>
              {#if recipe.last_used_at}<span>{recipe.use_count} runs</span>{/if}
            </div>
            <div class="mt-auto flex flex-wrap gap-2 pt-4">
              <Button variant="primary" icon="play" onclick={() => start(recipe.id)}>New run</Button>
              <Button variant="secondary" icon="code" onclick={() => onedit(recipe.id)}>Edit graph</Button>
            </div>
          </article>
        {/each}
      </div>
    {:else}
      <EmptyState title="No recipe matches this filter" description="Clear the search or choose another filter." action="Show all" onaction={() => { filter = "all"; query = ""; }} />
    {/if}
  </section>
</div>

<RunComposer
  open={composerOpen}
  recipeId={composerRecipe}
  onclose={() => (composerOpen = false)}
  onstarted={started}
/>
