"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { ApiError, getAccount, type Account } from "@/lib/api/accounts";
import { confirmStyle, getCandidates, getEdits, getMemory, removeMemory,
  type Candidate, type Edit, type MemoryList, type MemoryView } from "@/lib/api/memory";

export function MemorySettings() {
  const [account, setAccount] = useState<Account | null>(null);
  const [memory, setMemory] = useState<MemoryList | null>(null);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [edits, setEdits] = useState<Edit[]>([]);
  const [error, setError] = useState(""); const [message, setMessage] = useState("");
  const [signIn, setSignIn] = useState(false); const [busy, setBusy] = useState(false);
  const load = useCallback(async () => {
    const [saved, suggestions, history] = await Promise.all([getMemory(), getCandidates(), getEdits()]);
    setMemory(saved); setCandidates(suggestions); setEdits(history);
  }, []);
  useEffect(() => { let active = true;
    Promise.all([getAccount(), getMemory(), getCandidates(), getEdits()]).then(([user, saved, suggestions, history]) => {
      if (active) { setAccount(user); setMemory(saved); setCandidates(suggestions); setEdits(history); }
    }).catch(err => { if (active) { setError(err.message); setSignIn(err instanceof ApiError && err.status === 401); } });
    return () => { active = false; };
  }, []);
  async function confirm(candidate: Candidate) {
    if (!account) return; setBusy(true); setError(""); setMessage("");
    try { await confirmStyle(candidate.key, account.csrf_token);
      await load(); setMessage("Style preference confirmed. New proposal runs can use it."); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not confirm this preference."); }
    finally { setBusy(false); }
  }
  async function remove(item: MemoryView) {
    if (!account) return; setBusy(true); setError(""); setMessage("");
    try { await removeMemory(item, account.csrf_token); await load(); setMessage("Memory removed from future proposal runs."); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not remove this memory."); }
    finally { setBusy(false); }
  }
  if (signIn) return <p className="notice"><Link href="/sign-in">Sign in</Link> to manage memory.</p>;
  return <section aria-label="Memory settings" className="draft-panel"><h2>What GigBid remembers</h2>
    <p>Style preferences need matching edits to three distinct drafts and your confirmation. Marketplace outcomes have a separate memory. Neither is proof of portfolio experience.</p>
    {error && <p role="alert" className="error">{error}</p>}{message && <p role="status" className="notice">{message}</p>}
    {!memory && !error && <p role="status">Loading memory…</p>}
    {memory?.sync_pending && <p role="alert" className="notice">Saved memory is waiting to sync. Agents will use no long-term memory until it is available.</p>}
    {memory && <><div className="cards"><section className="card"><h3>Active style preferences</h3>
      {!memory.items.some(item => item.kind === "style") && <p className="muted">No confirmed style preferences.</p>}
      {memory.items.filter(item => item.kind === "style").map(item => <article key={item.key} className="evidence-hit">
        <p>{item.value.instruction}</p><p className="muted">Observed in {item.value.observations} distinct drafts.</p>
        <button disabled={busy} className="secondary-button" onClick={() => remove(item)}>Remove preference</button>
      </article>)}
    </section><section className="card"><h3>Outcome patterns</h3>
      <p className="muted">Patterns appear after three distinct marketplace jobs have a verified reply or win. Local drafts do not count.</p>
      {memory.items.filter(item => item.kind === "outcome").map(item => <article key={item.key} className="evidence-hit">
        <p>{item.value.category?.replaceAll("_", " ")}: {item.value.observations} jobs {item.value.outcome === "won" ? "won" : "received a reply"}.</p>
        {item.value.proposal_features && <p className="muted">Their saved drafts averaged {item.value.proposal_features.mean_cover_words} words. These are observations, not a promise of future success.</p>}
        <button disabled={busy} className="secondary-button" onClick={() => remove(item)}>Remove outcome memory</button>
      </article>)}
    </section></div><section className="card draft-panel"><h3>Patterns from your edits</h3>
      {!candidates.length && <p className="muted">No repeated edit patterns yet. Edit proposals in the proposal studio to build observations.</p>}
      {candidates.map(candidate => <article className="evidence-hit" key={candidate.key}><p>{candidate.instruction}</p>
        <p>{candidate.observations} distinct drafts · {candidate.active ? "already confirmed" : candidate.eligible ? "ready for your confirmation" : "needs three distinct drafts"}</p>
        {!candidate.active && <button disabled={busy || !candidate.eligible} onClick={() => confirm(candidate)}>Confirm preference</button>}
      </article>)}
      <button disabled={busy} className="text-button" onClick={() => load().catch(err => setError(err.message))}>Refresh memory</button>
    </section><section className="card draft-panel"><h3>Your recent draft edits</h3><p className="muted">Edit history is private run data. Removing a preference leaves its original review history intact.</p>
      {edits.length ? edits.map(edit => <details className="evidence-hit" key={edit.audit_id}><summary>Edit from {new Date(edit.created_at).toLocaleString()}</summary>
        <p><Link href={`/studio/${edit.run_id}`}>Open its proposal run</Link></p><pre className="preserve-text">{edit.diff}</pre>
      </details>) : <p className="muted">No saved edits yet.</p>}
    </section></>}
  </section>;
}
