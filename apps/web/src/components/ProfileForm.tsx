"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ApiError, getAccount, getProfile, saveProfile, type Account, type Profile, type ProfileUpdate } from "@/lib/api/accounts";

export function ProfileForm({ onboarding = false }: { onboarding?: boolean }) {
  const router = useRouter();
  const [account, setAccount] = useState<Account | null>(null);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [unauthorized, setUnauthorized] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([getAccount(), getProfile()]).then(([user, value]) => {
      if (active) { setAccount(user); setProfile(value); }
    }).catch(err => {
      if (active) {
        setUnauthorized(err instanceof ApiError && err.status === 401);
        setError(err instanceof Error ? err.message : "Unable to load profile.");
      }
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!account) return;
    setBusy(true); setError(""); setSaved(false);
    const data = new FormData(event.currentTarget);
    const body: ProfileUpdate = {
      display_name: String(data.get("display_name")),
      persona: String(data.get("persona")) as ProfileUpdate["persona"],
      hourly_floor: String(data.get("hourly_floor")),
      weekly_connects_budget: Number(data.get("weekly_connects_budget")),
      saved_searches: String(data.get("saved_searches")).split("\n").map(s => s.trim()).filter(Boolean),
    };
    try {
      const result = await saveProfile(body, account.csrf_token);
      setProfile(result); setSaved(true);
      if (onboarding) router.push("/inbox");
    } catch (err) { setError(err instanceof Error ? err.message : "Unable to save profile."); }
    finally { setBusy(false); }
  }

  if (loading) return <p role="status">Loading your profile…</p>;
  if (unauthorized) return <p className="notice">Sign in to configure your profile. <Link href="/sign-in">Sign in</Link></p>;
  if (!profile) return <p role="alert" className="error">{error || "Profile unavailable."}</p>;

  return <section className="card form-card"><h2>Your freelancer profile</h2><p className="muted">Signed in as {account?.email}</p>
    <form onSubmit={submit}>
      <label htmlFor="display_name">Display name</label><input id="display_name" name="display_name" required maxLength={100} defaultValue={profile.display_name} />
      <label htmlFor="persona">Profile type</label><select id="persona" name="persona" defaultValue={profile.persona}>
        <option value="own">My own profile</option><option value="ai_ml">AI / ML engineer</option>
        <option value="full_stack">Full-stack developer</option><option value="data_analyst">Data analyst</option>
      </select>
      <label htmlFor="hourly_floor">Minimum hourly rate (USD)</label><input id="hourly_floor" name="hourly_floor" type="number" min="0.01" max="100000" step="0.01" required defaultValue={profile.hourly_floor} />
      <label htmlFor="weekly_connects_budget">Weekly Connects budget</label><input id="weekly_connects_budget" name="weekly_connects_budget" type="number" min="0" max="100000" step="1" required defaultValue={profile.weekly_connects_budget} />
      <label htmlFor="saved_searches">Saved searches (one per line)</label><textarea id="saved_searches" name="saved_searches" rows={4} defaultValue={profile.saved_searches.join("\n")} />
      {error && <p role="alert" className="error">{error}</p>}
      {saved && <p role="status">Profile saved.</p>}
      <button type="submit" disabled={busy}>{busy ? "Saving…" : onboarding ? "Save and continue" : "Save profile"}</button>
    </form>
    <p className="muted">Persona selection saves your preference. Portfolio import and marketplace connection are the next implementation steps.</p>
  </section>;
}
