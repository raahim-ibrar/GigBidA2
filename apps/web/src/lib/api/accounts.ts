import type { components } from "./schema";

export type Account = components["schemas"]["Account"];
export type Profile = components["schemas"]["Profile"];
export type ProfileUpdate = components["schemas"]["ProfileUpdate"];
type Credentials = components["schemas"]["Credentials"];

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message); }
}

export async function apiRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
  const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  let response: Response;
  try { response = await fetch(`${base}/api${path}`, {
    ...init, credentials: "include", cache: "no-store",
    headers: { ...(typeof init.body === "string" ? { "Content-Type": "application/json" } : {}), ...init.headers },
  }); } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new ApiError(503, "Cannot reach the API. Check that the backend is running.");
  }
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    const detail = typeof body?.detail === "string" ? body.detail : Array.isArray(body?.detail)
      ? body.detail.map((item: { loc?: string[]; msg?: string }) => `${item.loc?.at(-1) ?? "Input"}: ${item.msg ?? "invalid value"}`).join("; ")
      : "Check your input and try again.";
    throw new ApiError(response.status, detail);
  }
  return response.status === 204 ? undefined as T : response.json();
}

export const getAccount = () => apiRequest<Account>("/auth/me");
export const getProfile = () => apiRequest<Profile>("/profile/me");
export const authenticate = (mode: "login" | "register", body: Credentials) =>
  apiRequest<Account>(`/auth/${mode}`, { method: "POST", body: JSON.stringify(body) });
export const saveProfile = (body: ProfileUpdate, csrf: string) => apiRequest<Profile>("/profile/me", {
  method: "PUT", headers: { "X-CSRF-Token": csrf }, body: JSON.stringify(body),
});
export const signOut = (csrf: string) => apiRequest<void>("/auth/logout", {
  method: "POST", headers: { "X-CSRF-Token": csrf },
});
