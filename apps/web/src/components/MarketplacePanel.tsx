"use client";
import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { usePathname } from "next/navigation";
import { ApiError, getAccount } from "@/lib/api/accounts";
import { getMarketplace, searchMarketplace, setMarketplace, syncMarketplace, type Connection } from "@/lib/api/marketplace";

export function MarketplacePanel({ onImported }: { onImported?: () => Promise<void> }) {
  const [connection, setConnection] = useState<Connection | null>(null); const [csrf, setCsrf] = useState("");
  const [error, setError] = useState(""); const [notice, setNotice] = useState(""); const [busy, setBusy] = useState(false);
  const refresh = useCallback(async () => { setConnection(await getMarketplace()); }, []);
  useEffect(() => { let active = true;
    Promise.all([getAccount(), getMarketplace()]).then(([account, current]) => { if (active) { setCsrf(account.csrf_token); setConnection(current); } })
      .catch(err => { if (active && !(err instanceof ApiError && err.status === 401)) setError(err.message); });
    return () => { active = false; };
  }, []);
  async function change(mode: "manual" | "student_sim") {
    setBusy(true); setError(""); setNotice("");
    try { setConnection(await setMarketplace(mode, csrf)); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not connect."); } finally { setBusy(false); }
  }
  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); const query = String(new FormData(event.currentTarget).get("query"));
    setBusy(true); setError(""); setNotice("");
    try { const result = await searchMarketplace(query, csrf); setNotice(`${result.jobs.length} simulator jobs saved to your inbox.`); if (onImported) await onImported(); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : "Search unavailable."); } finally { setBusy(false); }
  }
  async function sync() {
    setBusy(true); setError(""); setNotice("");
    try { const result = await syncMarketplace(csrf); setNotice(`Synced ${result.events} lifecycle events and ${result.messages} client messages.`); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : "Sync unavailable."); } finally { setBusy(false); }
  }
  return <section className="card draft-panel" aria-label="Student marketplace"><h2>Student-built marketplace</h2>
    <p>This simulator uses historical or synthetic job scenarios with generated clients and outcomes. Nothing is sent to a real Upwork client.</p>
    <p className="muted">Historical job data: <a href="https://www.kaggle.com/datasets/asaniczka/upwork-job-postings-dataset-2024-50k-records" target="_blank" rel="noreferrer">Asaniczka / Kaggle · ODC Attribution</a>. Portfolio demos and simulator outcomes are synthetic.</p>
    {error && <p role="alert" className="error">{error}</p>}{notice && <p role="status">{notice}</p>}
    {!connection ? <p><Link href="/sign-in">Sign in</Link> to connect the simulator.</p> : <>
      <p>Connection: <strong>{connection.connected ? (connection.available ? "student simulator online" : "student simulator unavailable") : "manual local drafts"}</strong>{connection.balance != null && ` · ${connection.balance} simulated Connects`}</p>
      {connection.error && <p role="alert" className="error">{connection.error}</p>}
      <div className="source-actions"><button disabled={busy} onClick={() => change(connection.connected ? "manual" : "student_sim")}>{connection.connected ? "Disconnect simulator" : "Connect student simulator"}</button>
        {connection.connected && <button className="secondary-button" disabled={busy} onClick={sync}>Sync simulator activity</button>}</div>
      {connection.connected && <form onSubmit={search}><label htmlFor="simulator-query">Simulator job search</label><input id="simulator-query" name="query" required maxLength={500} placeholder="Python, React, SQL…" /><button disabled={busy}>Search simulator jobs</button></form>}
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
  return <p role="alert" className="notice error" data-testid="marketplace-outage">Student simulator unavailable. Your saved jobs, reviews and drafts are preserved. Restore the simulator, then retry interrupted runs.</p>;
}
