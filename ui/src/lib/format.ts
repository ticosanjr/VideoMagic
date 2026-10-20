const DATE_FORMAT = new Intl.DateTimeFormat(undefined, {
  year: "numeric",
  month: "short",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit"
});

export function parseDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function formatDateTime(value: string | null | undefined): string {
  const parsed = parseDate(value);
  return parsed ? DATE_FORMAT.format(parsed) : "—";
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms === null || ms === undefined || !Number.isFinite(ms)) return "—";
  const value = Math.max(0, Math.round(ms));
  if (value < 1000) return `${value} ms`;
  const total = Math.round(value / 1000);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = total % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
  }
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function formatSeconds(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || !Number.isFinite(seconds)) {
    return "—";
  }
  return formatDuration(seconds * 1000);
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || !Number.isFinite(bytes)) return "—";
  const value = Math.max(0, bytes);
  if (value < 1024) return `${Math.round(value)} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let scaled = value / 1024;
  let unit = units[0];
  for (const candidate of units) {
    unit = candidate;
    if (scaled < 1024 || candidate === units.at(-1)) break;
    scaled /= 1024;
  }
  return `${scaled.toFixed(scaled >= 10 ? 0 : 1)} ${unit}`;
}

export function elapsedMs(
  startedAt: string | null | undefined,
  finishedAt: string | null | undefined,
  now = Date.now()
): number | null {
  const start = parseDate(startedAt);
  if (!start) return null;
  const end = parseDate(finishedAt)?.getTime() ?? now;
  return Math.max(0, end - start.getTime());
}

export function statusText(status: string): string {
  return status.replaceAll("_", " ");
}
