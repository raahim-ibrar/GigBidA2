import Link from "next/link";
import { getSkeletonStatus } from "@/lib/api/client";

export default async function Home() {
  let status;
  try { status = await getSkeletonStatus(); } catch { status = null; }
  return <><p className="eyebrow">AI-4016 / Freelancer copilot</p><h1>Your freelancer workspace.</h1>
    <p className="muted">Discover jobs, connect requirements to portfolio evidence, and keep every outgoing action under human control.</p>
    <p className="notice" role="status">{status ? status.message : "API unavailable. Start the FastAPI service to connect this workspace."}</p>
    <div className="cards"><section className="card"><h2>Start with one job</h2><p>Enter a job, inspect its match to your portfolio, and review a local proposal draft.</p><Link href="/inbox">Open job inbox</Link></section>
    <section className="card"><h2>Add your evidence</h2><p>Upload your CV or case studies so experience claims can point back to their sources.</p><Link href="/portfolio">Open portfolio</Link></section></div>
    <section className="card" style={{marginTop: 24}}><h2>Review before saving</h2>
      <p>Inspect the supporting evidence, edit the draft, or reject it with a reason. Edited drafts require verification and another review.</p>
      <p className="muted">Approved drafts are saved locally. Marketplace submission is pending, so no applications are sent and no Connects are spent.</p></section>
  </>;
}
