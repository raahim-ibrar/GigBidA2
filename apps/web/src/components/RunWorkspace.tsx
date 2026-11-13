"use client";
import Link from "next/link";
import { CheckpointReplay } from "./CheckpointReplay";
import { RunCostReport } from "./CostReport";
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { ApiError, apiRequest, getAccount, type Account } from "@/lib/api/accounts";
import { getRun, getRunActivity, retryRun, reviewRun, type Draft, type Evidence, type Review, type Run } from "@/lib/api/proposals";
type Progress = { id: number; kind: string; details: Record<string, unknown> };

function ClaimLine({ text, draft, evidence }: { text: string; draft: Draft; evidence: Evidence[] }) {
  const parts: ReactNode[] = []; let offset = 0;
  while (offset < text.length) {
    const matches = (draft.claims ?? []).filter(claim => claim.text.length > 0)
      .map(claim => ({ claim, index: text.indexOf(claim.text, offset) })).filter(item => item.index >= 0)
      .sort((a, b) => a.index - b.index);
    const match = matches[0]; if (!match) break;
    if (match.index > offset) parts.push(text.slice(offset, match.index));
    const sources = evidence.filter(item => match.claim.evidence_ids?.includes(item.id));
    parts.push(sources.length ? <span key={match.index} tabIndex={0} className="grounded-claim" aria-label={`${match.claim.text} Portfolio evidence available.`}>{match.claim.text}<span className="evidence-popover" role="tooltip">{sources.map(source => <span key={source.id}><strong>{source.source}{source.page ? ` Â· page ${source.page}` : ""}</strong><br />{source.text}<br /></span>)}</span></span> : match.claim.text);
    offset = match.index + match.claim.text.length;
  }
  parts.push(text.slice(offset)); return <p>{parts}</p>;
}

