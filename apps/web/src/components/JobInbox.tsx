"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, getAccount, type Account } from "@/lib/api/accounts";
import { createJob, listJobs, listRuns, startRun, type Job, type Run } from "@/lib/api/proposals";

export function JobInbox() {
  const router = useRouter(); const requestKey = useRef({ job: "", key: "" });
  const [account, setAccount] = useState<Account | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]); const [runs, setRuns] = useState<Run[]>([]);
  const [error, setError] = useState(""); const [loading, setLoading] = useState(true);
  const [signIn, setSignIn] = useState(false); const [busy, setBusy] = useState(false);
  useEffect(() => { let active = true;
    Promise.all([getAccount(), listJobs(), listRuns()]).then(([user, saved, progress]) => {
      if (active) { setAccount(user); setJobs(saved); setRuns(progress); }
    }).catch(err => { if (active) { setError(err.message); setSignIn(err instanceof ApiError && err.status === 401); } })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!account) return; setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    try {
      const job = await createJob({ title: String(data.get("title")), description: String(data.get("description")),
        billing_type: String(data.get("billing_type")) as "hourly" | "fixed", currency: "USD",
        budget_min: data.get("budget_min") ? Number(data.get("budget_min")) : null,
        budget_max: Number(data.get("budget_max")) }, account.csrf_token);
      if (requestKey.current.job !== job.id) requestKey.current = { job: job.id, key: crypto.randomUUID() };
      const run = await startRun(job.id, requestKey.current.key, account.csrf_token); router.push(`/studio/${run.id}`);
    } catch (err) { setError(err instanceof Error ? err.message : "Could not start this job."); setBusy(false); }
  }
  if (loading) return <p role="status">Loading jobs…</p>;
  if (signIn) return <p className="notice"><Link href="/sign-in">Sign in</Link> to add and review jobs.</p>;
  return <>{error && <p role="alert" className="error">{error}</p>}
    <p className="notice">Enter a job to analyse it against your <Link href="/portfolio">portfolio</Link>. Approval saves a local draft. Marketplace connection is pending.</p>
    <div className="cards portfolio-columns"><section className="card"><h2>Add a job</h2><form onSubmit={submit}>
      <label htmlFor="job-title">Job title</label><input id="job-title" name="title" required maxLength={200} />
      <label htmlFor="job-description">Job description and screening questions</label><textarea id="job-description" name="description" rows={8} required maxLength={12000} />
      <label htmlFor="billing-type">Pricing</label><select id="billing-type" name="billing_type" defaultValue="hourly"><option value="hourly">Hourly · USD per hour</option><option value="fixed">Fixed price · USD total</option></select>
      <label htmlFor="budget-min">Minimum client budget (optional)</label><input id="budget-min" name="budget_min" type="number" min="0.01" max="1000000" step="0.01" />
      <label htmlFor="budget-max">Maximum client budget</label><input id="budget-max" name="budget_max" type="number" min="0.01" max="1000000" step="0.01" required />
      <button disabled={busy || !account}>{busy ? "Starting analysis…" : "Analyse and draft"}</button>
    </form></section><section className="card"><h2>Your jobs</h2>{!jobs.length && <p className="muted">No jobs added yet.</p>}
      {jobs.map(job => { const latest = runs.find(run => run.job_id === job.id); return <article className="evidence-hit" key={job.id}><h3><Link href={`/jobs/${job.id}`}>{job.title}</Link></h3><p className="muted">Manually entered · {latest ? latest.status.replaceAll("_", " ") : "Not analysed"}</p>{latest && <Link href={`/studio/${latest.id}`}>Open proposal run</Link>}</article>; })}
    </section></div></>;
}
