<script lang="ts">
  import { onMount } from "svelte";
  import {
    errorMessage,
    getPublishTargets,
    savePublishTarget,
    scheduleShortPublish,
    type PublishTarget
  } from "$lib/api";

  let {
    jobId,
    index,
    allowExternal = false,
    allowedHosts = ""
  }: {
    jobId: string;
    index: number;
    allowExternal?: boolean;
    allowedHosts?: string;
  } = $props();
  let targets = $state<PublishTarget[]>([]);
  let selected = $state("");
  let platform = $state("youtube");
  let tone = $state("engaging");
  let scheduledAt = $state("");
  let targetName = $state("");
  let webhookUrl = $state("");
  let busy = $state(false);
  let message = $state("");
  let error = $state("");

  async function refresh() {
    try {
      targets = await getPublishTargets();
      if (!selected && targets.length) selected = targets[0].name;
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function addTarget() {
    if (!targetName.trim() || !webhookUrl.trim() || busy) return;
    busy = true;
    error = "";
    try {
      await savePublishTarget(targetName.trim(), webhookUrl.trim());
      targetName = "";
      webhookUrl = "";
      await refresh();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  async function schedule() {
    if (!selected || busy) return;
    busy = true;
    error = "";
    message = "";
    try {
      const hosts = allowedHosts
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      const item = await scheduleShortPublish(jobId, index, {
        target: selected,
        platform,
        tone,
        scheduled_at: scheduledAt ? new Date(scheduledAt).toISOString() : null,
        allow_external_services: allowExternal,
        allowed_external_hosts: hosts
      });
      message = `Scheduled ${item.id} · ${item.status}`;
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  onMount(() => {
    void refresh();
  });
</script>

<div class="rounded-xl border border-neutral-800 bg-neutral-950/60 p-3">
  <p class="text-[10px] uppercase tracking-wide text-neutral-500">Publish / schedule</p>
  <div class="mt-2 grid gap-2 sm:grid-cols-3">
    <select
      value={selected}
      onchange={(event) => (selected = event.currentTarget.value)}
      class="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100"
    >
      <option value="">Select target</option>
      {#each targets as target}<option value={target.name}>{target.name}</option>{/each}
    </select>
    <select
      value={platform}
      onchange={(event) => (platform = event.currentTarget.value)}
      class="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100"
    >
      <option value="youtube">YouTube</option>
      <option value="tiktok">TikTok</option>
      <option value="instagram">Instagram</option>
      <option value="linkedin">LinkedIn</option>
    </select>
    <select
      value={tone}
      onchange={(event) => (tone = event.currentTarget.value)}
      class="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100"
    >
      <option value="engaging">Engaging</option>
      <option value="professional">Professional</option>
      <option value="educational">Educational</option>
      <option value="bold">Bold</option>
    </select>
  </div>
  <div class="mt-2 grid gap-2 sm:grid-cols-[1fr_auto]">
    <input
      type="datetime-local"
      value={scheduledAt}
      oninput={(event) => (scheduledAt = event.currentTarget.value)}
      class="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100"
    />
    <button
      type="button"
      onclick={schedule}
      disabled={busy || !selected || !allowExternal}
      class="rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-[10px] text-emerald-200 disabled:opacity-40"
    >
      {busy ? "Scheduling…" : "Schedule"}
    </button>
  </div>
  {#if !allowExternal}
    <p class="mt-1 text-[10px] text-amber-300">Enable external services in Providers first.</p>
  {/if}
  {#if message}<p class="mt-1 text-[10px] text-emerald-300">{message}</p>{/if}
  {#if error}<p class="mt-1 text-[10px] text-rose-300">{error}</p>{/if}

  <details class="mt-2">
    <summary class="cursor-pointer text-[10px] text-neutral-500">Add webhook target</summary>
    <div class="mt-2 grid gap-2 sm:grid-cols-2">
      <input type="text" value={targetName} oninput={(event) => (targetName = event.currentTarget.value)} placeholder="Target name" class="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" />
      <input type="url" value={webhookUrl} oninput={(event) => (webhookUrl = event.currentTarget.value)} placeholder="https://hook.example/publish" class="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" />
    </div>
    <button type="button" onclick={addTarget} disabled={busy || !targetName.trim() || !webhookUrl.trim()} class="mt-2 rounded-lg border border-neutral-700 px-2.5 py-1.5 text-[10px] text-neutral-300 disabled:opacity-40">
      Save target
    </button>
  </details>
</div>
