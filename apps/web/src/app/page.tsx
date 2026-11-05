import Link from "next/link";
import { getSkeletonStatus } from "@/lib/api/client";

export default async function Home() {
  let status;
  try { status = await getSkeletonStatus(); } catch { status = null; }
  return <><p className="eyebrow">AI-4016 / Freelancer copilot</p><h1>Your freelancer workspace.</h1>
    <p className="muted">Discover jobs, connect requirements to portfolio evidence, and keep every outgoing action under human control.</p>
    <p className="notice" role="status">{status ? status.message : "API unavailable. Start the FastAPI service to connect this workspace."}</p>
    <div className="cards"><section className="card"><h2>Start with one job</h2><p>Build the path from job inbox to evidence-backed draft to a persisted approval.</p><Link href="/inbox">Open job inbox</Link></section>
    <section className="card"><h2>Set up your workspace</h2><p>Create an account and save your freelancer settings. Portfolio ingestion, marketplace access and agent work are still being built.</p><Link href="/settings">Open settings</Link></section></div>
    <section className="card" style={{marginTop: 24}}><h2>How the pieces connect</h2>
      <p>Web interface → FastAPI → Redis worker → LangGraph → MCP tools → marketplace and portfolio.</p>
      <p className="muted">Postgres will hold durable state. Every external write must pass a human approval and an idempotent execution boundary.</p></section>
  </>;
}
