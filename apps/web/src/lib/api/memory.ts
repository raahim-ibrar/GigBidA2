import type { components } from "./schema";
import { apiRequest } from "./accounts";

export type MemoryList = components["schemas"]["MemoryList"];
export type MemoryView = components["schemas"]["MemoryView"];
export type Candidate = components["schemas"]["StyleCandidate"];
export type Edit = components["schemas"]["EditView"];
type Confirm = components["schemas"]["ConfirmStyle"];
export const getMemory = () => apiRequest<MemoryList>("/memory");
export const getCandidates = () => apiRequest<Candidate[]>("/memory/style-candidates");
export const getEdits = () => apiRequest<Edit[]>("/memory/edits");
export const confirmStyle = (key: Confirm["key"], csrf: string) => apiRequest<MemoryList>("/memory/style", {
  method: "POST", headers: { "X-CSRF-Token": csrf }, body: JSON.stringify({ key, confirmed: true }),
});
export const removeMemory = (item: MemoryView, csrf: string) => apiRequest<void>(`/memory/${item.kind}/${encodeURIComponent(item.key)}`, {
  method: "DELETE", headers: { "X-CSRF-Token": csrf }, body: JSON.stringify({ version: item.version }),
});
