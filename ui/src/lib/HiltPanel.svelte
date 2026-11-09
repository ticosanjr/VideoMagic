<script lang="ts">
  import {
    errorMessage,
    respondToInteraction,
    uploadInteractionFiles,
    type HiltInteraction,
    type Job
  } from "$lib/api";

  let {
    job,
    onresumed,
    onerror
  }: {
    job: Job;
    onresumed?: (job: Job) => void;
    onerror?: (message: string) => void;
  } = $props();

  let interaction = $state<HiltInteraction | null>(null);
  let answers = $state<Record<string, unknown>>({});
  let comment = $state("");
  let files = $state<Record<string, File[]>>({});
  let busy = $state(false);
  let status = $state("");
  let localError = $state("");

  $effect(() => {
    const next =
      job.interaction ??
      ((job.error as { interaction?: HiltInteraction } | null)?.interaction ?? null);
    if (next) interaction = next;
  });

  function setAnswer(id: string, value: unknown) {
    answers = { ...answers, [id]: value };
  }

  function setFile(requestId: string, selected: FileList | null) {
    files = { ...files, [requestId]: selected ? Array.from(selected) : [] };
  }

  function fail(message: string) {
    localError = message;
    onerror?.(message);
  }

  async function submit(action: "approve" | "reject" | "submit") {
    if (!interaction) return;
    busy = true;
    localError = "";
    status = "";
    try {
      for (const request of interaction.files) {
        const selected = files[request.id] ?? [];
        if (request.required && selected.length === 0) {
          throw new Error(`${request.label} is required.`);
        }
        if (selected.length > 0) {
          await uploadInteractionFiles(job.job_id, interaction.interaction_id, selected, request.id);
        }
      }
      const resumed = await respondToInteraction(job.job_id, interaction.interaction_id, {
        action,
        answers,
        comment
      });
      status = action === "reject" ? "Rejected; the job will record the decision." : "Answer saved. Resuming…";
      onresumed?.(resumed);
    } catch (reason) {
      fail(errorMessage(reason));
    } finally {
      busy = false;
    }
  }
</script>

