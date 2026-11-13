<script lang="ts">
  import Button from "$lib/ui/Button.svelte";
  import Icon from "$lib/ui/Icon.svelte";
  type MaybeAsync = void | Promise<void>;

  let {
    open = $bindable(false),
    nleBusy = false,
    onSave,
    onValidate,
    onInspector,
    onRuns,
    onOutputs,
    onJson,
    onDryRun,
    onNleValidate,
    onBatches,
    onConfig,
    onResetLayout,
    onSaveAs,
    onDownload,
    onHistory,
    onTour
  }: {
    open?: boolean;
    nleBusy?: boolean;
    onSave: () => MaybeAsync;
    onValidate: () => MaybeAsync;
    onInspector: () => void;
    onRuns: () => MaybeAsync;
    onOutputs: () => void;
    onJson: () => void;
    onDryRun: () => MaybeAsync;
    onNleValidate: () => MaybeAsync;
    onBatches: () => MaybeAsync;
    onConfig: () => void;
    onResetLayout: () => void;
    onSaveAs: () => MaybeAsync;
    onDownload: () => void;
    onHistory: () => MaybeAsync;
    onTour: () => void;
  } = $props();

  function close(action: () => MaybeAsync) {
    open = false;
    void action();
  }
</script>

<div class="relative">
  <Button icon="more" variant="secondary" size="md" testid="recipe-more" onclick={() => (open = !open)}>More</Button>
  {#if open}
    <button type="button" class="fixed inset-0 z-40 cursor-default" aria-label="Close menu" onclick={() => (open = false)}></button>
    <div class="absolute right-0 z-50 mt-1 w-56 overflow-hidden rounded-xl border border-neutral-700 bg-neutral-950 p-1 shadow-2xl" role="menu" data-testid="recipe-more-menu">
      <div class="sm:hidden">
        <button type="button" role="menuitem" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-white/5" onclick={() => close(onSave)}><Icon name="save" size={13} />Save recipe</button>
        <button type="button" role="menuitem" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-white/5" onclick={() => close(onValidate)}><Icon name="check" size={13} />Validate</button>
        <button type="button" role="menuitem" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-white/5" onclick={() => close(onInspector)}><Icon name="panel" size={13} />Inspector</button>
        <button type="button" role="menuitem" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-white/5" onclick={() => close(onRuns)}><Icon name="activity" size={13} />Runs</button>
        <button type="button" role="menuitem" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-white/5" onclick={() => close(onOutputs)}><Icon name="file" size={13} />Outputs</button>
        <button type="button" role="menuitem" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-white/5" onclick={() => close(onJson)}><Icon name="code" size={13} />Recipe JSON</button>
        <div class="my-1 border-t border-neutral-800"></div>
      </div>
      <button type="button" role="menuitem" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-white/5" onclick={() => close(onDryRun)}><Icon name="flask" size={13} />Dry run</button>
      <button type="button" role="menuitem" data-testid="nle-validate" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-white/5" disabled={nleBusy} onclick={() => close(onNleValidate)}><Icon name="check" size={13} />{nleBusy ? "Validating…" : "Validate NLE exports"}</button>
      <button type="button" role="menuitem" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-white/5" onclick={() => close(onBatches)}><Icon name="layers" size={13} />Batch history</button>
      <button type="button" role="menuitem" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-white/5" onclick={() => close(onConfig)}><Icon name="settings" size={13} />Recipe config</button>
      <div class="my-1 border-t border-neutral-800"></div>
      <button type="button" role="menuitem" data-testid="recipe-reset-layout" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-white/5" onclick={() => close(onResetLayout)}><Icon name="layout" size={13} />Auto layout</button>
      <button type="button" role="menuitem" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-white/5" onclick={() => close(onSaveAs)}><Icon name="duplicate" size={13} />Save as</button>
      <button type="button" role="menuitem" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-white/5" onclick={() => close(onDownload)}><Icon name="file" size={13} />Download</button>
      <button type="button" role="menuitem" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-white/5" onclick={() => close(onHistory)}><Icon name="clock" size={13} />Version history</button>
      <button type="button" role="menuitem" class="flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-left text-[11px] text-neutral-300 hover:bg-white/5" onclick={() => close(onTour)}><Icon name="bulb" size={13} />Quick tour</button>
    </div>
  {/if}
</div>
