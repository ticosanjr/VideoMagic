import type { IconName } from "$lib/ui/icons";

export type AreaId = "runs" | "setup";

export type TabId =
  | "overview"
  | "jobs"
  | "models"
  | "providers"
  | "services"
  | "extensions"
  | "connect"
  | "gpu"
  | "settings";

export interface TabMeta {
  id: TabId;
  area: AreaId;
  legacy: string[];
}

export interface AreaMeta {
  id: AreaId;
  tabs: TabId[];
}

export const AREAS: AreaMeta[] = [
  { id: "runs", tabs: ["overview", "jobs"] },
  {
    id: "setup",
    tabs: ["models", "providers", "services", "extensions", "connect", "gpu", "settings"]
  }
];

export const TABS: TabMeta[] = [
  { id: "overview", area: "runs", legacy: ["home", "produce"] },
  { id: "jobs", area: "runs", legacy: ["runs"] },
  { id: "models", area: "setup", legacy: [] },
  { id: "providers", area: "setup", legacy: ["capabilities"] },
  { id: "services", area: "setup", legacy: [] },
  { id: "extensions", area: "setup", legacy: ["plugins"] },
  { id: "connect", area: "setup", legacy: ["integrations"] },
  { id: "gpu", area: "setup", legacy: ["gpu-offload", "acceleration"] },
  { id: "settings", area: "setup", legacy: [] }
];

const BY_ID = new Map<TabId, TabMeta>(TABS.map((tab) => [tab.id, tab]));
const LEGACY = new Map<string, TabId>(
  TABS.flatMap((tab) => [tab.id, ...tab.legacy].map((name) => [name, tab.id] as const))
);

export function isTabId(value: string): value is TabId {
  return BY_ID.has(value as TabId);
}

export function tabMeta(tab: TabId): TabMeta {
  return BY_ID.get(tab) ?? BY_ID.get("overview")!;
}

export function areaForTab(tab: TabId): AreaId {
  return tabMeta(tab).area;
}

export function areaTabs(area: AreaId): TabId[] {
  return AREAS.find((item) => item.id === area)?.tabs ?? ["overview"];
}

export function defaultTabForArea(area: AreaId): TabId {
  return areaTabs(area)[0];
}

/** Resolve `#tab`, `#area/tab`, or a legacy alias. */
export function resolveRoute(hash: string): { area: AreaId; tab: TabId } {
  const raw = hash.replace(/^#/, "").trim();
  if (!raw) return { area: "runs", tab: "overview" };
  const [first, second] = raw.split("/");
  if (second && isTabId(second) && areaForTab(second) === first) {
    return { area: first as AreaId, tab: second };
  }
  if (isTabId(first)) return { area: areaForTab(first), tab: first };
  const legacy = LEGACY.get(first);
  if (legacy) return { area: areaForTab(legacy), tab: legacy };
  return { area: "runs", tab: "overview" };
}

export function hashFor(tab: TabId): string {
  return `#${tab}`;
}

export function tabLabelKey(tab: TabId): string {
  return tab;
}

export function areaLabelKey(area: AreaId): string {
  return area;
}

export function tabHintKey(tab: TabId): string {
  return `${tab}_hint`;
}

export function areaHintKey(area: AreaId): string {
  return `${area}_hint`;
}

export const AREA_ICONS: Record<AreaId, IconName> = {
  runs: "activity",
  setup: "settings"
};

export const TAB_ICONS: Record<TabId, IconName> = {
  overview: "sparkles",
  jobs: "activity",
  models: "cpu",
  providers: "plug",
  services: "server",
  extensions: "puzzle",
  connect: "link",
  gpu: "gpu",
  settings: "settings"
};
