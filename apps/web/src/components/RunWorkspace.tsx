"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, getAccount, type Account } from "@/lib/api/accounts";
import { getRun, reviewRun, type Draft, type Evidence, type Review, type Run } from "@/lib/api/proposals";
type Progress = { id: number; kind: string; details: Record<string, unknown> };

function ClaimLine({ text, draft, evidence }: { text: string; draft: Draft; evidence: Evidence[] }) {
  const claim = draft.claims?.find(item => item.text === text);
  const sources = evidence.filter(item => claim?.evidence_ids?.includes(item.id));
  if (!sources.length) return <p>{text}</p>;
  return <p><span tabIndex={0} className="grounded-claim" aria-label={`${text} Portfolio evidence available.`}>{text}<span className="evidence-popover" role="tooltip">{sources.map(source => <span key={source.id}><strong>{source.source}{source.page ? ` · page ${source.page}` : ""}</strong><br />{source.text}<br /></span>)}</span></span></p>;
}

export function RunWorkspace({ id, trace = false }: { id: string; trace?: boolean }) {
  const [run, setRun] = useState<Run | null>(null); const [account, setAccount] = useState<Account | null>(null);
  const [events, setEvents] = useState<Progress[]>([]); const [error, setError] = useState(""); const [signIn, setSignIn] = useState(false);
  const [edit, setEdit] = useState(""); const [reason, setReason] = useState(""); const [busy, setBusy] = useState(false);
  const cursor = useRef(0); const loaded = !!run; const active = !!run && ["queued", "running"].includes(run.status);
  const refresh = useCallback(async () => { setRun(await getRun(id)); }, [id]);
  useEffect(() => { let mounted = true;
    Promise.all([getRun(id), getAccount()]).then(([current, user]) => { if (mounted) { setRun(current); setAccount(user); } })
      .catch(err => { if (mounted) { setError(err.message); setSignIn(err instanceof ApiError && err.status === 401); } }); return () => { mounted = false; };
  }, [id]);
  useEffect(() => { if (run?.status === "awaiting_approval") setEdit(run.snapshot.draft?.text ?? ""); }, [run?.version, run?.status, run?.snapshot.draft?.text]);
  useEffect(() => { if (!loaded || signIn) return;
    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    const source = new EventSource(`${base}/api/runs/${encodeURIComponent(id)}/events?after=${cursor.current}`, { withCredentials: true });
    source.addEventListener("progress", event => { try { const item = JSON.parse((event as MessageEvent).data) as Progress;
      if (item.id > cursor.current) { cursor.current = item.id; setEvents(previous => [...previous, item].slice(-100)); }
    } catch { /* Malformed progress cannot authorize or modify a run. */ } });
    source.addEventListener("done", () => { source.close(); void refresh().catch(err => setError(err.message)); });
    const timer = active ? setInterval(() => refresh().catch(err => setError(err.message)), 3000) : undefined;
    return () => { source.close(); if (timer) clearInterval(timer); };
  }, [id, active, loaded, signIn, refresh]);
  async function decide(action: Review["action"]) { if (!run || !account) return;
    const digest = run.snapshot.preview?.arguments.draft_digest;
    if (typeof digest !== "string") { setError("Reload this run to get its current preview."); return; }
    if (action === "reject" && !reason.trim()) { setError("Enter a rejection reason."); return; }
    if (action === "edit" && !edit.trim()) { setError("Enter a draft before requesting verification."); return; }
    setBusy(true); setError("");
    try { setRun(await reviewRun({ run_id: id, version: run.version, draft_digest: digest, action, reason: action === "reject" ? reason : null, edited_text: action === "edit" ? edit : null }, account.csrf_token)); }
    catch (err) { setError(err instanceof Error ? err.message : "Decision could not be saved."); } finally { setBusy(false); }
  }
  if (signIn) return <p className="notice"><Link href="/sign-in">Sign in</Link> to view this run.</p>;
  if (!run) return error ? <p role="alert" className="error">{error}</p> : <p role="status">Loading run…</p>;
  const state = run.snapshot; const draft = state.draft; const evidence = state.evidence ?? []; const ready = run.status === "awaiting_approval";
  return <><div className="source-actions"><Link href={`/jobs/${run.job_id}`}>Job detail</Link><Link href={`/studio/${id}`}>Proposal review</Link><Link href={`/runs/${id}`}>Run activity</Link></div>
    <p role="status" className="notice">Status: <strong>{run.status.replaceAll("_", " ")}</strong>{active && " · Working in the background; you can leave this page."}</p>
    {error && <p role="alert" className="error">{error}</p>}{run.error && <p role="alert" className="error">{run.error}</p>}{state.job && <h2>{state.job.title}</h2>}
    <div className="cards"><section className="card"><h2>Recommendation</h2>{state.decision ? <><strong>{state.decision.action}</strong><ul>{state.decision.reasons.map((text, i) => <li key={i}>{text}</li>)}</ul></> : <p className="muted">Waiting for analysis.</p>}
      {state.risk && <><h3>Risk: {Math.round(state.risk.score * 100)}%</h3><ul>{state.risk.reasons?.map((text, i) => <li key={i}>{text}</li>)}</ul></>}
      {state.price && <p>Provisional quote: ${state.price.amount} {state.price.billing_type === "hourly" ? "per hour" : "total"}. {state.price.rationale}</p>}
    </section><section className="card"><h2>Requirement evidence</h2>{state.fit ? <><p>Coverage: {Math.round(state.fit.score * 100)}%</p>{Object.entries(state.fit.requirement_evidence).map(([requirement, ids]) => <div key={requirement}><strong>{requirement}</strong>{ids.length ? <ul>{ids.map(sourceId => { const source = evidence.find(item => item.id === sourceId); return <li key={sourceId}>{source?.source ?? "Source unavailable"}<details><summary>Read evidence</summary><p>{source?.text}</p></details></li>; })}</ul> : <p className="muted">No supporting evidence.</p>}</div>)}</> : <p className="muted">Waiting for portfolio matching.</p>}</section></div>
    {draft && (ready || run.status === "drafted") && <section className="card draft-panel"><h2>{run.status === "drafted" ? "Saved local draft" : "Verified draft for review"}</h2><p className="muted">Hover or focus an underlined claim to inspect its portfolio source.</p>
      {draft.text.split("\n").map((text, i) => <ClaimLine key={i} text={text} draft={draft} evidence={evidence} />)}
      {Object.entries(draft.screening_answers ?? {}).map(([question, answer]) => <div key={question}><h3>{question}</h3>{answer.split("\n").map((text, i) => <ClaimLine key={i} text={text} draft={draft} evidence={evidence} />)}</div>)}
      {state.critique?.reasons?.length ? <p>Critic: {state.critique.reasons.join(" ")}</p> : null}<p>Local draft checks: {state.compliance?.allowed ? "passed" : "pending"}. Instructor marketplace policy is not supplied.</p>
      {ready && <><h3>Preview</h3><p>Save this draft locally. Connects spent: 0. No application will be sent.</p><button disabled={busy} onClick={() => decide("approve")}>Approve and save local draft</button>
        <label htmlFor="edited-draft">Edit cover letter</label><textarea id="edited-draft" rows={9} maxLength={20000} value={edit} onChange={event => setEdit(event.target.value)} /><button className="secondary-button" disabled={busy} onClick={() => decide("edit")}>Verify edits and request a new review</button>
        <label htmlFor="rejection-reason">Reason for rejection</label><textarea id="rejection-reason" rows={2} maxLength={1000} value={reason} onChange={event => setReason(event.target.value)} /><button className="secondary-button" disabled={busy} onClick={() => decide("reject")}>Reject draft</button></>}
    </section>}
    {(trace || active) && <section className="card draft-panel"><h2>Run activity</h2><p className="muted">{run.steps} steps · {run.tokens} tokens charged or reserved. Local model costs exclude hardware and electricity.</p><ol className="run-events">{events.map(event => <li key={event.id}>{event.kind.replaceAll("_", " ")}{typeof event.details.node === "string" && ` · ${event.details.node}`}{typeof event.details.role === "string" && ` · ${event.details.role}`}</li>)}</ol></section>}
  </>;
}