export function RunWorkspace({ id, trace = false, onSaved }: { id: string; trace?: boolean; onSaved?: () => Promise<void> }) {
  const [run, setRun] = useState<Run | null>(null); const [account, setAccount] = useState<Account | null>(null);
  const [events, setEvents] = useState<Progress[]>([]); const [error, setError] = useState(""); const [signIn, setSignIn] = useState(false);
  const [edit, setEdit] = useState(""); const [reason, setReason] = useState(""); const [busy, setBusy] = useState(false);
  const [paragraph, setParagraph] = useState(0);
  const [traceInfo, setTraceInfo] = useState<{ status: string; public_url: string | null; spans: number } | null>(null);
  useEffect(() => { void apiRequest<{ status: string; public_url: string | null; spans: number }>(`/runs/${encodeURIComponent(id)}/trace`).then(setTraceInfo).catch(() => {}); }, [id, run?.status]);
  const cursor = useRef(0); const loaded = !!run; const active = !!run && ["queued", "running"].includes(run.status);
  const refresh = useCallback(async () => { setRun(await getRun(id)); }, [id]);
  useEffect(() => { if (run && ["drafted", "sent"].includes(run.status) && onSaved) void onSaved().catch(err => setError(err.message)); }, [run?.status, onSaved, run]);
  useEffect(() => { let mounted = true;
    Promise.all([getRun(id), getAccount()]).then(([current, user]) => { if (mounted) { setRun(current); setAccount(user); } })
      .catch(err => { if (mounted) { setError(err.message); setSignIn(err instanceof ApiError && err.status === 401); } }); return () => { mounted = false; };
  }, [id]);
  useEffect(() => { if (run?.status === "awaiting_approval") { setEdit(run.snapshot.draft?.text ?? ""); setParagraph(0); } }, [run?.version, run?.status, run?.snapshot.draft?.text]);
  useEffect(() => { if (!loaded || signIn) return;
    let mounted = true;
    const ingest = (incoming: Progress[]) => { if (!mounted || !incoming.length) return;
      cursor.current = Math.max(cursor.current, ...incoming.map(item => item.id));
      setEvents(previous => Array.from(new Map([...previous, ...incoming].map(item => [item.id, item])).values()).sort((a, b) => a.id - b.id).slice(-100));
    };
    const replay = async () => { for (let page = 0; page < 5 && mounted; page += 1) {
      const items = await getRunActivity(id, cursor.current); ingest(items); if (items.length < 200) break;
    } };
    void replay().catch(() => { /* SSE remains available when replay is temporarily unavailable. */ });
    const base = process.env.NEXT_PUBLIC_API_URL ?? "";
    const source = new EventSource(`${base}/api/runs/${encodeURIComponent(id)}/events?after=${cursor.current}`, { withCredentials: true });
    source.addEventListener("progress", event => { try { const item = JSON.parse((event as MessageEvent).data) as Progress;
      ingest([item]);
    } catch { /* Malformed progress cannot authorize or modify a run. */ } });
    source.addEventListener("done", () => { source.close(); void refresh().catch(err => setError(err.message)); });
    const timer = active ? setInterval(() => {
      void refresh().catch(err => setError(err.message));
      void replay().catch(() => { /* The next poll or SSE reconnect retries durable progress. */ });
    }, 3000) : undefined;
    return () => { mounted = false; source.close(); if (timer) clearInterval(timer); };
  }, [id, active, loaded, signIn, refresh]);
  async function decide(action: Review["action"]) { if (!run || !account) return;
    const digest = run.review?.draft_digest ?? run.snapshot.preview?.arguments.draft_digest;
    if (typeof digest !== "string") { setError("Reload this run to get its current preview."); return; }
    if (action === "reject" && !reason.trim()) { setError("Enter a rejection reason."); return; }
    if (action === "edit" && !edit.trim()) { setError("Enter a draft before requesting verification."); return; }
    setBusy(true); setError("");
    try { setRun(await reviewRun({ run_id: id, version: run.version, draft_digest: digest, action, reason: action === "reject" ? reason : null, edited_text: action === "edit" ? edit : null, paragraph_index: action === "regenerate" ? paragraph : null }, account.csrf_token)); }
    catch (err) { setError(err instanceof Error ? err.message : "Decision could not be saved."); } finally { setBusy(false); }
  }
  async function retry() {
    if (!run || !account) return; setBusy(true); setError("");
    try { setRun(await retryRun(id, run.version, account.csrf_token)); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not retry this run."); }
    finally { setBusy(false); }
  }
  if (signIn) return <p className="notice"><Link href="/sign-in">Sign in</Link> to view this run.</p>;
  if (!run) return error ? <p role="alert" className="error">{error}</p> : <p role="status">Loading runâ€¦</p>;
  const state = run.snapshot; const draft = state.draft; const evidence = state.evidence ?? []; const ready = run.status === "awaiting_approval";
  const conversation = run.kind === "conversation";
  const liveProposal = state.preview?.tool === "submit_proposal" && state.marketplace_provider === "upwork";
  const simulatorProposal = state.preview?.tool === "submit_proposal" && !liveProposal;
  const simulatorReply = state.preview?.tool === "send_message";
  const completed = ["drafted", "submitted", "sent", "pending_provider_confirmation"].includes(run.status);
  const completedTitle = run.status === "pending_provider_confirmation" ? "Upwork preview prepared â€” not submitted" : run.status === "submitted" ? "Submitted to student simulator" : run.status === "sent" ? "Reply sent to student simulator" : conversation ? "Saved local email draft" : "Saved local draft";
  const paragraphs = draft?.text.match(/\S[\s\S]*?(?=\n[ \t\r]*\n|$)/g) ?? [];
  return <div className="section-stack run-workspace"><nav className="source-actions run-nav" aria-label="Proposal navigation"><Link href={`/jobs/${run.job_id}`}>Job detail</Link><Link href={conversation ? `/messages/${state.conversation_id}` : `/studio/${id}`}>{conversation ? "Conversation" : "Proposal review"}</Link><Link href={`/runs/${id}`}>Run activity</Link></nav>
    <p role="status" className="notice">Status: <strong>{run.status.replaceAll("_", " ")}</strong>{active && " Â· Working in the background; you can leave this page."}</p>
    {error && <p role="alert" className="error">{error}</p>}{run.error && <p role="alert" className="error">{run.error}</p>}{state.job && <h2>{state.job.title}</h2>}
    {["needs_attention", "failed"].includes(run.status) && <section className="card"><h2>{run.status === "failed" ? "Retries exhausted" : "Run needs attention"}</h2><p>{run.retry_count ?? 0} of 3 retries used. Previous token charges and step counts are preserved.</p>
      {run.retryable ? <><p>Retry the failed step after restoring the unavailable service. Any earlier approval remains limited to its exact preview.</p><button disabled={busy} onClick={retry}>{busy ? "Queuing retryâ€¦" : "Retry failed step"}</button></> : <p>Inspect the error and correct the source inputs. This run cannot be retried from this screen.</p>}
    </section>}
    <div className="cards"><section className="card"><h2>{conversation ? "Client intent" : "Recommendation"}</h2>{conversation ? <p>{state.intent ?? "Waiting for classification."}</p> : state.decision ? <><strong>{state.decision.action}</strong><ul>{state.decision.reasons.map((text, i) => <li key={i}>{text}</li>)}</ul></> : <p className="muted">Waiting for analysis.</p>}
      {state.risk && <><h3>Risk: {Math.round(state.risk.score * 100)}%</h3><ul>{state.risk.reasons?.map((text, i) => <li key={i}>{text}</li>)}</ul></>}
      {state.price && <p>Provisional quote: ${state.price.amount} {state.price.billing_type === "hourly" ? "per hour" : "total"}. {state.price.rationale}</p>}
    </section><section className="card"><h2>{conversation ? "Reply evidence" : "Requirement evidence"}</h2>{conversation ? <p>{evidence.length} portfolio sources retrieved. Inspect the underlined claims below.</p> : state.fit ? <><p>Coverage: {Math.round(state.fit.score * 100)}%</p>{Object.entries(state.fit.requirement_evidence).map(([requirement, ids]) => <div key={requirement}><strong>{requirement}</strong>{ids.length ? <ul>{ids.map(sourceId => { const source = evidence.find(item => item.id === sourceId); return <li key={sourceId}>{source?.source ?? "Source unavailable"}<details><summary>Read evidence</summary><p>{source?.text}</p></details></li>; })}</ul> : <p className="muted">No supporting evidence.</p>}</div>)}</> : <p className="muted">Waiting for portfolio matching.</p>}</section></div>
    {draft && (ready || completed) && <section className="card draft-panel"><h2>{completed ? completedTitle : (conversation ? "Verified reply for review" : "Verified draft for review")}</h2><p className="muted">Hover or focus an underlined claim to inspect its portfolio source.</p>
      {draft.text.split("\n").map((text, i) => <ClaimLine key={i} text={text} draft={draft} evidence={evidence} />)}
      {Object.entries(draft.screening_answers ?? {}).map(([question, answer]) => <div key={question}><h3>{question}</h3>{answer.split("\n").map((text, i) => <ClaimLine key={i} text={text} draft={draft} evidence={evidence} />)}</div>)}
      {state.critique?.reasons?.length ? <p>Critic: {state.critique.reasons.join(" ")}</p> : null}<p>Local draft checks: {state.compliance?.allowed ? "passed" : "pending"}. Instructor marketplace policy is not supplied.</p>
      {!!state.memory?.style_preferences?.length && <details><summary>Style preferences used in this run</summary><ul>{state.memory.style_preferences.map((text, index) => <li key={index}>{text}</li>)}</ul><p className="muted">These were loaded when this run started. Grounding and approval still apply.</p></details>}
      {conversation && state.preview && <div><h3>{simulatorReply ? "Simulator message preview" : "Email draft preview"}</h3>{!simulatorReply && <p>Subject: {String(state.preview.arguments.subject)}</p>}<pre style={{ whiteSpace: "pre-wrap" }}>{String(simulatorReply ? state.preview.arguments.text : state.preview.arguments.body)}</pre></div>}
      {ready && <><h3>Preview</h3><p>{liveProposal ? `Prepare this exact proposal as an Upwork preview. Application cost if you later submit: ${state.preview?.connects_cost} real Connects. GigBid will not confirm or submit it.` : simulatorProposal ? `Submit this proposal to the student simulator. Simulated Connects spent: ${state.preview?.connects_cost}. No real Upwork application is sent.` : simulatorReply ? "Send this exact reply to the student simulator. No real client is contacted." : conversation ? "Save this email draft locally. No message will be sent." : "Save this draft locally. Connects spent: 0. No application will be sent."}</p><button disabled={busy} onClick={() => decide("approve")}>{liveProposal ? "Approve Upwork preview preparation" : simulatorProposal ? "Approve and submit to simulator" : simulatorReply ? "Approve and send simulator reply" : conversation ? "Approve and save email draft" : "Approve and save local draft"}</button>
        <label htmlFor="edited-draft">{conversation ? "Edit reply" : "Edit cover letter"}</label><textarea id="edited-draft" rows={9} maxLength={20000} value={edit} onChange={event => setEdit(event.target.value)} /><button className="secondary-button" disabled={busy} onClick={() => decide("edit")}>Verify edits and request a new review</button>
        {!conversation && paragraphs.length > 0 && <><label htmlFor="regenerate-paragraph">Paragraph to regenerate</label><select id="regenerate-paragraph" value={paragraph} onChange={event => setParagraph(Number(event.target.value))}>{paragraphs.slice(0, 100).map((text, index) => <option key={index} value={index}>{index + 1}. {text.slice(0, 100)}</option>)}</select><p className="muted">Regeneration uses the verified draft above and preserves the other paragraphs. The result is checked and needs a new approval.</p><button className="secondary-button" disabled={busy} onClick={() => decide("regenerate")}>Regenerate selected paragraph</button></>}
        <label htmlFor="rejection-reason">Reason for rejection</label><textarea id="rejection-reason" rows={2} maxLength={1000} value={reason} onChange={event => setReason(event.target.value)} /><button className="secondary-button" disabled={busy} onClick={() => decide("reject")}>Reject draft</button></>}
    </section>}
    {run.status === "pending_provider_confirmation" && <section className="card"><h2>Final confirmation remains on Upwork</h2><p>No proposal was submitted and no Connects were spent. Final confirmation is disabled in GigBid.</p><p>Provider preview ID: <code>{String(state.provider_result?.preview_id ?? "unavailable")}</code></p><p className="muted">This is a server preview, not a confirmed application. Review it through an authorized Upwork client or prepare the application manually on Upwork. A provider preview may expire.</p></section>}
    <RunCostReport runId={id} revision={`${run.status}:${run.tokens}:${run.steps}`} />
    {trace && account && run.kind === "bid" && <CheckpointReplay runId={id} csrf={account.csrf_token} />}
    {(trace || active) && <section className="card draft-panel"><h2>Run activity</h2><p className="muted">{run.steps} steps Â· {run.tokens} tokens charged or reserved. Local model costs exclude hardware and electricity.</p><p className="muted">Trace ID: <code>{id}</code> Â· {traceInfo?.status ?? "not exported"}{traceInfo?.public_url && <> Â· <a href={traceInfo.public_url} target="_blank" rel="noreferrer">Open public trace</a></>}</p><ol className="run-events">{events.map(event => <li key={event.id}>{event.kind.replaceAll("_", " ")}{typeof event.details.node === "string" && ` Â· ${event.details.node}`}{typeof event.details.role === "string" && ` Â· ${event.details.role}`}</li>)}</ol></section>}
  </div>;
}
