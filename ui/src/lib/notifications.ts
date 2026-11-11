export type NoticeKind = "info" | "success" | "warning" | "error";
export type NoticeCategory =
  | "hilt"
  | "job_finished"
  | "blocker"
  | "action"
  | "system";
export type NoticeLevel = "minimal" | "standard" | "verbose";

export interface Notice {
  id: string;
  kind: NoticeKind;
  category: NoticeCategory;
  title: string;
  message: string;
  detail: string;
  code: string;
  actionLabel: string;
  actionId: string;
  persistent: boolean;
  createdAt: string;
}

export interface NoticeInput {
  kind: NoticeKind;
  category?: NoticeCategory;
  title: string;
  message?: string;
  detail?: string;
  code?: string;
  actionLabel?: string;
  actionId?: string;
  persistent?: boolean;
}

const SEVERITY: Record<NoticeKind, number> = {
  error: 0,
  warning: 1,
  info: 2,
  success: 3
};

export function noticeAllowed(level: NoticeLevel, input: NoticeInput): boolean {
  if (input.kind === "error" || input.kind === "warning") return true;
  const category = input.category ?? "action";
  if (level === "verbose") return true;
  if (level === "standard") return category !== "system";
  return category === "hilt" || category === "job_finished" || category === "blocker";
}

let counter = 0;

export function createNotice(input: NoticeInput): Notice {
  counter += 1;
  const kind = input.kind;
  return {
    id: `notice-${Date.now().toString(36)}-${counter}`,
    kind,
    category: input.category ?? (kind === "error" || kind === "warning" ? "blocker" : "action"),
    title: input.title,
    message: input.message ?? "",
    detail: input.detail ?? "",
    code: input.code ?? "",
    actionLabel: input.actionLabel ?? "",
    actionId: input.actionId ?? "",
    persistent: input.persistent ?? (kind === "error" || kind === "warning"),
    createdAt: new Date().toISOString()
  };
}

export function sortNotices(notices: Notice[]): Notice[] {
  return [...notices].sort((a, b) => {
    const severity = SEVERITY[a.kind] - SEVERITY[b.kind];
    if (severity !== 0) return severity;
    return b.createdAt.localeCompare(a.createdAt);
  });
}

export function noticeCounts(notices: Notice[]): {
  total: number;
  errors: number;
  warnings: number;
} {
  return {
    total: notices.length,
    errors: notices.filter((notice) => notice.kind === "error").length,
    warnings: notices.filter((notice) => notice.kind === "warning").length
  };
}
