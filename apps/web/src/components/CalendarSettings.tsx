"use client";

import Link from "next/link";
import { useEffect, useState, type FormEvent } from "react";
import { ApiError, getAccount, type Account } from "@/lib/api/accounts";
import { addAvailability, findSlots, getAvailability, getWorkspaceActions, removeAvailability,
  type Availability, type Slots, type WorkspaceAction } from "@/lib/api/workspace";

export function CalendarSettings() {
  const [account, setAccount] = useState<Account | null>(null);
  const [windows, setWindows] = useState<Availability[]>([]);
  const [actions, setActions] = useState<WorkspaceAction[]>([]);
  const [slots, setSlots] = useState<Slots | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [signIn, setSignIn] = useState(false);

  useEffect(() => {
    let active = true;
    Promise.all([getAccount(), getAvailability(), getWorkspaceActions()]).then(([user, saved, history]) => {
      if (active) {
        setAccount(user);
        setWindows(saved);
        setActions(history);
      }
    }).catch(err => {
      if (active) {
        setError(err.message);
        setSignIn(err instanceof ApiError && err.status === 401);
      }
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);

  async function saveWindow(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!account) return;
    const form = event.currentTarget;
    const data = new FormData(form);
    setBusy(true); setError(""); setMessage("");
    try {
      await addAvailability({ start: new Date(String(data.get("start"))).toISOString(),
        end: new Date(String(data.get("end"))).toISOString() }, account.csrf_token);
      setWindows(await getAvailability());
      setSlots(null); form.reset(); setMessage("Availability saved.");
    } catch (err) { setError(err instanceof Error ? err.message : "Could not save availability."); }
    finally { setBusy(false); }
  }

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!account) return;
    const data = new FormData(event.currentTarget);
    setBusy(true); setError("");
    try {
      setSlots(await findSlots({ start: new Date(String(data.get("start"))).toISOString(),
        end: new Date(String(data.get("end"))).toISOString(), minutes: Number(data.get("minutes")) }, account.csrf_token));
    } catch (err) { setError(err instanceof Error ? err.message : "Could not find available slots."); }
    finally { setBusy(false); }
  }

  async function remove(id: string) {
    if (!account) return;
    setBusy(true); setError("");
    try {
      await removeAvailability(id, account.csrf_token);
      setWindows(await getAvailability()); setSlots(null); setMessage("Availability removed.");
    } catch (err) { setError(err instanceof Error ? err.message : "Could not remove availability."); }
    finally { setBusy(false); }
  }

  if (loading) return <p role="status">Loading calendar…</p>;
  if (signIn) return <p className="notice"><Link href="/sign-in">Sign in</Link> to manage your calendar.</p>;
  return <section aria-label="Local calendar" className="draft-panel">
    <h2>Local calendar</h2>
    <p>Declare when you are available for interviews. Times use your device’s time zone. This calendar stores local tentative holds and email drafts.</p>
    {error && <p role="alert" className="error">{error}</p>}
    {message && <p role="status" className="notice">{message}</p>}
    <div className="cards"><section className="card"><h3>Add availability</h3>
      <form onSubmit={saveWindow}>
        <label htmlFor="availability-start">Available from</label><input id="availability-start" name="start" type="datetime-local" required />
        <label htmlFor="availability-end">Available until</label><input id="availability-end" name="end" type="datetime-local" required />
        <button disabled={busy || !account}>Save availability</button>
      </form>
      {!windows.length && <p className="muted">No availability declared yet.</p>}
      {windows.map(window => <article className="evidence-hit" key={window.id}>
        <p>{new Date(window.start).toLocaleString()} – {new Date(window.end).toLocaleString()}</p>
        <button className="secondary-button" disabled={busy} onClick={() => remove(window.id)}>Remove availability</button>
      </article>)}
    </section><section className="card"><h3>Find interview slots</h3>
      <form onSubmit={search}>
        <label htmlFor="slot-start">Search from</label><input id="slot-start" name="start" type="datetime-local" required />
        <label htmlFor="slot-end">Search until</label><input id="slot-end" name="end" type="datetime-local" required />
        <label htmlFor="slot-minutes">Interview duration</label><select id="slot-minutes" name="minutes" defaultValue="30"><option value="15">15 minutes</option><option value="30">30 minutes</option><option value="60">60 minutes</option></select>
        <button disabled={busy || !account}>Find free slots</button>
      </form>
      {slots && <div role="region" aria-label="Available interview slots">
        {slots.slots.length ? <ul>{slots.slots.map(slot => <li key={slot.start}>{new Date(slot.start).toLocaleString()} – {new Date(slot.end).toLocaleTimeString()}</li>)}</ul> : <p>No free slots in this window.</p>}
      </div>}
    </section></div>
    <section className="card draft-panel"><h3>Approved Workspace actions</h3>
      {!actions.length && <p className="muted">No approved calendar holds or email drafts yet.</p>}
      {actions.map(action => <article className="evidence-hit" key={action.id}>
        <p>{action.tool === "create_interview_hold" ? "Tentative interview hold created" : "Local email draft saved"} · {new Date(action.created_at).toLocaleString()}</p>
        <Link href={`/runs/${action.run_id}`}>Open approval run</Link>
      </article>)}
    </section>
  </section>;
}
