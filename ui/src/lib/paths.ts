export function pathSeparator(path: string): "/" | "\\" {
  return path.includes("\\") ? "\\" : "/";
}

export function trimTrailingSeparators(path: string): string {
  const trimmed = path.trim();
  if (!trimmed) return "";
  if (/^[A-Za-z]:[\\/]$/.test(trimmed)) return trimmed;
  return trimmed.replace(/[\\/]+$/, "");
}

export function baseName(path: string): string {
  const trimmed = trimTrailingSeparators(path);
  if (!trimmed) return "";
  const index = Math.max(trimmed.lastIndexOf("/"), trimmed.lastIndexOf("\\"));
  return trimmed.slice(index + 1);
}

export function parentPath(path: string): string {
  const trimmed = trimTrailingSeparators(path);
  if (!trimmed) return "";
  const index = Math.max(trimmed.lastIndexOf("/"), trimmed.lastIndexOf("\\"));
  if (index < 0) return "";
  if (index === 0) return trimmed.slice(0, 1);
  if (index === 2 && /^[A-Za-z]:[\\/]/.test(trimmed)) return trimmed.slice(0, 3);
  return trimmed.slice(0, index);
}

export function suggestOutputPath(source: string): string {
  const trimmed = trimTrailingSeparators(source);
  if (!trimmed) return "";
  const name = baseName(trimmed).replace(/\.[^.]*$/, "");
  const parent = parentPath(trimmed);
  if (!parent) return `${name}-videoflow`;
  const separator = pathSeparator(trimmed);
  const prefix = parent.endsWith("/") || parent.endsWith("\\") ? parent : `${parent}${separator}`;
  return `${prefix}${name}-videoflow`;
}
