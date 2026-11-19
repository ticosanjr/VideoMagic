<section class="space-y-4" data-testid="help-panel">
  <div class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4">
    <p class="vf-label text-sky-300/80">Setup · Help</p>
    <h2 class="mt-1 text-[length:var(--vf-text-xl)] font-semibold text-white">How to use the MCP</h2>
    <p class="mt-1 max-w-3xl text-[length:var(--vf-text-xs)] text-neutral-400">The panel configures and observes. Editing happens through an MCP client such as OpenCode or Paperclip.</p>
  </div>
  <div class="grid gap-4 xl:grid-cols-2">
    <article class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4">
      <h3 class="text-[length:var(--vf-text-sm)] font-semibold text-neutral-100">Recommended flow</h3>
      <ol class="mt-3 list-decimal space-y-1 pl-5 text-[length:var(--vf-text-xs)] text-neutral-300">
        <li><code>vf_project(action="init")</code> with the workspace folder.</li>
        <li><code>vf_ingest</code> then transcript, VAD, retakes, and decupage.</li>
        <li><code>vf_exec(step_id="scene.analyze")</code> and <code>vf_scenes(action="manifest")</code>.</li>
        <li><code>short.plan</code>, <code>short.captions</code>, <code>short.validate</code>, <code>short.render</code>, <code>short.export</code>, <code>short.qa</code>.</li>
        <li><code>vf_export</code> and optionally <code>delivery.collect</code>.</li>
      </ol>
    </article>
    <article class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4">
      <h3 class="text-[length:var(--vf-text-sm)] font-semibold text-neutral-100">Example prompt</h3>
      <pre class="mt-3 overflow-x-auto rounded-xl bg-black/40 p-3 font-mono text-[length:var(--vf-text-xs)] leading-5 text-neutral-300">Use o MCP VideoFlow no projeto &lt;project_id&gt;.
1. Analise as cenas e me mostre o manifesto resumido.
2. Planeje um Short de 45s com FULL_FACE, SPLIT_SCREEN_SAFE e SPLIT_BROLL.
3. Gere legendas, valide, renderize e exporte FCPXML.
4. Rode a QA final e me diga o status e os warnings.</pre>
    </article>
    <article class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4">
      <h3 class="text-[length:var(--vf-text-sm)] font-semibold text-neutral-100">Worker troubleshooting</h3>
      <ul class="mt-3 list-disc space-y-1 pl-5 text-[length:var(--vf-text-xs)] text-neutral-300">
        <li>Open Setup → GPU: LAN auto-discovery should find the Windows worker.</li>
        <li>If the worker is on a Public network, reinstall the kit so the firewall rule covers all profiles.</li>
        <li>If NVENC is unavailable, the worker reports <code>libx264</code> and remote rendering still works.</li>
        <li>Use Advanced pairing only when LAN-open mode is disabled on the worker.</li>
      </ul>
    </article>
    <article class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4">
      <h3 class="text-[length:var(--vf-text-sm)] font-semibold text-neutral-100">Resources</h3>
      <ul class="mt-3 space-y-1 text-[length:var(--vf-text-xs)] text-neutral-300">
        <li><code>vf://docs/steps</code> — node catalog</li>
        <li><code>vf://docs/contracts/scenes-manifest</code> — scene contract</li>
        <li><code>vf://docs/contracts/short-composition-plan</code> — Short contract</li>
        <li><code>vf://projects/&lt;id&gt;/scenes</code> — cached scenes</li>
        <li><code>vf://projects/&lt;id&gt;/scenes/&lt;scene&gt;/keyframe</code> — keyframe metadata</li>
      </ul>
    </article>
  </div>
</section>
