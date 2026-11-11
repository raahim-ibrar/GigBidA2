"use client";
import { useEffect, useState, type FormEvent } from "react";
import { apiRequest, getAccount } from "@/lib/api/accounts";
import type { components } from "@/lib/api/schema";
type Schedule = components["schemas"]["ScheduleView"];

export function SearchScheduleSettings() {
  const [schedule, setSchedule] = useState<Schedule | null>(null); const [csrf, setCsrf] = useState("");
  const [enabled, setEnabled] = useState(false); const [autoAnalyse, setAutoAnalyse] = useState(false); const [interval, setIntervalMinutes] = useState(60);
  const [error, setError] = useState(""); const [notice, setNotice] = useState(""); const [busy, setBusy] = useState(false);
  function apply(value: Schedule) { setSchedule(value); setEnabled(value.enabled); setAutoAnalyse(value.auto_analyse); setIntervalMinutes(value.interval_minutes); }
  useEffect(() => { let active = true;
    Promise.all([getAccount(), apiRequest<Schedule>("/search-schedule")]).then(([account, value]) => { if (active) { setCsrf(account.csrf_token); apply(value); } })
      .catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, []);
  async function refresh() {
    setBusy(true); setError(""); setNotice("");
    try { apply(await apiRequest<Schedule>("/search-schedule")); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not refresh schedule."); } finally { setBusy(false); }
  }
  async function submit(event: FormEvent) {
    event.preventDefault(); if (!schedule) return; setBusy(true); setError(""); setNotice("");
    try { apply(await apiRequest<Schedule>("/search-schedule", { method: "PUT", headers: { "X-CSRF-Token": csrf }, body: JSON.stringify({ version: schedule.version, enabled, auto_analyse: autoAnalyse, interval_minutes: interval }) })); setNotice("Search schedule saved."); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not save schedule."); } finally { setBusy(false); }
  }
  return <section className="card form-card"><h2>Saved-search schedule</h2>
    <p className="notice">Saved searches fetch jobs from your connected simulator. You can also analyse one newly found job per check. Every submission still needs your approval.</p>
    {error && <p role="alert" className="error">{error}</p>}{notice && <p role="status">{notice}</p>}
    {schedule && <><p>Uses the saved searches in your freelancer profile: {schedule.queries.length ? schedule.queries.join("; ") : "no queries saved"}.</p>
      <form onSubmit={submit}><label><input type="checkbox" checked={enabled} onChange={event => setEnabled(event.target.checked)} /> Enable scheduled connection checks</label>
        <label><input type="checkbox" checked={autoAnalyse} onChange={event => setAutoAnalyse(event.target.checked)} /> Automatically analyse one new job per check</label><label htmlFor="search-interval">Check interval (minutes)</label><input id="search-interval" type="number" min={5} max={1440} required value={interval} onChange={event => setIntervalMinutes(Number(event.target.value))} />
        <p>Schedule status: <strong>{schedule.status.replaceAll("_", " ")}</strong></p>
        <p>Last connection check: {schedule.last_checked_at ? new Date(schedule.last_checked_at).toLocaleString() : "not checked yet"}</p>
        <p>Next connection check: {schedule.next_check_at ? new Date(schedule.next_check_at).toLocaleString() : "paused"}</p>
        <button disabled={busy}>{busy ? "Saving…" : "Save search schedule"}</button><button type="button" className="secondary-button" disabled={busy} onClick={refresh}>Refresh schedule</button>
      </form></>}
  </section>;
}
