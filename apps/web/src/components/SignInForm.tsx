"use client";

import { useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { authenticate, getProfile } from "@/lib/api/accounts";

export function SignInForm() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setBusy(true); setError("");
    const form = new FormData(event.currentTarget);
    try {
      await authenticate(mode, { email: String(form.get("email")), password: String(form.get("password")) });
      window.dispatchEvent(new Event("gigbid-account-changed"));
      const profile = await getProfile();
      router.push(profile.onboarding_complete ? "/inbox" : "/onboarding");
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to sign in."); }
    finally { setBusy(false); }
  }

  return <section className="card form-card"><h2>{mode === "login" ? "Welcome back" : "Create your account"}</h2>
    <form onSubmit={submit}>
      <label htmlFor="email">Email</label><input id="email" name="email" type="email" autoComplete="email" required maxLength={254} />
      <label htmlFor="password">Password</label><input id="password" name="password" type="password" minLength={12} maxLength={128}
        autoComplete={mode === "register" ? "new-password" : "current-password"} required aria-describedby="password-help" />
      <p id="password-help" className="muted">Use at least 12 characters.</p>
      {error && <p role="alert" className="error">{error}</p>}
      <button type="submit" disabled={busy}>{busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}</button>
    </form>
    <button className="text-button" disabled={busy} onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>
      {mode === "login" ? "Create a new account" : "Already have an account? Sign in"}
    </button>
  </section>;
}
