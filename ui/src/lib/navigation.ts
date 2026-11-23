import type { IconName } from "$lib/ui/icons";

export type AreaId = "main";
export type TabId = "curation" | "jobs" | "setup";

export interface TabMeta {
  id: TabId;
  area: AreaId;
  legacy: string[];
}

export interface AreaMeta {
  id: AreaId;
  tabs: TabId[];
}

/** Three top-level screens. The old setup tabs are aliases for Setup. */
export const TABS: TabMeta[] = [
  {
    id: "curation",
    area: "main",
    legacy: ["overview", "home", "produce", "runs", "curation"]
  },
  { id: "jobs", area: "main", legacy: ["job"] },
  {
    id: "setup",
    area: "main",
    legacy: [
      "workspace",
      "connect",
      "integrations",
      "models",
      "providers",
      "capabilities",
      "services",
      "extensions",
      "plugins",
      "styles",
      "presets",
      "formats",
      "help",
      "gpu",
      "gpu-offload",
      "acceleration",
      "settings"
    ]
  }
];

export const AREAS: AreaMeta[] = [
  { id: "main", tabs: TABS.map((tab) => tab.id) }
];

const BY_ID = new Map<TabId, TabMeta>(TABS.map((tab) => [tab.id, tab]));
const LEGACY = new Map<string, TabId>(
  TABS.flatMap((tab) => [tab.id, ...tab.legacy].map((name) => [name, tab.id] as const))
);

export function isTabId(value: string): value is TabId {
  return BY_ID.has(value as TabId);
}

export function tabMeta(tab: TabId): TabMeta {
  return BY_ID.get(tab) ?? BY_ID.get("curation")!;
}

export function areaForTab(_tab: TabId): AreaId {
  return "main";
}

export function areaTabs(_area: AreaId): TabId[] {
  return TABS.map((tab) => tab.id);
}

export function defaultTabForArea(_area: AreaId): TabId {
  return "curation";
}

/** Resolve `#tab`, `#tab/<project_id>`, or a legacy alias. */
export function resolveRoute(hash: string): { area: AreaId; tab: TabId } {
  const raw = hash.replace(/^#/, "").trim();
  if (!raw) return { area: "main", tab: "curation" };
  const first = raw.split("/")[0];
  if (isTabId(first)) return { area: "main", tab: first };
  const legacy = LEGACY.get(first);
  if (legacy) return { area: "main", tab: legacy };
  return { area: "main", tab: "curation" };
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
  main: "activity"
};

export const TAB_ICONS: Record<TabId, IconName> = {
  curation: "sparkles",
  jobs: "activity",
  setup: "settings"
};
