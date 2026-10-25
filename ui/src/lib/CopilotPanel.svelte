<script lang="ts">
  import { onMount } from "svelte";
  import ErrorBanner from "$lib/ErrorBanner.svelte";
  import {
    assistantTurn,
    approveAssistant,
    copilotRecipe,
    copilotTimeline,
    errorMessage,
    getAssistantHistory,
    listJobs,
    saveRecipe,
    type AssistantAction,
    type AssistantHistoryEntry,
    type Job
  } from "$lib/api";

  let mode = $state<"recipe" | "timeline" | "agent">("recipe");
  let prompt = $state("");
  let jobs = $state<Job[]>([]);
  let jobId = $state("");
  let busy = $state(false);
  let error = $state("");
  let status = $state("");
  let draft = $state<Record<string, unknown> | null>(null);
  let edits = $state<Array<Record<string, unknown>>>([]);
  let apply = $state(true);
  let agentMessage = $state("");
  let agentActions = $state<AssistantAction[]>([]);
  let agentDiff = $state<Array<Record<string, unknown>>>([]);
  let observations = $state<Array<Record<string, unknown>>>([]);
  let approvalId = $state("");
  let tokens = $state(0);
  let cost = $state(0);
  let history = $state<AssistantHistoryEntry[]>([]);

  onMount(async () => {
    try {
      jobs = (await listJobs()).filter((job) => job.status === "succeeded");
      jobId = jobs[0]?.job_id ?? "";
    } catch (reason) {
      error = errorMessage(reason);
    }
  });

  async function generate() {
    if (!prompt.trim()) return;
    busy = true;
    error = "";
    status = "";
    draft = null;
    edits = [];
    try {
      if (mode === "recipe") {
        draft = await copilotRecipe(prompt.trim());
        status = "Recipe draft validated. Save it or refine the prompt.";
      } else if (mode === "timeline") {
        if (!jobId) throw new Error("Select a finished job first.");
        const result = await copilotTimeline(jobId, prompt.trim(), apply);
        edits = result.edits;
        status = `${result.edits.length} edit(s) ${apply ? "applied" : "proposed"} at revision ${result.revision}.`;
      } else {
        if (!jobId) throw new Error("Select a finished job first.");
        const turn = await assistantTurn(jobId, prompt.trim());
        agentMessage = turn.message;
        agentActions = turn.actions;
        agentDiff = turn.diff;
        observations = turn.observations;
        approvalId = turn.approval_id;
        tokens = turn.tokens;
        cost = turn.cost_usd;
        history = await getAssistantHistory(jobId);
        status = turn.requires_approval
          ? "Review the diff and approve to apply."
          : "Answer ready. Nothing was written.";
      }
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  async function approve() {
    if (!jobId || !approvalId) return;
    busy = true;
    error = "";
    try {
      await approveAssistant(jobId, approvalId);
      status = "Approved and applied. Undo is available in the timeline.";
      approvalId = "";
      history = await getAssistantHistory(jobId);
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  async function save() {
    if (!draft) return;
    busy = true;
    try {
      await saveRecipe(draft as never);
      status = "Recipe saved to the local library.";
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }
</script>

<section class="space-y-4" data-testid="copilot-panel">
  <header>
    <h2 class="text-lg font-semibold text-white">Assistant</h2>
    <p class="mt-1 text-xs text-neutral-500">
      Use the configured LLM provider to draft a recipe or propose timeline edits. Every proposal is validated before it touches the project.
    </p>
  </header>

  <ErrorBanner message={error} title="Copilot error" onDismiss={() => (error = "")} testId="copilot-error" />

  <div class="flex flex-wrap gap-2">
    <button type="button" class={mode === "recipe" ? "rounded-xl bg-sky-500/15 px-3 py-1.5 text-xs text-sky-200 ring-1 ring-inset ring-sky-400/25" : "rounded-xl border border-neutral-800 px-3 py-1.5 text-xs text-neutral-400"} onclick={() => (mode = "recipe")}>Recipe draft</button>
    <button type="button" class={mode === "timeline" ? "rounded-xl bg-sky-500/15 px-3 py-1.5 text-xs text-sky-200 ring-1 ring-inset ring-sky-400/25" : "rounded-xl border border-neutral-800 px-3 py-1.5 text-xs text-neutral-400"} onclick={() => (mode = "timeline")}>Timeline edit</button>
    <button type="button" class={mode === "agent" ? "rounded-xl bg-sky-500/15 px-3 py-1.5 text-xs text-sky-200 ring-1 ring-inset ring-sky-400/25" : "rounded-xl border border-neutral-800 px-3 py-1.5 text-xs text-neutral-400"} onclick={() => (mode = "agent")}>Agent tools</button>
  </div>

  {#if mode !== "recipe"}
    <label class="block text-xs text-neutral-400">
      Job
      <select bind:value={jobId} class="mt-1 w-full rounded-xl border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-200">
        {#each jobs as job (job.job_id)}
          <option value={job.job_id}>{job.source.split("/").pop()} · {job.job_id.slice(0, 8)}</option>
        {/each}
      </select>
    </label>
  {/if}

  <label class="block text-xs text-neutral-400">
    Instruction
    <textarea bind:value={prompt} rows="4" class="mt-1 w-full rounded-xl border border-neutral-700 bg-neutral-950 px-3 py-2 text-xs text-neutral-100" placeholder={mode === "recipe" ? "Create a recipe that removes silence, adds captions, and renders three vertical Shorts." : "Tighten the first clip and remove the last one."}></textarea>
  </label>

  <div class="flex flex-wrap items-center gap-2">
    <button type="button" onclick={() => void generate()} disabled={busy || !prompt.trim()} class="rounded-xl bg-sky-500/15 px-3 py-1.5 text-xs text-sky-200 ring-1 ring-inset ring-sky-400/25 disabled:opacity-40">
      {busy ? "Working…" : mode === "recipe" ? "Draft recipe" : mode === "timeline" ? "Propose edits" : "Ask the agent"}
    </button>
    {#if mode === "timeline"}
      <label class="flex items-center gap-1.5 text-[11px] text-neutral-400">
        <input type="checkbox" bind:checked={apply} class="h-3.5 w-3.5 accent-sky-500" />
        Apply to the timeline
      </label>
    {/if}
    {#if draft}
      <button type="button" onclick={() => void save()} disabled={busy} class="rounded-xl border border-emerald-400/30 px-3 py-1.5 text-xs text-emerald-200 disabled:opacity-40">Save recipe</button>
    {/if}
  </div>

  {#if status}<p class="text-[11px] text-neutral-400">{status}</p>{/if}

  {#if draft}
    <pre class="max-h-[420px] overflow-auto rounded-xl border border-neutral-800 bg-black/40 p-3 text-[10px] text-neutral-300">{JSON.stringify(draft, null, 2)}</pre>
  {/if}

  {#if agentMessage}
    <div class="rounded-xl border border-sky-400/20 bg-sky-950/20 p-3" data-testid="assistant-answer">
      <p class="text-xs text-sky-100">{agentMessage}</p>
      <p class="mt-1 text-[10px] text-sky-200/60">{tokens} tokens · ${cost.toFixed(4)} estimated</p>
      {#if agentActions.length}
        <ul class="mt-2 space-y-1">
          {#each agentActions as action (action.id)}
            <li class="rounded-lg border border-white/10 bg-black/20 px-2 py-1 font-mono text-[10px] text-neutral-300">{action.tool} · {JSON.stringify(action.arguments)}</li>
          {/each}
        </ul>
      {/if}
      {#if agentDiff.length}
        <ul class="mt-2 space-y-1" data-testid="assistant-diff">
          {#each agentDiff as change}
            <li class="rounded-lg border border-amber-400/20 bg-amber-950/20 px-2 py-1 text-[10px] text-amber-100">{JSON.stringify(change)}</li>
          {/each}
        </ul>
      {/if}
      {#if observations.length}
        <details class="mt-2 text-[10px] text-neutral-400">
          <summary class="cursor-pointer">Tool observations</summary>
          <pre class="mt-1 max-h-48 overflow-auto rounded-lg bg-black/30 p-2">{JSON.stringify(observations, null, 2)}</pre>
        </details>
      {/if}
      {#if approvalId}
        <button type="button" onclick={() => void approve()} disabled={busy} class="mt-2 rounded-lg border border-emerald-400/30 px-2.5 py-1 text-[11px] text-emerald-200 disabled:opacity-40">Approve and apply</button>
      {/if}
    </div>
  {/if}

  {#if mode === "agent" && history.length}
    <div class="space-y-1">
      <p class="text-[10px] uppercase tracking-wide text-neutral-500">Conversation history</p>
      {#each history.slice(-6).reverse() as entry}
        <p class="rounded-lg border border-neutral-800 bg-white/[0.02] px-2 py-1 text-[10px] text-neutral-400"><span class="text-neutral-200">{entry.prompt}</span> · {entry.applied ? "applied" : "not applied"} · {entry.tokens} tokens</p>
      {/each}
    </div>
  {/if}

  {#if edits.length}
    <ul class="space-y-1">
      {#each edits as edit}
        <li class="rounded-lg border border-neutral-800 bg-white/[0.02] px-2 py-1 font-mono text-[10px] text-neutral-300">{JSON.stringify(edit)}</li>
      {/each}
    </ul>
  {/if}
</section>
