import type { components } from "./schema";
import { apiRequest } from "./accounts";

export type Availability = components["schemas"]["AvailabilityView"];
export type WorkspaceAction = components["schemas"]["WorkspaceActionView"];
export type Slots = components["schemas"]["SlotList"];
type Window = components["schemas"]["TimeWindow"];
type SlotQuery = components["schemas"]["SlotRequest"];

export const getAvailability = () => apiRequest<Availability[]>("/workspace/availability");
export const getWorkspaceActions = () => apiRequest<WorkspaceAction[]>("/workspace/actions");
export const addAvailability = (body: Window, csrf: string) => apiRequest<Availability>("/workspace/availability", {
  method: "POST", headers: { "X-CSRF-Token": csrf }, body: JSON.stringify(body),
});
export const removeAvailability = (id: string, csrf: string) => apiRequest<void>(`/workspace/availability/${encodeURIComponent(id)}`, {
  method: "DELETE", headers: { "X-CSRF-Token": csrf },
});
export const findSlots = (body: SlotQuery, csrf: string) => apiRequest<Slots>("/workspace/slots", {
  method: "POST", headers: { "X-CSRF-Token": csrf }, body: JSON.stringify(body),
});
