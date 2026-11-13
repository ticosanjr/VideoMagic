import type { Job, Recipe } from "$lib/api";

export type RetakeGroupView = {
  keep: number[];
  discard: number[];
  reason: string;
  keep_text: string[];
  discard_text: string[];
  start_sec: number;
  end_sec: number;
};

export function outputValueText(value: unknown): string {
  if (value === undefined) return "";
  return typeof value === "string" ? value : JSON.stringify(value, null, 2);
}

export function retakeGroups(value: unknown): RetakeGroupView[] {
  if (!value || typeof value !== "object" || !("groups" in value)) return [];
  const groups = (value as { groups?: unknown }).groups;
  if (!Array.isArray(groups)) return [];
  return groups.filter(
    (group): group is RetakeGroupView =>
      Boolean(group) &&
      typeof group === "object" &&
      Array.isArray((group as RetakeGroupView).keep) &&
      Array.isArray((group as RetakeGroupView).discard)
  );
}

export function describeRecipeDiff(current: Recipe, older: Recipe): string[] {
  const lines: string[] = [];
  if (current.name !== older.name) {
    lines.push(`Name: "${older.name}" → "${current.name}"`);
  }
  const currentSteps = new Map(current.steps.map((step) => [step.id, step]));
  const olderSteps = new Map(older.steps.map((step) => [step.id, step]));
  for (const id of olderSteps.keys()) {
    if (!currentSteps.has(id)) lines.push(`Removed step: ${id}`);
  }
  for (const id of currentSteps.keys()) {
    if (!olderSteps.has(id)) lines.push(`Added step: ${id}`);
  }
  for (const [id, currentStep] of currentSteps) {
    const olderStep = olderSteps.get(id);
    if (!olderStep) continue;
    if (currentStep.type !== olderStep.type) {
      lines.push(`${id}: type ${olderStep.type} → ${currentStep.type}`);
    }
    if (JSON.stringify(currentStep.needs) !== JSON.stringify(olderStep.needs)) {
      lines.push(`${id}: needs [${olderStep.needs.join(", ")}] → [${currentStep.needs.join(", ")}]`);
    }
    if (JSON.stringify(currentStep.inputs) !== JSON.stringify(olderStep.inputs)) {
      lines.push(`${id}: wiring changed`);
    }
    const keys = new Set([
      ...Object.keys(olderStep.params),
      ...Object.keys(currentStep.params)
    ]);
    for (const key of keys) {
      if (
        JSON.stringify(currentStep.params[key]) !==
        JSON.stringify(olderStep.params[key])
      ) {
        lines.push(`${id}.${key}: ${JSON.stringify(olderStep.params[key])} → ${JSON.stringify(currentStep.params[key])}`);
      }
    }
  }
  if (current.steps.length !== older.steps.length) {
    lines.unshift(`Steps: ${older.steps.length} → ${current.steps.length}`);
  }
  return lines.length ? lines : ["No recipe changes."];
}

export function runDuration(run: Job): string {
  if (run.duration_ms !== null && run.duration_ms !== undefined) {
    return `${(run.duration_ms / 1000).toFixed(1)}s`;
  }
  return run.result?.elapsed_seconds !== undefined
    ? `${run.result.elapsed_seconds.toFixed(1)}s`
    : "—";
}

export function cachedCount(run: Job): number {
  return (run.result?.step_runs ?? []).filter((step) => step.status === "cached").length;
}

export function executedCount(run: Job): number {
  return (run.result?.step_runs ?? []).filter((step) => step.status === "executed").length;
}
