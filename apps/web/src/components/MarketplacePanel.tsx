"use client";
import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { usePathname } from "next/navigation";
import { ApiError, getAccount } from "@/lib/api/accounts";
import { disconnectUpwork, getMarketplace, searchMarketplace, setMarketplace, syncMarketplace, type Connection } from "@/lib/api/marketplace";

export function MarketplacePanel({ onImported }: { onImported?: () => Promise<void> }) {
  const [connection, setConnection] = useState<Connection | null>(null); const [csrf, setCsrf] = useState("");
  const [error, setError] = useState(""); const [notice, setNotice] = useState(""); const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => { setConnection(await getMarketplace()); }, []);
  useEffect(() => { let active = true;
    Promise.all([getAccount(), getMarketplace()]).then(([account, current]) => { if (active) { setCsrf(account.csrf_token); setConnection(current); } })
      .catch(err => { if (active && !(err instanceof ApiError && err.status === 401)) setError(err.message); });
    return () => { active = false; };
  }, []);
  async function change(mode: "manual" | "student_sim" | "upwork") {
    setBusy(true); setError(""); setNotice("");
    try { setConnection(await setMarketplace(mode, csrf)); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not connect."); } finally { setBusy(false); }
  }
  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const query = String(new FormData(event.currentTarget).get("query"));
    setBusy(true); setError(""); setNotice("");
    try { const result = await searchMarketplace(query, csrf); setNotice(`${result.jobs.length} ${result.provider === "upwork" ? "real Upwork" : "simulator"} jobs saved to your inbox.`); if (onImported) await onImported(); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : "Search unavailable."); } finally { setBusy(false); }
  }
  async function sync() {
    setBusy(true); setError(""); setNotice("");
    try { const result = await syncMarketplace(csrf); setNotice(`Synced ${result.events} lifecycle events and ${result.messages} client messages.`); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : "Sync unavailable."); } finally { setBusy(false); }
  }
  return <section className="card draft-panel" aria-label={connection?.mode === "upwork" ? "Upwork marketplace" : "Student marketplace"}><h2>{connection?.mode === "upwork" ? "Upwork marketplace" : "Student-built marketplace"}</h2>
    <p>{connection?.mode === "upwork" ? "Real Upwork account. Reads and approved proposal previews are supported; final submissions and direct message sending are disabled." : "This simulator uses historical or synthetic job scenarios with generated clients and outcomes. Nothing is sent to a real Upwork client."}</p>
    {connection?.mode !== "upwork" && <p className="muted">Historical job data: <a href="https://www.kaggle.com/datasets/asaniczka/upwork-job-postings-dataset-2024-50k-records" target="_blank" rel="noreferrer">Asaniczka / Kaggle · ODC Attribution</a>. Portfolio demos and simulator outcomes are synthetic.</p>}
    {error && <p role="alert" className="error">{error}</p>}{notice && <p role="status">{notice}</p>}
    {!connection ? <p><Link href="/sign-in">Sign in</Link> to connect the simulator.</p> : <>
      <p>Connection: <strong>{connection.mode === "upwork" ? (connection.connected ? "Upwork authorized" : "Upwork reconnect required") : connection.connected ? (connection.available ? "student simulator online" : "student simulator unavailable") : "manual local drafts"}</strong>{connection.balance != null && ` · ${connection.balance} simulated Connects`}</p>
      {connection.error && <p role="alert" className="error">{connection.error}</p>}
      <div className="source-actions"><button disabled={busy} onClick={() => change(connection.mode === "upwork" ? "student_sim" : connection.connected ? "manual" : "student_sim")}>{connection.mode === "upwork" ? "Use student simulator" : connection.connected ? "Disconnect simulator" : "Connect student simulator"}</button>
        {connection.connected && connection.mode === "student_sim" && <button className="secondary-button" disabled={busy} onClick={sync}>Sync simulator activity</button>}</div>
      {connection.connected && <form onSubmit={search}><label htmlFor="simulator-query">{connection.mode === "upwork" ? "Upwork job search" : "Simulator job search"}</label><input id="simulator-query" name="query" required maxLength={500} placeholder="Python, React, SQL…" /><button disabled={busy}>{connection.mode === "upwork" ? "Search Upwork jobs" : "Search simulator jobs"}</button></form>}
      <h3>Upwork connection</h3>
      <p className="muted">Connect or reconnect on the host laptop with <code>python -m scripts.connect_upwork</code>, then refresh this page. Sign-in happens on Upwork; never paste a password or token here.</p>
      <p>{connection.upwork_connected ? "Upwork authorization is saved for your account." : "Upwork has not been authorized, or the local encryption key is unavailable."}</p>
      {connection.expires_at && <p className="muted">Current access token expires: {new Date(connection.expires_at).toLocaleString()}. Refresh is automatic while authorization remains valid.</p>}
      {!!connection.capabilities?.length && <p className="muted">Available: {connection.capabilities?.join(", ")}. Final submission, direct messages and a simulator-style event feed are disabled.</p>}
      <div className="source-actions">{connection.upwork_connected && connection.mode !== "upwork" && <button disabled={busy} onClick={() => change("upwork")}>Use Upwork</button>}
        {connection.upwork_connected && <button className="secondary-button" disabled={busy} onClick={async () => { setBusy(true); try { setConnection(await disconnectUpwork(csrf)); } catch (err) { setError((err as Error).message); } finally { setBusy(false); } }}>Revoke Upwork connection</button>}
        <button className="secondary-button" disabled={busy} onClick={() => void refresh().catch(err => setError(err.message))}>Refresh connection</button></div>
    </>}
  </section>;
}

export function MarketplaceBanner() {
  const pathname = usePathname(); const [connection, setConnection] = useState<Connection | null>(null);
  useEffect(() => { let active = true; let anonymous = false;
    async function load() { if (anonymous) return;
      try { const value = await getMarketplace(); if (active) setConnection(value); }
      catch (err) { if (err instanceof ApiError && err.status === 401) { anonymous = true; if (active) setConnection(null); } }
    }
    void load(); const timer = setInterval(() => void load(), 5000);
    return () => { active = false; clearInterval(timer); };
  }, [pathname]);
  if (!connection?.connected || connection.available) return null;
  return <p role="alert" className="notice error" data-testid="marketplace-outage">{connection.mode === "upwork" ? "Upwork unavailable or reconnect required. Your saved work is preserved. Reconnect on the host laptop; uncertain provider writes are never retried automatically." : "Student simulator unavailable. Your saved jobs, reviews and drafts are preserved. Restore the simulator, then retry interrupted runs."}</p>;
}
