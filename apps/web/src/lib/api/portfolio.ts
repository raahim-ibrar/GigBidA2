import type { components } from "./schema";
import { apiRequest } from "./accounts";

export type DocumentMetadata = components["schemas"]["DocumentMetadata"];
export type DocumentView = components["schemas"]["DocumentView"];
export type PortfolioSearch = components["schemas"]["PortfolioSearch"];
export type SearchResult = components["schemas"]["SearchResult"];

export const listDocuments = () => apiRequest<DocumentView[]>("/portfolio/documents");
export const importGitHub = (body: { repository_url: string; ref: string; project: string; skills: string[]; path: string }, csrf: string) => apiRequest<DocumentView>("/portfolio/import/github", {
  method: "POST", headers: { "X-CSRF-Token": csrf }, body: JSON.stringify(body),
});
export const uploadDocument = (file: File, metadata: DocumentMetadata, csrf: string) => {
  const data = new FormData(); data.append("file", file); data.append("metadata", JSON.stringify(metadata));
  return apiRequest<DocumentView>("/portfolio/documents", { method: "POST", body: data, headers: { "X-CSRF-Token": csrf } });
};
export const deleteDocument = (id: string, csrf: string) => apiRequest<void>(`/portfolio/documents/${encodeURIComponent(id)}`, {
  method: "DELETE", headers: { "X-CSRF-Token": csrf },
});
export const retryDocument = (id: string, csrf: string) => apiRequest<DocumentView>(`/portfolio/documents/${encodeURIComponent(id)}/retry`, {
  method: "POST", headers: { "X-CSRF-Token": csrf },
});
export const searchPortfolio = (body: PortfolioSearch, csrf: string) => apiRequest<SearchResult>("/portfolio/search", {
  method: "POST", headers: { "X-CSRF-Token": csrf }, body: JSON.stringify(body),
});
