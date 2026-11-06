"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { listRuns, type Run } from "@/lib/api/proposals";

export function RunList() {
  const [runs, setRuns] = useState<Run[] | null>(null); const [error, setError] = useState("");
  const [attentionOnly, setAttentionOnly] = useState(false);
  useEffect(() => { let active = true;
    listRuns().then(saved => { if (active) setRuns(saved); }).catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, []);
  if (error) return <p role="alert" className="error">{error} <Link href="/sign-in">Sign in</Link></p>;
  if (!runs) return <p role="status">Loading your runs…</p>;
  const visible = attentionOnly ? runs.filter(run => ["needs_attention", "failed"].includes(run.status)) : runs;
  return <section className="card"><label><input type="checkbox" checked={attentionOnly} onChange={event => setAttentionOnly(event.target.checked)} /> Show only runs needing attention</label>{visible.length ? visible.map(run => <article className="evidence-hit" key={run.id}>
    <h2><Link href={`/runs/${run.id}`}>{run.snapshot.conversation_title ?? run.snapshot.job?.title ?? "Job analysis"}</Link></h2>
    <p>{run.status === "failed" ? "Retries exhausted" : run.status.replaceAll("_", " ")} · {new Date(run.created_at).toLocaleString()}</p>{run.error && <p className="error">{run.error}</p>}<Link href={run.kind === "conversation" ? `/messages/${run.snapshot.conversation_id}` : `/studio/${run.id}`}>{run.kind === "conversation" ? "Open conversation" : "Open proposal review"}</Link>
  </article>) : <p>{attentionOnly ? "No runs need attention." : <>No runs yet. <Link href="/inbox">Add a job</Link> to start.</>}</p>}</section>;
}
