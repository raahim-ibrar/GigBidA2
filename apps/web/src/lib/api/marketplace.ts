import { apiRequest } from "./accounts";
import type { components } from "./schema";
export type Connection = components["schemas"]["ConnectionStatus"];
export const getMarketplace = () => apiRequest<Connection>("/marketplace");
export const setMarketplace = (mode: "manual" | "student_sim", csrf: string) => apiRequest<Connection>("/marketplace", {
  method: "PUT", headers: { "X-CSRF-Token": csrf }, body: JSON.stringify({ mode }),
});
export const searchMarketplace = (query: string, csrf: string) => apiRequest<components["schemas"]["ImportedJobs"]>("/marketplace/search", {
  method: "POST", headers: { "X-CSRF-Token": csrf }, body: JSON.stringify({ query, limit: 10 }),
});
export const syncMarketplace = (csrf: string) => apiRequest<components["schemas"]["SyncResult"]>("/marketplace/sync", {
  method: "POST", headers: { "X-CSRF-Token": csrf }, body: "{}",
});
