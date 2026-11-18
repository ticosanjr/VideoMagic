<script lang="ts">
  import { onMount } from "svelte";
  import {
    deleteStyle,
    deleteWorkflow,
    duplicateStyle,
    restoreStyle,
    duplicateWorkflow,
    errorMessage,
    getAgentsFile,
    getStyle,
    getWorkflow,
    listStyles,
    listWorkflows,
    restoreAgentsFile,
    restoreWorkflow,
    saveAgentsFile,
    saveStyleMarkdown,
    saveWorkflow,
    type StyleSummary,
    type WorkflowSummary
  } from "$lib/api";
  import HelpTip from "$lib/HelpTip.svelte";

  let tab = $state<"agents" | "workflows" | "styles">("agents");
  let workspace = $state("");
  let agents = $state("");
  let workflows = $state<WorkflowSummary[]>([]);
  let styles = $state<StyleSummary[]>([]);
  let selectedWorkflow = $state("");
  let selectedStyle = $state("");
  let workflowMarkdown = $state("");
  let styleMarkdown = $state("");
  let status = $state("");
  let error = $state("");
  let busy = $state(false);

  onMount(() => {
    void reload();
  });

  async function reload() {
    try {
      workflows = await listWorkflows();
      styles = await listStyles();
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function loadAgents() {
    if (!workspace.trim()) return;
    busy = true;
    error = "";
    try {
      const result = await getAgentsFile(workspace.trim());
      agents = result.content;
      status = "AGENTS.md carregado";
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  async function saveAgents() {
    if (!workspace.trim()) return;
    busy = true;
    error = "";
    try {
      await saveAgentsFile(workspace.trim(), agents);
      status = "AGENTS.md salvo e sincronizado";
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  async function restoreAgents() {
    if (!workspace.trim()) return;
    busy = true;
    error = "";
    try {
      const result = await restoreAgentsFile(workspace.trim());
      agents = result.content;
      status = "AGENTS.md restaurado";
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  async function openWorkflow(id: string) {
    selectedWorkflow = id;
    try {
      const result = await getWorkflow(id);
      workflowMarkdown = result.markdown;
      status = `Workflow ${id} carregado`;
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function saveCurrentWorkflow() {
    if (!selectedWorkflow) return;
    busy = true;
    error = "";
    try {
      await saveWorkflow({
        workflow_id: selectedWorkflow,
        markdown_content: workflowMarkdown,
        workspace_dir: workspace.trim(),
        overwrite: true
      });
      await reload();
      status = `Workflow ${selectedWorkflow} salvo`;
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  async function newWorkflow() {
    const id = window.prompt("Novo workflow_id", "meu-workflow")?.trim();
    if (!id) return;
    try {
      await saveWorkflow({ workflow_id: id, name: id });
      await reload();
      await openWorkflow(id);
      status = `Workflow criado: ${id}`;
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function newStyle() {
    const id = window.prompt("Novo style_id", "meu-estilo")?.trim();
    if (!id) return;
    try {
      await saveStyleMarkdown({
        style_id: id,
        name: id,
        markdown_content: `---\nschema_version: 2\nversion: 1\nstyle_id: ${id}\nname: ${id}\naspect_ratio: "9:16"\nlayout_mode: "fullscreen"\nmotion_engine: "ffmpeg"\nexport_targets:\n  - mp4_youtube\n  - resolve\n  - premiere\n  - kdenlive\n---\n\n# ${id}\n`
      });
      await reload();
      await openStyle(id);
      status = `Estilo criado: ${id}`;
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function duplicateCurrentWorkflow() {
    if (!selectedWorkflow) return;
    const newId = window.prompt("Novo workflow_id", `${selectedWorkflow}-copy`)?.trim();
    if (!newId) return;
    try {
      await duplicateWorkflow(selectedWorkflow, { new_id: newId });
      await reload();
      status = `Workflow duplicado: ${newId}`;
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function removeCurrentWorkflow() {
    if (!selectedWorkflow) return;
    try {
      await deleteWorkflow(selectedWorkflow);
      selectedWorkflow = "";
      workflowMarkdown = "";
      await reload();
      status = "Workflow removido";
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function restoreCurrentWorkflow() {
    if (!selectedWorkflow) return;
    try {
      await restoreWorkflow(selectedWorkflow);
      await openWorkflow(selectedWorkflow);
      status = "Workflow restaurado do seed";
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function openStyle(id: string) {
    selectedStyle = id;
    try {
      const result = await getStyle(id);
      styleMarkdown = result.markdown;
      status = `Estilo ${id} carregado`;
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function saveCurrentStyle() {
    if (!selectedStyle) return;
    busy = true;
    error = "";
    try {
      await saveStyleMarkdown({
        style_id: selectedStyle,
        markdown_content: styleMarkdown,
        workspace_dir: workspace.trim(),
        overwrite: true
      });
      await reload();
      status = `Estilo ${selectedStyle} salvo`;
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  async function duplicateCurrentStyle() {
    if (!selectedStyle) return;
    const newId = window.prompt("Novo style_id", `${selectedStyle}-copy`)?.trim();
    if (!newId) return;
    try {
      await duplicateStyle(selectedStyle, { new_id: newId });
      await reload();
      await openStyle(newId);
      status = `Estilo duplicado: ${newId}`;
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function restoreCurrentStyle() {
    if (!selectedStyle) return;
    try {
      await restoreStyle(selectedStyle);
      await openStyle(selectedStyle);
      status = "Estilo restaurado do seed";
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function removeCurrentStyle() {
    if (!selectedStyle) return;
    try {
      await deleteStyle(selectedStyle);
      selectedStyle = "";
      styleMarkdown = "";
      await reload();
      status = "Estilo removido";
    } catch (reason) {
      error = errorMessage(reason);
    }
  }
</script>

<section class="space-y-3 rounded-2xl border border-violet-500/25 bg-violet-500/5 p-4" data-testid="opencode-manager">
  <header>
    <div class="flex items-center gap-1.5">
      <h3 class="text-sm font-semibold text-violet-100">OpenCode Studio Manager</h3>
      <HelpTip label="Studio Manager" body="Edite AGENTS.md, workflows e estilos; o bootstrap copia tudo para o workspace OpenCode." doc="docs/opencode.md" />
    </div>
    <p class="mt-1 text-[11px] leading-relaxed text-neutral-300">
      Direção do agente em arquivos Markdown: protocolo mestre, playbooks e catálogo visual.
    </p>
  </header>

  <div class="flex flex-wrap gap-1">
    {#each [["agents", "AGENTS.md"], ["workflows", "Workflows"], ["styles", "Estilos"]] as [id, label] (id)}
      <button
        type="button"
        class={`rounded-lg border px-2.5 py-1 text-[10px] ${tab === id ? "border-violet-400/50 bg-violet-500/20 text-violet-100" : "border-white/10 text-neutral-400 hover:text-violet-200"}`}
        onclick={() => (tab = id as "agents" | "workflows" | "styles")}
      >{label}</button>
    {/each}
  </div>

  <label class="block text-[11px] text-neutral-300">
    <span class="mb-1 block font-medium text-neutral-200">Workspace OpenCode</span>
    <div class="flex gap-2">
      <input
        class="min-w-0 flex-1 rounded-lg border border-neutral-700 bg-black/40 px-2 py-1.5 font-mono text-[11px] text-neutral-100 outline-none focus:border-violet-400/60"
        bind:value={workspace}
        placeholder="/home/you/Videos/canal"
        data-testid="opencode-manager-workspace"
      />
      <button type="button" class="rounded-lg border border-white/10 px-2 py-1 text-[10px] text-neutral-300 hover:text-violet-200" onclick={() => void loadAgents()}>Load</button>
    </div>
  </label>

  {#if error}
    <p class="rounded-lg border border-rose-500/30 bg-rose-500/10 p-2 text-[11px] text-rose-200">{error}</p>
  {/if}
  {#if status}
    <p class="text-[10px] text-violet-200">{status}</p>
  {/if}

  {#if tab === "agents"}
    <div class="space-y-2">
      <div class="flex flex-wrap gap-2">
        <button type="button" class="rounded-lg border border-violet-400/30 bg-violet-500/15 px-2.5 py-1 text-[10px] text-violet-100" onclick={() => void saveAgents()} disabled={busy || !workspace.trim()}>Salvar & Sincronizar</button>
        <button type="button" class="rounded-lg border border-white/10 px-2.5 py-1 text-[10px] text-neutral-300" onclick={() => void restoreAgents()} disabled={busy || !workspace.trim()}>Restaurar Padrão Diretor Lego</button>
      </div>
      <textarea class="h-72 w-full rounded-xl border border-neutral-700 bg-black/50 p-3 font-mono text-[11px] text-neutral-100" bind:value={agents} spellcheck="false" data-testid="opencode-agents-editor"></textarea>
    </div>
  {:else if tab === "workflows"}
    <div class="grid gap-3 lg:grid-cols-[220px_1fr]">
      <div class="space-y-1">
        {#each workflows as item (item.workflow_id)}
          <button type="button" class={`block w-full rounded-lg border px-2 py-1 text-left text-[10px] ${selectedWorkflow === item.workflow_id ? "border-violet-400/50 bg-violet-500/15 text-violet-100" : "border-white/10 text-neutral-300"}`} onclick={() => void openWorkflow(item.workflow_id)}>
            <span class="font-mono">{item.workflow_id}</span><br /><span class="text-neutral-500">{item.name}</span>
          </button>
        {/each}
      </div>
      <div class="space-y-2">
        <div class="flex flex-wrap gap-2">
          <button type="button" class="rounded-lg border border-white/10 px-2 py-1 text-[10px] text-neutral-300" onclick={() => void newWorkflow()}>Novo</button>
          <button type="button" class="rounded-lg border border-violet-400/30 px-2 py-1 text-[10px] text-violet-100" onclick={() => void saveCurrentWorkflow()} disabled={!selectedWorkflow || busy}>Salvar</button>
          <button type="button" class="rounded-lg border border-white/10 px-2 py-1 text-[10px] text-neutral-300" onclick={() => void duplicateCurrentWorkflow()} disabled={!selectedWorkflow}>Duplicar</button>
          <button type="button" class="rounded-lg border border-white/10 px-2 py-1 text-[10px] text-neutral-300" onclick={() => void restoreCurrentWorkflow()} disabled={!selectedWorkflow}>Restaurar seed</button>
          <button type="button" class="rounded-lg border border-rose-500/30 px-2 py-1 text-[10px] text-rose-200" onclick={() => void removeCurrentWorkflow()} disabled={!selectedWorkflow}>Excluir</button>
        </div>
        <textarea class="h-72 w-full rounded-xl border border-neutral-700 bg-black/50 p-3 font-mono text-[11px] text-neutral-100" bind:value={workflowMarkdown} spellcheck="false" data-testid="opencode-workflow-editor"></textarea>
      </div>
    </div>
  {:else}
    <div class="grid gap-3 lg:grid-cols-[220px_1fr]">
      <div class="max-h-80 space-y-1 overflow-auto">
        {#each styles as item (item.style_id)}
          <button type="button" class={`block w-full rounded-lg border px-2 py-1 text-left text-[10px] ${selectedStyle === item.style_id ? "border-violet-400/50 bg-violet-500/15 text-violet-100" : "border-white/10 text-neutral-300"}`} onclick={() => void openStyle(item.style_id)}>
            <span class="font-mono">{item.style_id}</span><br /><span class="text-neutral-500">{item.name}</span>
          </button>
        {/each}
      </div>
      <div class="space-y-2">
        <div class="flex flex-wrap gap-2">
          <button type="button" class="rounded-lg border border-white/10 px-2 py-1 text-[10px] text-neutral-300" onclick={() => void newStyle()}>Novo</button>
          <button type="button" class="rounded-lg border border-violet-400/30 px-2 py-1 text-[10px] text-violet-100" onclick={() => void saveCurrentStyle()} disabled={!selectedStyle || busy}>Salvar</button>
          <button type="button" class="rounded-lg border border-white/10 px-2 py-1 text-[10px] text-neutral-300" onclick={() => void duplicateCurrentStyle()} disabled={!selectedStyle}>Duplicar</button>
          <button type="button" class="rounded-lg border border-white/10 px-2 py-1 text-[10px] text-neutral-300" onclick={() => void restoreCurrentStyle()} disabled={!selectedStyle}>Restaurar seed</button>
          <button type="button" class="rounded-lg border border-rose-500/30 px-2 py-1 text-[10px] text-rose-200" onclick={() => void removeCurrentStyle()} disabled={!selectedStyle}>Excluir</button>
        </div>
        <textarea class="h-72 w-full rounded-xl border border-neutral-700 bg-black/50 p-3 font-mono text-[11px] text-neutral-100" bind:value={styleMarkdown} spellcheck="false" data-testid="opencode-style-editor"></textarea>
      </div>
    </div>
  {/if}
</section>
