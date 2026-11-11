"use client";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { getAccount, type Account } from "@/lib/api/accounts";
import { addMessage, getConversation, getMessages, getReplies, type Conversation, type Message, type Reply } from "@/lib/api/messages";
import { RunWorkspace } from "./RunWorkspace";

export function ConversationDetail({ id }: { id: string }) {
  const [thread, setThread] = useState<Conversation | null>(null); const [account, setAccount] = useState<Account | null>(null);
  const [messages, setMessages] = useState<Message[]>([]); const [replies, setReplies] = useState<Reply[]>([]);
  const [text, setText] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  const request = useRef({ text: "", key: "" });
  const refreshHistory = useCallback(async () => { const [history, drafts] = await Promise.all([getMessages(id), getReplies(id)]); setMessages(history); setReplies(drafts); }, [id]);
  useEffect(() => { let active = true;
    Promise.all([getConversation(id), getAccount(), getMessages(id), getReplies(id)]).then(([conversation, user, history, drafts]) => {
      if (active) { setThread(conversation); setAccount(user); setMessages(history); setReplies(drafts); }
    }).catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [id]);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!account) return; setBusy(true); setError("");
    if (request.current.text !== text) request.current = { text, key: crypto.randomUUID() };
    try { setThread(await addMessage(id, text, request.current.key, account.csrf_token)); setText(""); request.current = { text: "", key: "" }; await refreshHistory(); }
    catch (err) { setError(err instanceof Error ? err.message : "Could not add this message."); } finally { setBusy(false); }
  }
  if (!thread) return error ? <p role="alert" className="error">{error} <Link href="/sign-in">Sign in</Link></p> : <p role="status">Loading conversation…</p>;
  return <><h2>{thread.title}</h2><p className="notice">{thread.provider_id ? "This thread is linked to the student simulator. Approved replies are sent only to the simulation. New incoming messages invalidate a pending review." : "Client messages are entered manually. Each new message replaces any pending reply review. Approved email drafts remain local."}</p>
    {error && <p role="alert" className="error">{error}</p>}
    <div className="cards portfolio-columns"><section className="card"><h2>Client messages</h2>{messages.map(message => <article className="evidence-hit" key={message.id}><p>{message.text}</p><small>{new Date(message.created_at).toLocaleString()}</small></article>)}
      <form onSubmit={submit}><label htmlFor="next-client-message">New client message</label><textarea id="next-client-message" value={text} onChange={event => setText(event.target.value)} required maxLength={8000} rows={4} /><button disabled={busy}>{busy ? "Adding…" : "Add message and draft reply"}</button></form>
    </section><section className="card"><h2>{thread.provider_id ? "Approved simulator replies" : "Approved local email drafts"}</h2>{!replies.length && <p>No approved replies saved yet.</p>}{replies.map(reply => <article className="evidence-hit" key={reply.id}><p style={{ whiteSpace: "pre-wrap" }}>{reply.body}</p><small>{reply.status ?? "local draft"} · {new Date(reply.created_at).toLocaleString()}</small></article>)}</section></div>
    <RunWorkspace key={thread.revision} id={thread.run_id} onSaved={refreshHistory} />
  </>;
}
