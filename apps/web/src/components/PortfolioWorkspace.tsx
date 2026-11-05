"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { ApiError, getAccount, type Account } from "@/lib/api/accounts";
import { deleteDocument, listDocuments, retryDocument, searchPortfolio, uploadDocument,
  type DocumentMetadata, type DocumentView, type PortfolioSearch, type SearchResult } from "@/lib/api/portfolio";

export function PortfolioWorkspace() {
  const [account, setAccount] = useState<Account | null>(null);
  const [documents, setDocuments] = useState<DocumentView[]>([]);
  const [loading, setLoading] = useState(true);
  const [needsSignIn, setNeedsSignIn] = useState(false);
  const [busy, setBusy] = useState(false);
  const [searching, setSearching] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [results, setResults] = useState<SearchResult | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);

  const load = useCallback(async () => { setDocuments(await listDocuments()); }, []);
  useEffect(() => {
    let active = true;
    Promise.all([getAccount(), listDocuments()]).then(([user, docs]) => {
      if (active) { setAccount(user); setDocuments(docs); }
    }).catch(err => {
      if (active) { setNeedsSignIn(err instanceof ApiError && err.status === 401); setError(err.message); }
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, []);
  useEffect(() => {
    if (!documents.some(doc => ["queued", "indexing"].includes(doc.status))) return;
    const timer = setInterval(() => load().catch(err => setError(err.message)), 3000);
    return () => clearInterval(timer);
  }, [documents, load]);

  async function upload(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!account) return;
    const form = event.currentTarget;
    const data = new FormData(form); const file = data.get("file");
    if (!(file instanceof File) || file.size === 0) { setError("Choose a non-empty portfolio file."); return; }
    if (file.size > 10 * 1024 * 1024) { setError("Files must be at most 10 MB."); return; }
    setBusy(true); setError(""); setMessage("");
    const metadata: DocumentMetadata = {
      project: String(data.get("project")), type: String(data.get("type")) as DocumentMetadata["type"],
      persona: String(data.get("persona")) as DocumentMetadata["persona"],
      skills: String(data.get("skills")).split(",").map(s => s.trim()).filter(Boolean),
      date: String(data.get("date")) || null, client_industry: String(data.get("client_industry")) || null,
      outcome: (String(data.get("outcome")) || null) as DocumentMetadata["outcome"],
    };
    try {
      const doc = await uploadDocument(file, metadata, account.csrf_token);
      setMessage(doc.error ?? (doc.status === "ready" ? "This source is already indexed." : "Upload saved. Background indexing is queued."));
      form.reset(); setResults(null); await load();
    } catch (err) { setError(err instanceof Error ? err.message : "Upload failed."); }
    finally { setBusy(false); }
  }

  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!account) return;
    const data = new FormData(event.currentTarget); setSearching(true); setError("");
    try { setResults(await searchPortfolio({ query: String(data.get("query")),
      variant: String(data.get("variant")) as PortfolioSearch["variant"], k: 5 }, account.csrf_token)); }
    catch (err) { setError(err instanceof Error ? err.message : "Search failed."); }
    finally { setSearching(false); }
  }

  if (loading) return <p role="status">Loading your portfolio…</p>;
  if (needsSignIn) return <p className="notice">Sign in to manage your portfolio. <Link href="/sign-in">Sign in</Link></p>;
  if (!account) return <p role="alert" className="error">{error || "Portfolio unavailable."}</p>;

  return <>
    {error && <p role="alert" className="error">{error}</p>}{message && <p role="status" className="notice">{message}</p>}
    <div className="cards portfolio-columns"><section className="card"><h2>Add portfolio evidence</h2>
      <p className="muted">CVs, case studies, reviews and past proposals. Uploading the same filename updates that source and replaces its old evidence IDs.</p>
      <form onSubmit={upload}>
        <label htmlFor="portfolio-file">Portfolio file</label><input id="portfolio-file" name="file" type="file" accept=".pdf,.md,.txt" required />
        <p className="muted">PDF with selectable text, Markdown or UTF-8 text; maximum 10 MB.</p>
        <label htmlFor="project">Project or portfolio title</label><input id="project" name="project" required maxLength={200} />
        <label htmlFor="document-type">Evidence type</label><select id="document-type" name="type" defaultValue="case_study">
          <option value="case_study">Case study</option><option value="cv">CV</option><option value="readme">README</option>
          <option value="code">Code excerpt</option><option value="review">Client review</option><option value="proposal">Past proposal</option>
        </select>
        <label htmlFor="evidence-persona">Persona</label><select id="evidence-persona" name="persona" defaultValue="own">
          <option value="own">My own profile</option><option value="ai_ml">AI / ML engineer</option><option value="full_stack">Full-stack developer</option><option value="data_analyst">Data analyst</option>
        </select>
        <label htmlFor="skills">Skills (comma separated)</label><input id="skills" name="skills" maxLength={2000} placeholder="Python, FastAPI, PostgreSQL" />
        <label htmlFor="source-date">Source date, if known</label><input id="source-date" name="date" type="date" />
        <label htmlFor="industry">Client industry, if known</label><input id="industry" name="client_industry" maxLength={200} />
        <label htmlFor="outcome">Past proposal outcome</label><select id="outcome" name="outcome" defaultValue="">
          <option value="">Unknown / not applicable</option><option value="won">Won</option><option value="replied">Replied</option><option value="ignored">Ignored</option>
        </select>
        <button type="submit" disabled={busy}>{busy ? "Saving upload…" : "Upload evidence"}</button>
      </form>
    </section><section className="card"><h2>Search your evidence</h2>
      <form onSubmit={search}>
        <label htmlFor="evidence-query">Job requirement</label><textarea id="evidence-query" name="query" required maxLength={4000} rows={4} placeholder="Experience building Python APIs with PostgreSQL" />
        <label htmlFor="retrieval-variant">Retrieval variant</label><select id="retrieval-variant" name="variant" defaultValue="v0">
          <option value="v0">V0 · Dense baseline</option><option value="v1">V1 · Per requirement</option><option value="v2">V2 · Hybrid BM25 + dense</option><option value="v3">V3 · Cross-encoder reranking</option><option value="v8">V8 · Corrective retrieval</option>
        </select>
        <p className="muted">Development comparison controls. The final pipeline will be chosen using the instructor&apos;s evaluation data.</p>
        <button type="submit" disabled={searching || !documents.some(d => d.status === "ready")}>{searching ? "Searching evidence…" : "Search evidence"}</button>
      </form>
      {results && <section aria-label="Evidence results"><h3>{results.items.length ? "Retrieved evidence" : "No supporting evidence found"}</h3>
        {results.items.map(hit => <article className="evidence-hit" key={hit.evidence.id}>
          <strong>{hit.evidence.project ?? hit.evidence.source}</strong>
          <p className="muted">{hit.evidence.source}{hit.evidence.page ? ` · page ${hit.evidence.page}` : ""} · {hit.evidence.type}</p>
          <p>{hit.evidence.text}</p><details><summary>Source details</summary><code>{hit.evidence.id}</code>
          <p>Skills: {hit.evidence.skills?.join(", ") || "Not provided"}</p><p>Ranking score: {hit.score.toFixed(4)} · {results.variant}</p></details>
        </article>)}
      </section>}
    </section></div>
    <section className="card" style={{ marginTop: 24 }}><h2>Your sources</h2>
      {!documents.length && <p className="muted">No portfolio evidence yet. Add your first CV or case study above.</p>}
      {documents.map(doc => <article className="source-row" key={doc.id}>
        <div><strong>{doc.filename}</strong><p className="muted">{doc.details.project} · revision {doc.revision} · <span className={`source-status ${doc.status}`} data-testid="source-status">{doc.status}</span></p>
          {doc.error && <p className="error">{doc.error}</p>}</div>
        <div className="source-actions">{doc.status !== "indexing" && <button className="secondary-button" onClick={async () => {
          try { await retryDocument(doc.id, account.csrf_token); await load(); } catch (err) { setError((err as Error).message); }
        }}>{doc.status === "ready" ? "Re-index" : "Retry indexing"}</button>}
        {deleting === doc.id ? <><button onClick={async () => {
          try { await deleteDocument(doc.id, account.csrf_token); setDeleting(null); setResults(null); await load(); }
          catch (err) { setError((err as Error).message); }
        }}>Confirm delete</button><button className="text-button" onClick={() => setDeleting(null)}>Cancel</button></>
          : <button className="text-button" onClick={() => setDeleting(doc.id)}>Delete</button>}</div>
      </article>)}
    </section>
  </>;
}
