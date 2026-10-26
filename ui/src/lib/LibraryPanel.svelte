<script lang="ts">
  import HelpTip from "$lib/HelpTip.svelte";
  import Icon from "$lib/ui/Icon.svelte";
  import { onMount } from "svelte";
  import ErrorBanner from "$lib/ErrorBanner.svelte";
  import {
    applyBrandTemplate,
    applyProjectTemplate,
    deleteBrandTemplate,
    deleteFontAsset,
    deleteImageAsset,
    deleteMusicAsset,
    deleteSfxAsset,
    deleteProjectTemplate,
    errorMessage,
    getBrandTemplates,
    getFonts,
    getImages,
    getMusic,
    getSfx,
    getPresets,
    getProjectTemplates,
    saveBrandTemplate,
    savePreset,
    saveProjectTemplate,
    uploadFont,
    uploadImage,
    uploadMusic,
    uploadSfx,
    type BrandTemplate,
    type FontAsset,
    type ImageAsset,
    type MusicAsset,
    type ProjectTemplate
  } from "$lib/api";

  let brands = $state<BrandTemplate[]>([]);
  let projects = $state<ProjectTemplate[]>([]);
  let presets = $state<Array<{ name: string; preset: Record<string, unknown> }>>([]);
  let music = $state<MusicAsset[]>([]);
  let sfx = $state<MusicAsset[]>([]);
  let images = $state<ImageAsset[]>([]);
  let fonts = $state<FontAsset[]>([]);
  let error = $state("");
  let status = $state("");
  let brandName = $state("");
  let brandDescription = $state("");
  let brandJson = $state('{"caption_style": {}, "overlay": {}, "music": {}, "intro_outro": {}}');
  let projectName = $state("");
  let projectDescription = $state("");
  let projectJson = $state("{}");
  let presetName = $state("");
  let presetJson = $state("{}");

  async function load() {
    try {
      [brands, projects, presets, music, sfx, images, fonts] = await Promise.all([
        getBrandTemplates(),
        getProjectTemplates(),
        getPresets(),
        getMusic(),
        getSfx(),
        getImages(),
        getFonts()
      ]);
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function saveBrand() {
    try {
      const parsed = JSON.parse(brandJson) as Omit<BrandTemplate, "name">;
      await saveBrandTemplate(brandName.trim(), {
        description: brandDescription,
        caption_style: parsed.caption_style ?? {},
        overlay: parsed.overlay ?? {},
        music: parsed.music ?? {},
        intro_outro: parsed.intro_outro ?? {}
      });
      status = `Brand template ${brandName} saved.`;
      await load();
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function saveProject() {
    try {
      await saveProjectTemplate(
        projectName.trim(),
        projectDescription,
        JSON.parse(projectJson) as Record<string, unknown>
      );
      status = `Project template ${projectName} saved.`;
      await load();
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function savePresetDraft() {
    try {
      await savePreset(presetName.trim(), JSON.parse(presetJson) as Record<string, unknown>);
      status = `Preset ${presetName} saved.`;
      await load();
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function apply(name: string, kind: "brand" | "project") {
    try {
      const options = kind === "brand" ? await applyBrandTemplate(name) : await applyProjectTemplate(name);
      status = `${kind} ${name} applied to the next job options.`;
      presetJson = JSON.stringify(options, null, 2);
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function remove(name: string, kind: "brand" | "project") {
    if (!confirm(`Delete ${kind} template ${name}?`)) return;
    try {
      if (kind === "brand") await deleteBrandTemplate(name);
      else await deleteProjectTemplate(name);
      await load();
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function removeMedia(name: string, kind: "music" | "sfx" | "image" | "font") {
    if (!confirm(`Delete ${name}?`)) return;
    try {
      if (kind === "music") await deleteMusicAsset(name);
      else if (kind === "sfx") await deleteSfxAsset(name);
      else if (kind === "image") await deleteImageAsset(name);
      else await deleteFontAsset(name);
      await load();
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function upload(file: File | undefined, kind: "music" | "sfx" | "image" | "font") {
    if (!file) return;
    try {
      if (kind === "music") await uploadMusic(file);
      else if (kind === "sfx") await uploadSfx(file);
      else if (kind === "image") await uploadImage(file);
      else await uploadFont(file);
      status = `${file.name} uploaded.`;
      await load();
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  onMount(() => {
    void load();
  });
</script>

<div class="space-y-4" data-testid="library-panel">
  <ErrorBanner message={error} onDismiss={() => (error = "")} testId="library-error" />
  <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <div>
        <div class="flex items-center gap-1.5"><h2 class="text-sm font-semibold text-white">Brand library</h2> <HelpTip label="Brand library" body="Reusable templates, presets, fonts, images, music, and SFX. Separate from source media." doc="docs/api.md" /></div>
        <p class="mt-1 text-xs text-neutral-500">Brand templates, project templates, presets, fonts, images, and music.</p>
      </div>
      <button type="button" onclick={() => void load()} class="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300">Refresh</button>
    </div>
    {#if status}<p class="mt-2 text-[11px] text-emerald-300" role="status">{status}</p>{/if}
  </section>

  <div class="grid gap-4 lg:grid-cols-2">
    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4">
      <h3 class="text-xs font-semibold text-neutral-100">Brand templates</h3>
      <div class="mt-3 grid gap-2">
        <input bind:value={brandName} placeholder="name" class="rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" />
        <input bind:value={brandDescription} placeholder="description" class="rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" />
        <textarea rows="4" bind:value={brandJson} class="rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100"></textarea>
        <button type="button" onclick={() => void saveBrand()} disabled={!brandName.trim()} class="rounded border border-sky-500/40 px-3 py-1.5 text-[10px] text-sky-200 disabled:opacity-40">Save brand template</button>
      </div>
      <div class="mt-3 space-y-1">
        {#each brands as brand}
          <div class="flex items-center gap-2 rounded bg-neutral-950/60 px-2 py-1 text-[10px]">
            <span class="min-w-0 flex-1 truncate text-neutral-300">{brand.name}</span>
            <button type="button" onclick={() => void apply(brand.name, "brand")} class="rounded border border-neutral-700 px-1.5 py-0.5 text-sky-300">apply</button>
            <button type="button" onclick={() => void remove(brand.name, "brand")} class="rounded border border-rose-500/30 px-1.5 py-0.5 text-rose-300">delete</button>
          </div>
        {/each}
      </div>
    </section>

    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4">
      <h3 class="text-xs font-semibold text-neutral-100">Project templates</h3>
      <div class="mt-3 grid gap-2">
        <input bind:value={projectName} placeholder="name" class="rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" />
        <input bind:value={projectDescription} placeholder="description" class="rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" />
        <textarea rows="4" bind:value={projectJson} class="rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100"></textarea>
        <button type="button" onclick={() => void saveProject()} disabled={!projectName.trim()} class="rounded border border-sky-500/40 px-3 py-1.5 text-[10px] text-sky-200 disabled:opacity-40">Save project template</button>
      </div>
      <div class="mt-3 space-y-1">
        {#each projects as project}
          <div class="flex items-center gap-2 rounded bg-neutral-950/60 px-2 py-1 text-[10px]">
            <span class="min-w-0 flex-1 truncate text-neutral-300">{project.name}</span>
            <button type="button" onclick={() => void apply(project.name, "project")} class="rounded border border-neutral-700 px-1.5 py-0.5 text-sky-300">apply</button>
            <button type="button" onclick={() => void remove(project.name, "project")} class="rounded border border-rose-500/30 px-1.5 py-0.5 text-rose-300">delete</button>
          </div>
        {/each}
      </div>
    </section>

    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4">
      <h3 class="text-xs font-semibold text-neutral-100">Presets</h3>
      <div class="mt-3 grid gap-2">
        <input bind:value={presetName} placeholder="name" class="rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100" />
        <textarea rows="4" bind:value={presetJson} class="rounded border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[10px] text-neutral-100"></textarea>
        <button type="button" onclick={() => void savePresetDraft()} disabled={!presetName.trim()} class="rounded border border-sky-500/40 px-3 py-1.5 text-[10px] text-sky-200 disabled:opacity-40">Save preset</button>
      </div>
      <div class="mt-3 space-y-1">
        {#each presets as preset}
          <div class="flex items-center gap-2 rounded bg-neutral-950/60 px-2 py-1 text-[10px]">
            <span class="min-w-0 flex-1 truncate text-neutral-300">{preset.name}</span>
            <button type="button" onclick={() => (presetJson = JSON.stringify(preset.preset, null, 2))} class="rounded border border-neutral-700 px-1.5 py-0.5 text-sky-300">load</button>
          </div>
        {/each}
      </div>
    </section>

    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4">
      <h3 class="text-xs font-semibold text-neutral-100">Local media</h3>
      <div class="mt-3 grid gap-3">
        <div>
          <p class="text-[10px] uppercase tracking-wide text-neutral-500">Music ({music.length})</p>
          <input type="file" accept="audio/*" onchange={(event) => void upload(event.currentTarget.files?.[0], "music")} class="mt-1 block text-[10px] text-neutral-400" />
          <div class="mt-1 space-y-0.5">{#each music as item}<div class="flex items-center gap-1"><p class="min-w-0 flex-1 truncate font-mono text-[9px] text-neutral-500">{item.name}</p><button type="button" onclick={() => void removeMedia(item.name, "music")} class="text-[9px] text-rose-300"><Icon name="close" size={10} /></button></div>{/each}</div>
        </div>
        <div>
          <p class="text-[10px] uppercase tracking-wide text-neutral-500">SFX ({sfx.length})</p>
          <input type="file" accept="audio/*" onchange={(event) => void upload(event.currentTarget.files?.[0], "sfx")} class="mt-1 block text-[10px] text-neutral-400" />
          <div class="mt-1 space-y-0.5">{#each sfx as item}<div class="flex items-center gap-1"><p class="min-w-0 flex-1 truncate font-mono text-[9px] text-neutral-500">{item.name}</p><button type="button" onclick={() => void removeMedia(item.name, "sfx")} class="text-[9px] text-rose-300"><Icon name="close" size={10} /></button></div>{/each}</div>
        </div>
        <div>
          <p class="text-[10px] uppercase tracking-wide text-neutral-500">Images ({images.length})</p>
          <input type="file" accept="image/*" onchange={(event) => void upload(event.currentTarget.files?.[0], "image")} class="mt-1 block text-[10px] text-neutral-400" />
          <div class="mt-1 space-y-0.5">{#each images as item}<div class="flex items-center gap-1"><p class="min-w-0 flex-1 truncate font-mono text-[9px] text-neutral-500">{item.name}</p><button type="button" onclick={() => void removeMedia(item.name, "image")} class="text-[9px] text-rose-300"><Icon name="close" size={10} /></button></div>{/each}</div>
        </div>
        <div>
          <p class="text-[10px] uppercase tracking-wide text-neutral-500">Fonts ({fonts.length})</p>
          <input type="file" accept=".ttf,.otf" onchange={(event) => void upload(event.currentTarget.files?.[0], "font")} class="mt-1 block text-[10px] text-neutral-400" />
          <div class="mt-1 space-y-0.5">{#each fonts as item}<div class="flex items-center gap-1"><p class="min-w-0 flex-1 truncate font-mono text-[9px] text-neutral-500">{item.family} · {item.file}</p><button type="button" onclick={() => void removeMedia(item.name, "font")} class="text-[9px] text-rose-300"><Icon name="close" size={10} /></button></div>{/each}</div>
        </div>
      </div>
    </section>
  </div>
</div>