{#if interaction}
  <section class="mt-3 rounded-xl border border-amber-400/30 bg-amber-950/20 p-3" data-testid="hilt-panel">
    <div class="flex flex-wrap items-start justify-between gap-2">
      <div>
        <p class="text-[10px] uppercase tracking-wide text-amber-300/70">
          {interaction.kind === "approval" ? "Approval required" : "Waiting for your input"}
        </p>
        <h3 class="mt-1 text-sm font-medium text-amber-100">{interaction.title}</h3>
        {#if interaction.description}
          <p class="mt-1 whitespace-pre-wrap text-[11px] text-amber-100/70">{interaction.description}</p>
        {/if}
      </div>
      <span class="rounded-full border border-amber-400/30 px-2 py-0.5 text-[10px] uppercase text-amber-200">
        {interaction.kind}
      </span>
    </div>

    {#if interaction.artifacts.length}
      <div class="mt-3">
        <p class="text-[10px] uppercase tracking-wide text-amber-300/60">Review artifacts</p>
        <div class="mt-1 grid gap-1">
          {#each interaction.artifacts as artifact (artifact.id)}
            <a
              class="flex items-center justify-between gap-2 rounded-lg border border-amber-400/10 bg-black/20 px-2 py-1 text-[11px] text-amber-100 hover:border-amber-400/30"
              href={artifact.download_url}
              target="_blank"
              rel="noreferrer"
            >
              <span class="truncate">{artifact.label}</span>
              <span class="shrink-0 text-[9px] text-amber-300/60">
                {artifact.exists ? `${Math.max(1, Math.round(artifact.size_bytes / 1024))} KB` : "missing"}
              </span>
            </a>
          {/each}
        </div>
      </div>
    {/if}

    {#if interaction.questions.length}
      <div class="mt-3 space-y-2">
        {#each interaction.questions as question (question.id)}
          <label class="block text-[10px] text-amber-100/70">
            <span>{question.label}{question.required ? " *" : ""}</span>
            {#if question.help}<span class="mt-0.5 block text-[9px] text-amber-100/40">{question.help}</span>{/if}
            {#if question.type === "textarea"}
              <textarea
                rows="3"
                placeholder={question.placeholder}
                value={String(answers[question.id] ?? question.default ?? "")}
                oninput={(event) => setAnswer(question.id, event.currentTarget.value)}
                class="mt-1 w-full rounded-lg border border-amber-400/20 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100"
              ></textarea>
            {:else if question.type === "choice"}
              <select
                value={String(answers[question.id] ?? question.default ?? "")}
                onchange={(event) => setAnswer(question.id, event.currentTarget.value)}
                class="mt-1 w-full rounded-lg border border-amber-400/20 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100"
              >
                <option value="">Choose…</option>
                {#each question.options as option}
                  <option value={String(option)}>{String(option)}</option>
                {/each}
              </select>
            {:else if question.type === "boolean"}
              <span class="mt-1 flex items-center gap-2 text-[11px] text-amber-100">
                <input
                  type="checkbox"
                  checked={Boolean(answers[question.id] ?? question.default ?? false)}
                  onchange={(event) => setAnswer(question.id, event.currentTarget.checked)}
                  class="h-3.5 w-3.5"
                />
                Yes
              </span>
            {:else if question.type === "number"}
              <input
                type="number"
                value={String(answers[question.id] ?? question.default ?? "")}
                oninput={(event) => setAnswer(question.id, Number(event.currentTarget.value))}
                class="mt-1 w-full rounded-lg border border-amber-400/20 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100"
              />
            {:else}
              <input
                type="text"
                placeholder={question.placeholder}
                value={String(answers[question.id] ?? question.default ?? "")}
                oninput={(event) => setAnswer(question.id, event.currentTarget.value)}
                class="mt-1 w-full rounded-lg border border-amber-400/20 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100"
              />
            {/if}
          </label>
        {/each}
      </div>
    {/if}

    {#if interaction.files.length}
      <div class="mt-3 space-y-2">
        {#each interaction.files as request (request.id)}
          <label class="block rounded-lg border border-dashed border-amber-400/20 bg-black/10 px-2 py-2 text-[10px] text-amber-100/70">
            <span>{request.label}{request.required ? " *" : ""}</span>
            {#if request.help}<span class="mt-0.5 block text-[9px] text-amber-100/40">{request.help}</span>{/if}
            <input
              type="file"
              multiple
              accept={request.accept.join(",")}
              onchange={(event) => setFile(request.id, event.currentTarget.files)}
              class="mt-1 block w-full text-[10px] text-amber-100/60"
            />
            {#if request.target}<span class="mt-0.5 block font-mono text-[9px] text-amber-100/30">→ {request.target}</span>{/if}
          </label>
        {/each}
      </div>
    {/if}

    <label class="mt-3 block text-[10px] text-amber-100/60">
      Comment
      <textarea
        rows="2"
        bind:value={comment}
        placeholder="Decision notes, feedback, or the reason for a correction"
        class="mt-1 w-full rounded-lg border border-amber-400/20 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100"
      ></textarea>
    </label>

    {#if localError}
      <p class="mt-2 rounded-lg border border-rose-500/30 bg-rose-950/30 px-2 py-1 text-[11px] text-rose-200">{localError}</p>
    {/if}
    {#if status}
      <p class="mt-2 text-[11px] text-emerald-300" role="status">{status}</p>
    {/if}

    <div class="mt-3 flex flex-wrap gap-2">
      {#if interaction.kind === "approval"}
        <button
          type="button"
          onclick={() => void submit("approve")}
          disabled={busy}
          class="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-[11px] text-emerald-200 disabled:opacity-40"
        >{interaction.approve_label || "Approve and resume"}</button>
        <button
          type="button"
          onclick={() => void submit("reject")}
          disabled={busy}
          class="rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-1.5 text-[11px] text-rose-200 disabled:opacity-40"
        >{interaction.reject_label || "Reject"}</button>
      {:else}
        <button
          type="button"
          onclick={() => void submit("submit")}
          disabled={busy}
          class="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-[11px] text-sky-200 disabled:opacity-40"
        >{busy ? "Submitting…" : "Submit and resume"}</button>
      {/if}
      <span class="self-center text-[9px] text-amber-100/40">
        {interaction.channels.join(" · ") || "local"} · expires {interaction.expires_at || "later"}
      </span>
    </div>
  </section>
{/if}
