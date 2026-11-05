"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { getAccount, type Account } from "@/lib/api/accounts";
import { getJob, listRuns, startRun, type Job, type Run } from "@/lib/api/proposals";

export function JobDetail({ id }: { id: string }) {
  const router = useRouter(); const key = useRef("");
  const [job, setJob] = useState<Job | null>(null); const [runs, setRuns] = useState<Run[]>([]);
  const [account, setAccount] = useState<Account | null>(null); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  useEffect(() => { let active = true;
    Promise.all([getJob(id), listRuns(id), getAccount()]).then(([saved, progress, user]) => { if (active) { setJob(saved); setRuns(progress); setAccount(user); } })
      .catch(err => { if (active) setError(err.message); }); return () => { active = false; };
  }, [id]);
  async function start() { if (!account) return; setBusy(true); setError("");
    try { key.current ||= crypto.randomUUID(); const run = await startRun(id, key.current, account.csrf_token); router.push(`/studio/${run.id}`); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not start analysis."); setBusy(false); }
  }
  return <>{error && <p role="alert" className="error">{error} <Link href="/sign-in">Sign in</Link></p>}{job ? <><h2>{job.title}</h2><section className="card"><p className="preserve-text">{String(job.raw.description ?? "")}</p><p>Client budget: ${String(job.raw.budget_max)} {job.raw.billing_type === "hourly" ? "per hour" : "total"} · manually entered</p><button onClick={start} disabled={busy || !account}>{busy ? "Starting…" : "Start a new proposal run"}</button></section><h2>Analysis and drafts</h2>{runs.length ? runs.map(run => <p key={run.id}><Link href={`/studio/${run.id}`}>{run.status.replaceAll("_", " ")}</Link> · {new Date(run.created_at).toLocaleString()}</p>) : <p>No runs yet.</p>}</> : !error && <p role="status">Loading job…</p>}</>;
}
