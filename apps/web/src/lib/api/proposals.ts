import type { components } from "./schema";
import { apiRequest } from "./accounts";

export type Job = components["schemas"]["JobView"];
export type Run = components["schemas"]["RunView"];
export type Evidence = components["schemas"]["EvidenceItem"];
export type Draft = components["schemas"]["ProposalDraft"];
export type ManualJob = components["schemas"]["ManualJob"];
export type Review = components["schemas"]["ReviewRun"];
export const listJobs = () => apiRequest<Job[]>("/jobs");
export const getJob = (id: string) => apiRequest<Job>(`/jobs/${encodeURIComponent(id)}`);
export const listRuns = (job?: string) => apiRequest<Run[]>(`/runs${job ? `?job_id=${encodeURIComponent(job)}` : ""}`);
export const getRun = (id: string) => apiRequest<Run>(`/runs/${encodeURIComponent(id)}`);
export const createJob = (body: ManualJob, csrf: string) => apiRequest<Job>("/jobs", {
  method: "POST", headers: { "X-CSRF-Token": csrf }, body: JSON.stringify(body),
});
export const startRun = (job: string, key: string, csrf: string) => apiRequest<Run>("/runs", {
  method: "POST", headers: { "X-CSRF-Token": csrf }, body: JSON.stringify({ job_id: job, idempotency_key: key }),
});
export const reviewRun = (body: Review, csrf: string) => apiRequest<Run>("/approvals", {
  method: "POST", headers: { "X-CSRF-Token": csrf }, body: JSON.stringify(body),
});
