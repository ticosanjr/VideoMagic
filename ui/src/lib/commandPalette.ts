export interface Command {
  id: string;
  title: string;
  group?: string;
  hint?: string;
  keywords?: string;
  shortcut?: string;
}

export const RECENT_LIMIT = 5;

export function recordRecentCommand(
  recentIds: string[],
  id: string,
  limit = RECENT_LIMIT
): string[] {
  return [id, ...recentIds.filter((item) => item !== id)].slice(0, limit);
}

export function withRecentCommands(
  commands: Command[],
  recentIds: string[],
  limit = RECENT_LIMIT
): Command[] {
  if (!recentIds.length) return commands;
  const byId = new Map(commands.map((command) => [command.id, command]));
  const seen = new Set<string>();
  const recent: Command[] = [];
  for (const id of recentIds) {
    if (seen.has(id)) continue;
    const command = byId.get(id);
    if (!command) continue;
    seen.add(id);
    recent.push({ ...command, group: "Recent" });
    if (recent.length >= limit) break;
  }
  if (!recent.length) return commands;
  return [...recent, ...commands.filter((command) => !seen.has(command.id))];
}

function score(command: Command, needle: string): number {
  const title = command.title.toLowerCase();
  if (title.startsWith(needle)) return 0;
  if (title.includes(needle)) return 1;
  const keywords = (command.keywords ?? "").toLowerCase();
  if (keywords.includes(needle)) return 2;
  const hint = (command.hint ?? "").toLowerCase();
  if (hint.includes(needle)) return 3;
  return -1;
}

export function filterCommands(commands: Command[], query: string): Command[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return commands;
  return commands
    .map((command, index) => ({ command, index, rank: score(command, needle) }))
    .filter((entry) => entry.rank >= 0)
    .sort((a, b) => a.rank - b.rank || a.index - b.index)
    .map((entry) => entry.command);
}

export function moveActiveIndex(index: number, length: number, delta: number): number {
  if (length <= 0) return 0;
  const next = (index + delta) % length;
  return next < 0 ? next + length : next;
}
