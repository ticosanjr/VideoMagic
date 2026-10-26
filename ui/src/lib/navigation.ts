import type { IconName } from "$lib/ui/icons";

export type AreaId = "produce" | "edit" | "runs" | "library" | "setup";

export type TabId =
  | "recipes"
  | "projects"
  | "assistant"
  | "timeline"
  | "jobs"
  | "schedules"
  | "media"
  | "brand"
  | "models"
  | "providers"
  | "services"
  | "extensions"
  | "connect"
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
  { id: "produce", tabs: ["recipes", "projects", "assistant"] },
  { id: "edit", tabs: ["timeline"] },
  { id: "runs", tabs: ["jobs", "schedules"] },
  { id: "library", tabs: ["media", "brand"] },
  {
    id: "setup",
    tabs: ["models", "providers", "services", "extensions", "connect", "settings"]
  }
];

export const TABS: TabMeta[] = [
  { id: "recipes", area: "produce", legacy: [] },
  { id: "projects", area: "produce", legacy: [] },
  { id: "assistant", area: "produce", legacy: ["copilot"] },
  { id: "timeline", area: "edit", legacy: [] },
  { id: "jobs", area: "runs", legacy: [] },
  { id: "schedules", area: "runs", legacy: ["automation"] },
  { id: "media", area: "library", legacy: ["assets"] },
  { id: "brand", area: "library", legacy: ["library"] },
  { id: "models", area: "setup", legacy: [] },
  { id: "providers", area: "setup", legacy: [] },
  { id: "services", area: "setup", legacy: [] },
  { id: "extensions", area: "setup", legacy: ["plugins"] },
  { id: "connect", area: "setup", legacy: ["integrations"] },
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
  return BY_ID.get(tab) ?? BY_ID.get("recipes")!;
}

export function areaForTab(tab: TabId): AreaId {
  return tabMeta(tab).area;
}

export function areaTabs(area: AreaId): TabId[] {
  return AREAS.find((item) => item.id === area)?.tabs ?? ["recipes"];
}

export function defaultTabForArea(area: AreaId): TabId {
  return areaTabs(area)[0];
}

/** Resolve `#tab`, `#area/tab`, or a legacy alias. */
export function resolveRoute(hash: string): { area: AreaId; tab: TabId } {
  const raw = hash.replace(/^#/, "").trim();
  if (!raw) return { area: "produce", tab: "recipes" };
  const [first, second] = raw.split("/");
  if (second && isTabId(second) && areaForTab(second) === first) {
    return { area: first as AreaId, tab: second };
  }
  if (isTabId(first)) return { area: areaForTab(first), tab: first };
  const legacy = LEGACY.get(first);
  if (legacy) return { area: areaForTab(legacy), tab: legacy };
  return { area: "produce", tab: "recipes" };
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
  produce: "play",
  edit: "scissors",
  runs: "activity",
  library: "library",
  setup: "settings"
};

export const TAB_ICONS: Record<TabId, IconName> = {
  recipes: "list",
  projects: "folder",
  assistant: "sparkles",
  timeline: "film",
  jobs: "activity",
  schedules: "calendar",
  media: "image",
  brand: "palette",
  models: "cpu",
  providers: "plug",
  services: "server",
  extensions: "puzzle",
  connect: "link",
  settings: "settings"
};
