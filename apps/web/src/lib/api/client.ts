import type { components } from "./schema";
export type SkeletonStatus = components["schemas"]["SkeletonStatus"];

export async function getSkeletonStatus(): Promise<SkeletonStatus> {
  const base = process.env.API_INTERNAL_URL ?? process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const response = await fetch(`${base}/api/status`, { cache: "no-store", signal: AbortSignal.timeout(2500) });
  if (!response.ok) throw new Error(`API returned ${response.status}`);
  return response.json();
}
