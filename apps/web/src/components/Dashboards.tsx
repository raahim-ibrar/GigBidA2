"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { apiRequest } from "@/lib/api/accounts";
import type { components } from "@/lib/api/schema";
type Pipeline = components["schemas"]["PipelineView"];
type Analytics = components["schemas"]["AnalyticsView"];
const stages = ["drafted", "submitted", "viewed", "replied", "interview", "hired", "lost"] as const;

function useDashboard<T>(path: string) {
  const [saved, setSaved] = useState<{ path: string; value: T } | null>(null);
  const [error, setError] = useState(""); const [refresh, setRefresh] = useState(0);
  useEffect(() => { let active = true;
    async function load() { try { const value = await apiRequest<T>(path); if (active) { setSaved({ path, value }); setError(""); } }
      catch (err) { if (active) setError(err instanceof Error ? err.message : "Could not refresh this view."); } }
    void load(); const timer = setInterval(() => void load(), 30000);
    return () => { active = false; clearInterval(timer); };
  }, [path, refresh]);
  return { data: saved?.path === path ? saved.value : null, error, refresh: () => setRefresh(value => value + 1) };
}

function LoadError({ message }: { message: string }) {
  return <p role="alert" className="error">{message} <Link href="/sign-in">Sign in</Link> if your session has expired.</p>;
}

export function PipelineBoard() {
  const { data, error, refresh } = useDashboard<Pipeline>("/pipeline");
  return <><p className="notice">Track approved drafts and confirmed simulator activity. Simulator replies and hires are generated scenarios, not real client outcomes.</p>
    <button className="secondary-button" onClick={refresh}>Refresh pipeline</button>{error && <LoadError message={error} />}
    {!data ? !error && <p role="status">Loading pipeline…</p> : <>
      {data.truncated && <p className="notice">Showing the latest 200 proposal runs.</p>}
      {!data.cards.length && <p>No approved drafts or provider events yet. <Link href="/inbox">Open the job inbox</Link> to start.</p>}
      <div className="pipeline-board">{stages.map(stage => { const cards = data.cards.filter(card => card.stage === stage); return <section className="pipeline-column" key={stage} aria-label={`${stage} proposals`}>
        <h2>{stage[0].toUpperCase() + stage.slice(1)} <span className="muted">({cards.length})</span></h2>
        {!cards.length && <p className="muted">No proposals.</p>}{cards.map(card => <article className="card pipeline-card" key={card.run_id}>
          <h3><Link href={`/jobs/${card.job_id}`}>{card.title}</Link></h3><p className="muted">{card.source === "local" ? "Local draft · not submitted" : card.source}</p>
          <Link href={`/studio/${card.run_id}`}>Open proposal</Link><p><small>{new Date(card.updated_at).toLocaleString()}</small></p>
        </article>)}
      </section>; })}</div>
    </>}
  </>;
}

const measured = (value: number | null | undefined, suffix = "") => value == null ? "Not measured" : `${value.toLocaleString(undefined, { maximumFractionDigits: 3 })}${suffix}`;

export function AnalyticsDashboard() {
  const [days, setDays] = useState(30);
  const { data, error, refresh } = useDashboard<Analytics>(`/analytics?days=${days}`);
  return <><p className="notice">Activity comes from saved runs and confirmed provider receipts. Student simulator outcomes are synthetic; rates are grouped by source. Local inference charges exclude hardware and electricity.</p>
    <label htmlFor="analytics-window">Run creation window</label><select id="analytics-window" value={days} onChange={event => setDays(Number(event.target.value))}><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option><option value={365}>Last year</option></select>
    <button className="secondary-button" onClick={refresh}>Refresh analytics</button>{error && <LoadError message={error} />}
    {!data ? !error && <p role="status">Loading analytics…</p> : <>
      <div className="cards metric-cards"><section className="card"><h2>Agent runs</h2><p className="metric-value">{data.run_count}</p></section>
        <section className="card"><h2>Approved local proposals</h2><p className="metric-value">{data.local_drafts}</p></section>
        <section className="card"><h2>Charged or reserved tokens</h2><p className="metric-value">{data.charged_or_reserved_tokens.toLocaleString()}</p><p>Measured model tokens: {measured(data.measured_model_tokens)}</p></section>
        <section className="card"><h2>Measured inference API charges</h2><p className="metric-value">{data.inference_api_usd == null ? "Not measured" : `$${data.inference_api_usd.toFixed(4)}`}</p><p>Sum of recorded calls; failed calls may have unknown usage.</p></section>
      </div>
      <section className="card draft-panel"><h2>Marketplace outcomes by category</h2><p>Verified submissions: {data.provider_submissions}. Known Connects spend: {data.connects_spent == null ? "Unavailable" : `${data.connects_spent} across ${data.submissions_with_known_spend} submissions`}.</p>
        {!data.category_rates.length ? <p>No verified submission cohort is available. Reply and hire rates are unavailable.</p> : <div className="table-scroll" tabIndex={0} role="region" aria-label="Marketplace outcome rates"><table><thead><tr><th scope="col">Source</th><th scope="col">Category</th><th scope="col">Submitted</th><th scope="col">Replied</th><th scope="col">Hired</th><th scope="col">Reply rate</th><th scope="col">Hire rate</th></tr></thead><tbody>{data.category_rates.map(row => <tr key={`${row.provider}:${row.category}`}><td>{row.provider === "student_sim" ? "Simulator · synthetic" : row.provider}</td><th scope="row">{row.category.replaceAll("_", " ")}</th><td>{row.submitted}</td><td>{row.replied}</td><td>{row.hired}</td><td>{(row.reply_rate * 100).toFixed(1)}%</td><td>{(row.hire_rate * 100).toFixed(1)}%</td></tr>)}</tbody></table></div>}
        <p className="muted">Rates use proposals with a verified submission receipt in the selected run-creation cohort. Interviews and hires count as replies. Recent proposals may still be awaiting outcomes.</p>
      </section>
      <section className="card draft-panel"><h2>Top human rejection reasons</h2>{data.rejection_reasons.length ? <ul>{data.rejection_reasons.map((item, i) => <li key={i}>{item.reason} · {item.count}</li>)}</ul> : <p>No recorded rejections in this period.</p>}</section>
      <section className="card draft-panel"><h2>Cost and latency per run</h2><p className="muted">Completed worker segments exclude human review wait. Model-call seconds add parallel calls and are not wall-clock latency. Measurements may be partial after a crash.</p>
        {data.measurements_truncated && <p>Showing the latest 200 runs; totals above include the full cohort.</p>}
        {!data.measurements.length ? <p>No runs in this period.</p> : <div className="table-scroll" tabIndex={0} role="region" aria-label="Run measurements"><table><thead><tr><th scope="col">Run</th><th scope="col">Status</th><th scope="col">Tokens charged/reserved</th><th scope="col">Model tokens</th><th scope="col">Worker seconds</th><th scope="col">Model-call seconds</th><th scope="col">API USD</th></tr></thead><tbody>{data.measurements.map(row => <tr key={row.run_id}><th scope="row"><Link href={`/runs/${row.run_id}`}>{row.job_title}</Link><br /><small>{row.kind}</small></th><td>{row.status.replaceAll("_", " ")}</td><td>{row.charged_or_reserved_tokens}</td><td>{measured(row.measured_model_tokens)}</td><td>{measured(row.measured_worker_seconds)}</td><td>{measured(row.model_call_seconds)}</td><td>{measured(row.inference_api_usd)}</td></tr>)}</tbody></table></div>}
      </section>
    </>}
  </>;
}
