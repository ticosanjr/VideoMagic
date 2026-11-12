export function artifactUrl(jobId: string, name: string): string {
  return `/api/v1/jobs/${encodeURIComponent(jobId)}/artifacts/${encodeURIComponent(name)}`;
}

export async function loadArtifactJson<T = Record<string, unknown>>(
  jobId: string,
  name: string
): Promise<T | null> {
  try {
    const response = await fetch(artifactUrl(jobId, name), {
      headers: { accept: "application/json" }
    });
    if (!response.ok) return null;
    return (await response.json()) as T;
  } catch {
    return null;
  }
}

export function isVideo(path: string): boolean {
  return /\.(mp4|webm|mov|m4v)$/i.test(path);
}

export function isImage(path: string): boolean {
  return /\.(png|jpe?g|webp|gif)$/i.test(path);
}
