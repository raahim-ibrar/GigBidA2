"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { getAccount, type Account } from "@/lib/api/accounts";
import { listJobs, type Job } from "@/lib/api/proposals";
import { createConversation, listConversations, type Conversation } from "@/lib/api/messages";

export function ConversationInbox() {
  const router = useRouter(); const request = useRef({ body: "", key: "" });
  const [account, setAccount] = useState<Account | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]); const [threads, setThreads] = useState<Conversation[]>([]);
  const [error, setError] = useState(""); const [loading, setLoading] = useState(true); const [busy, setBusy] = useState(false);
  useEffect(() => { let active = true;
    Promise.all([getAccount(), listJobs(), listConversations()]).then(([user, saved, conversations]) => {
      if (active) { setAccount(user); setJobs(saved); setThreads(conversations); }
    }).catch(err => { if (active) setError(err.message); }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!account) return; setBusy(true); setError("");
    const data = new FormData(event.currentTarget);
    const body = { job_id: String(data.get("job")), title: String(data.get("title")), text: String(data.get("text")) };
    const serialized = JSON.stringify(body);
    if (request.current.body !== serialized) request.current = { body: serialized, key: crypto.randomUUID() };
    try { const conversation = await createConversation({ ...body, idempotency_key: request.current.key }, account.csrf_token); router.push(`/messages/${conversation.id}`); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not create the conversation."); setBusy(false); }
  }
  if (loading) return <p role="status">Loading conversations…</p>;
  return <><p className="notice">Enter client messages manually. Approved replies are saved as local email drafts. Nothing is sent to a client.</p>
    {error && <p role="alert" className="error">{error} {!account && <Link href="/sign-in">Sign in</Link>}</p>}
    <div className="cards portfolio-columns"><section className="card"><h2>Start a conversation</h2>
      {!jobs.length ? <p><Link href="/inbox">Add a job</Link> before starting its client conversation.</p> : <form onSubmit={submit}>
        <label htmlFor="conversation-job">Related job</label><select id="conversation-job" name="job" required>{jobs.map(job => <option key={job.id} value={job.id}>{job.title}</option>)}</select>
        <label htmlFor="conversation-title">Conversation title</label><input id="conversation-title" name="title" required maxLength={200} />
        <label htmlFor="conversation-message">Client message</label><textarea id="conversation-message" name="text" required maxLength={8000} rows={6} />
        <button disabled={busy || !account}>{busy ? "Starting…" : "Draft a reply"}</button>
      </form>}</section><section className="card"><h2>Client conversations</h2>{!threads.length && <p>No conversations yet.</p>}
      {threads.map(thread => <article className="evidence-hit" key={thread.id}><h3><Link href={`/messages/${thread.id}`}>{thread.title}</Link></h3><p>{thread.revision} client messages · {new Date(thread.created_at).toLocaleString()}</p></article>)}
    </section></div></>;
}
